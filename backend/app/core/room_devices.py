"""Revocable room-scoped display credentials; never accepted as user JWTs."""
import hashlib
import hmac
import re
import secrets
from contextlib import asynccontextmanager

import redis.asyncio as redis
import structlog
from redis.exceptions import RedisError

from .config import settings
from .exceptions import ExternalAPIError, UnauthorizedError

logger = structlog.get_logger(__name__)
DEVICE_TTL = 30 * 86400


@asynccontextmanager
async def room_cache():
    client = redis.from_url(settings.REDIS_URL, decode_responses=True,
                             socket_connect_timeout=3, socket_timeout=3)
    try:
        yield client
    except RedisError as exc:
        logger.warning("room_cache_unavailable", error_type=type(exc).__name__)
        raise ExternalAPIError("room-cache", "Redis unavailable") from exc
    finally:
        await client.aclose()


async def issue_device(room_id: str) -> str:
    token = f"room:{room_id}:{secrets.token_urlsafe(32)}"
    async with room_cache() as cache:
        await cache.set(f"rooms:device:{room_id}", hashlib.sha256(token.encode()).hexdigest(), ex=DEVICE_TTL)
    logger.info("room_device_issued", room_id=room_id)
    return token


async def revoke_device(room_id: str) -> None:
    async with room_cache() as cache:
        await cache.delete(f"rooms:device:{room_id}")
    logger.info("room_device_revoked", room_id=room_id)


async def authenticate_device(token: str, path: str, method: str) -> dict:
    if path != "/api/meeting-rooms/display" or method != "GET":
        raise UnauthorizedError("门牌凭证仅可读取绑定会议室")
    match = re.fullmatch(r"room:(omm_[a-zA-Z0-9]{1,96}):[A-Za-z0-9_-]{43}", token)
    if not match:
        raise UnauthorizedError("门牌凭证无效")
    room_id = match.group(1)
    async with room_cache() as cache:
        digest = await cache.get(f"rooms:device:{room_id}")
    if not digest or not hmac.compare_digest(digest, hashlib.sha256(token.encode()).hexdigest()):
        raise UnauthorizedError("门牌凭证已失效，请重新绑定")
    return {"role": "room_display", "room_id": room_id}
