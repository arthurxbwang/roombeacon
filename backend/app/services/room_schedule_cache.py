"""Publish snapshots in fetch-start order so slow reads cannot undo newer truth."""
import structlog

from ..schemas.meeting_room import RoomSchedule

logger = structlog.get_logger()

SNAPSHOT_CAS = """
if (redis.call('get',KEYS[1]) or '') ~= ARGV[1] then return 0 end
redis.call('set',KEYS[1],ARGV[2],'EX',ARGV[3]); return 1
"""


async def save_snapshot(cache, snapshot, ttl):
    key = 'rooms:snapshot:' + snapshot.room.room_id
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
        if await cache.eval(SNAPSHOT_CAS, 1, key, raw or '', snapshot.model_dump_json(), ttl):
            return True
    raise RuntimeError('Concurrent snapshot refresh did not settle')
