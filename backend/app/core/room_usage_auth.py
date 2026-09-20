"""Independent V5 action credentials; legacy room tokens remain read-only."""
import hashlib
import hmac
import re
import secrets

from .exceptions import UnauthorizedError
from .room_devices import DEVICE_TTL, room_cache

KEY = 'rooms:usage:v1:credential:'


async def issue_usage(room_id):
    token = f'usage:{room_id}:{secrets.token_urlsafe(32)}'
    async with room_cache() as cache:
        await cache.set(KEY + room_id, hashlib.sha256(token.encode()).hexdigest(), ex=DEVICE_TTL)
    return token


async def revoke_usage(room_id):
    async with room_cache() as cache:
        await cache.delete(KEY + room_id)


async def authenticate_usage(token):
    match = re.fullmatch(r'usage:(omm_[A-Za-z0-9]{1,96}):[A-Za-z0-9_-]{43}', token)
    if not match:
        raise UnauthorizedError('V5 操作凭证无效')
    room_id = match.group(1)
    digest = hashlib.sha256(token.encode()).hexdigest()
    async with room_cache() as cache:
        expected = await cache.get(KEY + room_id)
    if not expected or not hmac.compare_digest(expected, digest):
        raise UnauthorizedError('V5 操作凭证已失效')
    return room_id, digest
