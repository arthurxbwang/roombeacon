"""Best-effort invalidation; polling recovers missed Feishu events."""
import re
import time

import redis
import structlog

from ..core.config import settings
from ..core.room_devices import room_cache

logger = structlog.get_logger(__name__)
EVENT_TYPE = "meeting_room.meeting_room.status_changed_v1"


def valid_room_id(room_id: str) -> bool:
    return isinstance(room_id, str) and bool(re.fullmatch(r"omm_[A-Za-z0-9]{1,96}", room_id))


async def invalidate_room(room_id: str) -> None:
    if not valid_room_id(room_id):
        logger.warning("room_event_invalid_id")
        return
    async with room_cache() as cache:
        await cache.set(f"rooms:dirty:{room_id}", str(time.time()), ex=600)
        await cache.delete("rooms:catalog")


def handle_room_event(raw: dict) -> None:
    room_id = (raw.get("event") or {}).get("room_id", "")
    if not valid_room_id(room_id):
        logger.warning("room_event_invalid_id")
        return
    try:
        with redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=3, socket_timeout=3) as cache:
            cache.set(f"rooms:dirty:{room_id}", str(time.time()), ex=600)
            cache.delete("rooms:catalog")
    except redis.RedisError as exc:
        logger.warning("room_event_cache_failed", error_type=type(exc).__name__)
        raise
