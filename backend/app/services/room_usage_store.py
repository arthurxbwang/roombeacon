"""Atomic V5 records and bounded audit, isolated under new Redis keys."""
import json
from datetime import UTC, datetime

PREFIX = 'rooms:usage:v1:'
TTL = 7 * 86400
AUDIT_TTL = 30 * 86400
CAS = """
if (redis.call('get', KEYS[1]) or '') ~= ARGV[1] then return 0 end
if KEYS[3] ~= '' and (redis.call('get', KEYS[3]) or '') ~= ARGV[4] then return 0 end
redis.call('set', KEYS[1], ARGV[2], 'EX', ARGV[3])
if ARGV[7] ~= 'monitor' then
 redis.call('lpush', KEYS[2], ARGV[5])
 redis.call('ltrim', KEYS[2], 0, 999)
 redis.call('expire', KEYS[2], ARGV[6])
end
return 1
"""


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


class UsageStore:
    def __init__(self, cache):
        self.cache = cache

    async def get(self, name, default=None):
        raw = await self.cache.get(PREFIX + name)
        return json.loads(raw) if raw else default

    async def put(self, name, value, ttl=TTL):
        await self.cache.set(PREFIX + name, encoded(value), ex=ttl)

    async def cas(self, name, old, new, room_id, *, policy=None, action='state'):
        values = new if isinstance(new, dict) else {'paused': new}
        audit = {'time': datetime.now(UTC).isoformat(), 'action': action,
                 'room_id': room_id, 'occurrence_id': values.get('id'),
                 'state': values.get('state'), 'reason': values.get('reason')}
        audit.update({k: values[k] for k in ('mode', 'revision', 'paused') if k in values})
        return bool(await self.cache.eval(CAS, 3, PREFIX + name, PREFIX + 'audit:' + room_id,
                                         PREFIX + 'policy:' + room_id if policy is not None else '',
                                         encoded(old) if old is not None else '', encoded(new), TTL,
                                         encoded(policy) if policy is not None else '',
                                         encoded(audit), AUDIT_TTL, action))

    async def audit(self, room_id):
        return [json.loads(row) for row in await self.cache.lrange(PREFIX + 'audit:' + room_id, 0, 99)]

    async def rooms(self):
        return sorted(await self.cache.smembers(PREFIX + 'rooms'))
