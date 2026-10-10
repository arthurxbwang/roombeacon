"""Publish snapshots in fetch-start order so slow reads cannot undo newer truth."""
import structlog

from ..schemas.meeting_room import RoomSchedule
from .room_usage_store import PREFIX, encoded

logger = structlog.get_logger()

SNAPSHOT_CAS = """
if (redis.call('get',KEYS[1]) or '') ~= ARGV[1] then return 0 end
redis.call('set',KEYS[1],ARGV[2],'EX',ARGV[3])
redis.call('set',KEYS[2],ARGV[4],'EX',ARGV[3]); return 1
"""


async def save_snapshot(cache, snapshot, ttl, *, source_rows=()):
    from .room_calendar_evidence import source_evidence
    key = 'rooms:snapshot:' + snapshot.room.room_id
    sources = encoded(source_evidence(snapshot, source_rows))
    for _ in range(3):
        raw = await cache.get(key)
        if raw:
            try:
                previous = RoomSchedule.model_validate_json(raw)
            except ValueError:
                logger.warning('room_snapshot_invalid_replaced', room_id=snapshot.room.room_id)
            else:
                if previous.synced_at > snapshot.synced_at:
                    return False
        if await cache.eval(SNAPSHOT_CAS, 2, key, PREFIX + 'sources:' + snapshot.room.room_id,
                            raw or '', snapshot.model_dump_json(), ttl, sources):
            return True
    raise RuntimeError('Concurrent snapshot refresh did not settle')
