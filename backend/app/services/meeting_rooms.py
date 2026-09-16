"""Shared batch snapshots. No calls to Feishu originate from a tablet."""
import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import structlog

from ..connectors.feishu.rooms import FeishuRoomsClient
from ..core.exceptions import ExternalAPIError, NotFoundError
from ..core.room_devices import room_cache
from ..schemas.meeting_room import Room, RoomEvent, RoomSchedule

logger = structlog.get_logger(__name__)
ZONE = ZoneInfo("Asia/Shanghai")
SYNC_SECONDS = 300


async def catalog(cache, client: FeishuRoomsClient) -> list[Room]:
    saved = await cache.get("rooms:catalog")
    if saved:
        return [Room.model_validate(row) for row in json.loads(saved)]
    rows = await client.list_rooms()
    rooms = sorted([Room(
        room_id=row["room_id"], name=row["name"], capacity=row.get("capacity", 0),
        enabled=(row.get("room_status") or {}).get("status", True),
    ) for row in rows], key=lambda room: room.room_id)
    await cache.set("rooms:catalog", json.dumps([room.model_dump() for room in rooms]), ex=300)
    return rooms


def parse_events(rows: list[dict]) -> list[RoomEvent]:
    events = {}
    for row in rows:
        event = RoomEvent(
            uid=row["uid"], original_time=row.get("original_time", 0),
            start_time=row["start_time"], end_time=row["end_time"],
            organizer=(row.get("organizer_info") or {}).get("name") or None,
        )
        if event.start_time.tzinfo is None or event.end_time.tzinfo is None:
            raise ValueError("Meeting timestamps must include timezone")
        if event.end_time <= event.start_time:
            raise ValueError("Meeting end must follow start")
        # A recurring series can have multiple occurrences with original_time=0.
        events[(event.uid, event.original_time, event.start_time)] = event
    return sorted(events.values(), key=lambda event: event.start_time)


async def refresh_batch(cache, client, rooms: list[Room], now: datetime, *,
                        snapshot_ttl: int = 86400, fresh_seconds: int = SYNC_SECONDS) -> int:
    start = now.astimezone(ZONE).replace(hour=0, minute=0, second=0, microsecond=0)
    data = await client.freebusy([room.room_id for room in rooms], start - timedelta(days=1), start + timedelta(days=2))
    busy = data["free_busy"]
    failed = set(data.get("error_room_ids") or [])
    parsed = {}
    for room in rooms:
        if room.room_id in failed or room.room_id not in busy:
            logger.warning("room_schedule_missing", room_id=room.room_id)
            continue
        try:
            parsed[room.room_id] = parse_events(busy[room.room_id])
        except (KeyError, TypeError, ValueError):
            logger.warning("room_schedule_parse_failed", room_id=room.room_id)
    refs = {(event.uid, event.original_time) for events in parsed.values() for event in events if event.organizer}
    titles, titles_available = {}, True
    try:
        keys = sorted(refs)
        for offset in range(0, len(keys), 50):
            details = await client.summaries([
                {"uid": uid, "original_time": original} for uid, original in keys[offset:offset + 50]
            ])
            if details.get("ErrorEventUids"):
                titles_available = False
            for info in details["EventInfos"]:
                titles[(info["uid"], info["original_time"])] = info.get("summary")
    except (ExternalAPIError, httpx.HTTPError, KeyError, TypeError, ValueError):
        logger.warning("room_titles_unavailable")
        titles_available = False
    for room in rooms:
        if room.room_id not in parsed:
            continue
        for event in parsed[room.room_id]:
            # Do not expose a title for an occurrence with hidden organizer data.
            if event.organizer:
                event.summary = titles.get((event.uid, event.original_time)) or None
        schedule = RoomSchedule(
            room=room, events=parsed[room.room_id], synced_at=now,
            valid_until=min(now + timedelta(seconds=fresh_seconds), start + timedelta(days=1)),
            titles_available=titles_available,
        )
        await cache.set(f"rooms:snapshot:{room.room_id}", schedule.model_dump_json(), ex=snapshot_ttl)
    return len(parsed)


async def list_rooms() -> list[Room]:
    client = FeishuRoomsClient()
    try:
        async with room_cache() as cache:
            return await asyncio.wait_for(catalog(cache, client), timeout=20)
    except (TimeoutError, httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        logger.warning("room_catalog_invalid", error_type=type(exc).__name__)
        raise ExternalAPIError("feishu", "Incomplete room catalog") from exc
    finally:
        await client.close()


async def schedule_for(room_id: str) -> RoomSchedule:
    client = FeishuRoomsClient()
    try:
        async with room_cache() as cache:
            return await asyncio.wait_for(_schedule(cache, client, room_id), timeout=25)
    except (TimeoutError, httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        logger.warning("room_schedule_invalid", room_id=room_id, error_type=type(exc).__name__)
        raise ExternalAPIError("feishu", "Incomplete room schedule") from exc
    finally:
        await client.close()


async def _schedule(cache, client, room_id: str) -> RoomSchedule:
    now = datetime.now(UTC)
    saved = await cache.get(f"rooms:snapshot:{room_id}")
    previous = RoomSchedule.model_validate_json(saved) if saved else None
    dirty = float(await cache.get(f"rooms:dirty:{room_id}") or 0)
    if previous and previous.valid_until > now and previous.synced_at.timestamp() >= dirty:
        return previous
    rooms = await catalog(cache, client)
    index = next((i for i, room in enumerate(rooms) if room.room_id == room_id), None)
    if index is None:
        raise NotFoundError("会议室不存在或已删除")
    batch = rooms[index // 20 * 20:index // 20 * 20 + 20]
    group = hashlib.sha256(",".join(room.room_id for room in batch).encode()).hexdigest()
    # Retained for 30 seconds, including failures, to avoid retry storms across workers.
    if await cache.set(f"rooms:refresh:{group}", "1", nx=True, ex=30):
        await refresh_batch(cache, client, batch, now)
        saved = await cache.get(f"rooms:snapshot:{room_id}")
        if saved:
            refreshed = RoomSchedule.model_validate_json(saved)
            dirty = float(await cache.get(f"rooms:dirty:{room_id}") or 0)
            if refreshed.synced_at.timestamp() >= dirty:
                return refreshed
    if previous:
        return previous.model_copy(update={"valid_until": min(previous.valid_until, now)})
    raise ExternalAPIError("feishu", "Room snapshot is unavailable; retry shortly")
