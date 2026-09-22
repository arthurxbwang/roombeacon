"""Feishu tenant-token transport for read-only room queries."""
from __future__ import annotations

import time
from typing import Any

import httpx
import structlog
from tenacity import (
    retry,
    retry_any,
    retry_if_exception,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ...core.config import settings
from ...core.exceptions import ExternalAPIError

logger = structlog.get_logger()

FEISHU_BASE = "https://open.feishu.cn/open-apis"


def _is_retryable_token_error(exc: BaseException) -> bool:
    return isinstance(exc, ExternalAPIError) and getattr(exc, "retryable_token_error", False)


def _is_retryable_freebusy_gateway_error(exc: BaseException) -> bool:
    return (isinstance(exc, httpx.HTTPStatusError)
            and exc.request.method == "GET"
            and exc.request.url.path == "/open-apis/meeting_room/freebusy/batch_get"
            and exc.response.status_code in {502, 503, 504})


def _before_api_retry(retry_state) -> None:
    exc = retry_state.outcome.exception()
    if _is_retryable_freebusy_gateway_error(exc):
        logger.warning("feishu_freebusy_retry", status_code=exc.response.status_code,
                       attempt=retry_state.attempt_number)
    if _is_retryable_token_error(retry_state.outcome.exception()):
        client = retry_state.args[0]
        client._tenant_token = None
        client._token_expires = 0


class FeishuClient:
    provider = "feishu"

    def __init__(self) -> None:
        self.app_id = settings.FEISHU_APP_ID
        self.app_secret = settings.FEISHU_APP_SECRET
        self._tenant_token: str | None = None
        self._token_expires: float = 0
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _get_tenant_token(self) -> str:
        if self._tenant_token and time.time() < self._token_expires:
            return self._tenant_token

        client = await self._get_client()
        resp = await client.post(
            f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
        )
        resp.raise_for_status()
        try:
            data = resp.json()
        except ValueError as exc:
            raise ExternalAPIError("feishu", "tenant_token response not JSON") from exc
        if not isinstance(data, dict) or data.get("code") != 0 or not data.get("tenant_access_token"):
            raise ExternalAPIError("feishu", "tenant_token request failed")
        self._tenant_token = data["tenant_access_token"]
        self._token_expires = time.time() + data.get("expire", 7200) - 300
        return self._tenant_token

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_any(
            retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
            retry_if_exception(_is_retryable_token_error),
            retry_if_exception(_is_retryable_freebusy_gateway_error),
        ),
        before_sleep=_before_api_retry,
        reraise=True,
    )
    async def _api(self, method: str, path: str, **kwargs: Any) -> dict:
        token = await self._get_tenant_token()
        client = await self._get_client()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        url = f"{FEISHU_BASE}{path}"
        logger.debug("feishu_request", method=method, path=path)

        resp = await client.request(method, url, headers=headers, **kwargs)
        resp.raise_for_status()
        try:
            data = resp.json()
        except ValueError as exc:
            raise ExternalAPIError("feishu", "API response not JSON") from exc
        if not isinstance(data, dict):
            raise ExternalAPIError("feishu", f"unexpected response shape: {type(data).__name__}")
        if data.get("code") == 99991663 or data.get("code") == 99991664:
            self._tenant_token = None
            self._token_expires = 0
            err = ExternalAPIError("feishu", "token expired, will retry")
            err.retryable_token_error = True
            raise err
        if data.get("code") != 0:
            logger.error("feishu_api_error", code=data.get("code"))
            raise ExternalAPIError("feishu", f"API code {data.get('code')}")
        return data

    async def health_check(self) -> bool:
        try:
            await self._get_tenant_token()
            return True
        except Exception:
            logger.debug("feishu_health_check_failed", exc_info=True)
            return False
