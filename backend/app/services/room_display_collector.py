"""Standalone collector owns upstream I/O; display requests only read Redis."""
import asyncio
import json
import secrets
import time
from datetime import UTC, datetime

import structlog

from ..connectors.feishu.rooms import FeishuRoomsClient
from ..core.config import settings
from ..core.exceptions import ExternalAPIError, NotFoundError
from ..core.room_devices import room_cache
from ..schemas.meeting_room import Room, RoomSchedule
from .meeting_rooms import refresh_batch
from .room_daylight import plan_for_location
from .room_display_directory import directory_rows

logger = structlog.get_logger(__name__)
DIRECTORY = 'rooms:collector:directory'
LOCK = 'rooms:collector:lease'
STATUS = 'rooms:collector:status'
HISTORY_SECONDS = 7 * 86400
RELEASE = "if redis.call('get',KEYS[1]) == ARGV[1] then return redis.call('del',KEYS[1]) else return 0 end"


async def cached_directory() -> list[dict]:
    async with room_cache() as cache:
        saved = await cache.get(DIRECTORY) or await cache.get('rooms:management-directory:v1')
    if saved is None:
        raise ExternalAPIError('room-cache', '目录首次同步中，请稍后重试')
    return json.loads(saved)


async def cached_schedule(room_id: str) -> RoomSchedule:
    async with room_cache() as cache:
        rows = await cache.get(DIRECTORY) or await cache.get('rooms:management-directory:v1')
        rooms = json.loads(rows) if rows is not None else None
        room = next((row for row in rooms or [] if row['room_id'] == room_id), None)
        if rooms is not None and room is None:
            raise NotFoundError('会议室不存在或已删除')
        saved = await cache.get(f'rooms:snapshot:{room_id}')
    if not saved:
        raise ExternalAPIError('room-cache', '会议室首次同步中，请稍后重试')
    snapshot = RoomSchedule.model_validate_json(saved)
    now = datetime.now(UTC)
    updates = {'server_time': now, 'daylight': plan_for_location((room or {}).get('location', ''), now)}
    if room:
        updates['room'] = Room.model_validate(room)
    return snapshot.model_copy(update=updates)


async def refresh_directory(cache, client, now: datetime) -> list[dict]:
    saved = await cache.get(DIRECTORY)
    updated = float(await cache.get('rooms:collector:directory-time') or 0)
    if saved is not None and now.timestamp() - updated < 900:
        return json.loads(saved)
    try:
        raw = await asyncio.wait_for(client.list_rooms(), timeout=35)
        previous = {row['room_id']: row for row in json.loads(saved or '[]')}
        try:
            names = await asyncio.wait_for(client.room_levels([level for row in raw for level in row.get('path', [])]), timeout=35)
            rows = directory_rows(raw, names)
        except Exception as exc:
            logger.exception('room_collector_locations_failed', error_type=type(exc).__name__)
            rows = directory_rows(raw, {})
            for row in rows:
                if row['room_id'] in previous:
                    for field in ('location', 'region', 'floor'):
                        row[field] = previous[row['room_id']][field]
        await cache.set(DIRECTORY, json.dumps(rows, ensure_ascii=False), ex=HISTORY_SECONDS)
        await cache.set('rooms:collector:directory-time', str(now.timestamp()), ex=HISTORY_SECONDS)
        return rows
    except Exception as exc:
        logger.exception('room_collector_directory_failed', error_type=type(exc).__name__)
        # Keep last successfully fetched directory during upstream outages.
        if saved is not None:
            return json.loads(saved)
        raise


async def collect_once(cache, client, owner: str) -> None:
    started = datetime.now(UTC)
    rows = await refresh_directory(cache, client, started)
    rooms = sorted([Room.model_validate(row) for row in rows], key=lambda room: room.room_id)
    batches = [rooms[i:i + 20] for i in range(0, len(rooms), 20)]
    cursor = int(await cache.get('rooms:collector:cursor') or 0)
    completed, failed, refreshed = 0, 0, 0
    await cache.set(STATUS, json.dumps({'started_at': started.isoformat(), 'state': 'refreshing', 'rooms': len(rooms)}), ex=HISTORY_SECONDS)
    for step in range(len(batches)):
        if await cache.get(LOCK) != owner:
            raise RuntimeError('Collector lease lost')
        index = (cursor + step) % len(batches)
        # Advance before I/O so a failing/timed-out batch cannot starve later rooms.
        await cache.set('rooms:collector:cursor', str((index + 1) % len(batches)), ex=HISTORY_SECONDS)
        try:
            count = await asyncio.wait_for(refresh_batch(cache, client, batches[index], datetime.now(UTC),
                                                snapshot_ttl=HISTORY_SECONDS,
                                                fresh_seconds=settings.ROOM_DISPLAY_SYNC_SECONDS + 60), timeout=40)
            completed += 1
            refreshed += count
            if count != len(batches[index]):
                failed += 1
        except Exception as exc:
            failed += 1
            logger.exception('room_collector_batch_failed', batch=index, error_type=type(exc).__name__)
        await asyncio.sleep(.2)
    result = {'started_at': started.isoformat(), 'finished_at': datetime.now(UTC).isoformat(),
              'state': 'partial' if failed else 'complete', 'rooms': len(rooms),
              'completed_batches': completed, 'failed_batches': failed, 'refreshed_rooms': refreshed}
    await cache.set(STATUS, json.dumps(result), ex=HISTORY_SECONDS)
    logger.info('room_collector_cycle_complete', **result)


async def collector_loop() -> None:
    # A fixed-window Redis lease caps upstream traffic across workers/restarts.
    # Work is cancelled before lease expiry. No tablet request may acquire it.
    owner = secrets.token_hex(16)
    client = FeishuRoomsClient()
    try:
        while True:
            try:
                async with room_cache() as cache:
                    period = settings.ROOM_DISPLAY_SYNC_SECONDS
                    began = time.monotonic()
                    if await cache.set(LOCK, owner, nx=True, ex=period):
                        budget = max(1, period - 10 - (time.monotonic() - began))
                        await asyncio.wait_for(collect_once(cache, client, owner), timeout=budget)
            except Exception as exc:
                logger.exception('room_collector_cycle_failed', error_type=type(exc).__name__)
            await asyncio.sleep(5)
    finally:
        await client.close()
        try:
            async with room_cache() as cache:
                await cache.eval(RELEASE, 1, LOCK, owner)
        except Exception as exc:
            logger.exception('room_collector_release_failed', error_type=type(exc).__name__)
