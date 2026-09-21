"""Publish only complete upstream readback after a successful room release."""
from datetime import UTC, datetime, timedelta

from ..core.config import settings
from ..schemas.meeting_room import RoomSchedule
from ..schemas.room_usage import Occurrence
from .meeting_rooms import ZONE, parse_events
from .room_schedule_cache import save_snapshot


async def expire_older_snapshot(cache, room_id, now):
    key = 'rooms:snapshot:' + room_id
    raw = await cache.get(key)
    if not raw:
        return
    snapshot = RoomSchedule.model_validate_json(raw)
    if snapshot.synced_at > now:
        return
    snapshot.valid_until = min(snapshot.valid_until, now)
    await cache.eval(
        "if redis.call('get',KEYS[1]) == ARGV[1] then redis.call('set',KEYS[1],ARGV[2],'KEEPTTL'); return 1 end return 0",
        1, key, raw, snapshot.model_dump_json())


async def read_after_release(cache, client, room_id, occurrence):
    now = datetime.now(UTC)
    day = now.astimezone(ZONE).replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        # Same complete window as the central collector, not just the released slot.
        data = await client.freebusy([room_id], day - timedelta(days=1), day + timedelta(days=2))
        if room_id in data.get('error_room_ids', []) or room_id not in data.get('free_busy', {}):
            raise ValueError('Incomplete release readback')
        events = parse_events(data['free_busy'][room_id])
        remaining = [Occurrence.model_validate(event.model_dump()) for event in events]
        still_busy = any(e.uid == occurrence.uid and e.start_time < occurrence.end_time
                         and e.end_time > now for e in remaining)
        raw = await cache.get('rooms:snapshot:' + room_id)
        if still_busy:
            await expire_older_snapshot(cache, room_id, now)
        elif raw:
            previous = RoomSchedule.model_validate_json(raw)
            # Busy periods come entirely from the new response. Do not invent empty
            # periods, copy stale titles or extend freshness after a failed read.
            snapshot = RoomSchedule(
                room=previous.room, events=events, synced_at=now,
                valid_until=min(now + timedelta(seconds=settings.ROOM_DISPLAY_SYNC_SECONDS + 60), day + timedelta(days=2)),
                titles_available=False,
            )
            await save_snapshot(cache, snapshot, 7 * 86400)
        return remaining
    except Exception:
        await expire_older_snapshot(cache, room_id, now)
        raise
