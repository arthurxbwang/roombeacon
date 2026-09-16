import httpx
import pytest

from app.connectors.feishu.client import FeishuClient
from app.core.exceptions import ExternalAPIError
from tests.fixtures.meeting_rooms import HttpClient


@pytest.mark.asyncio
async def test_transport_reuses_tenant_token():
    calls = []
    def respond(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/internal"):
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "test-token", "expire": 7200})
        assert request.headers["authorization"] == "Bearer test-token"
        return httpx.Response(200, json={"code": 0, "data": {}})
    client = FeishuClient()
    client._client = HttpClient(transport=httpx.MockTransport(respond))
    try:
        await client._api("GET", "/vc/v1/rooms")
        await client._api("GET", "/vc/v1/rooms")
        assert sum(p.endswith("/internal") for p in calls) == 1
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [[], {"code": 0}, {"code": 1, "msg": "sensitive-marker"}])
async def test_invalid_token_envelope_is_sanitized(payload, capsys):
    client = FeishuClient()
    client._client = HttpClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload)))
    try:
        with pytest.raises(ExternalAPIError):
            await client._get_tenant_token()
        assert "sensitive-marker" not in capsys.readouterr().out
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_non_json_response_is_not_logged(capsys):
    client = FeishuClient()
    client._client = HttpClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="sensitive-marker")))
    try:
        with pytest.raises(ExternalAPIError):
            await client._get_tenant_token()
        assert "sensitive-marker" not in capsys.readouterr().out
    finally:
        await client.close()
