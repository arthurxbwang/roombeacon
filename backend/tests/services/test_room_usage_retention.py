"""Room rules outlive transient booking and terminal state."""
import pytest

from app.schemas.room_usage import UsagePolicy
from app.services.room_usage import save_policy
from app.services.room_usage_store import PREFIX, TTL
from tests.services import test_room_usage as support

redis_socket = support.redis_socket
setup_usage = support.setup_usage


@pytest.mark.asyncio
async def test_saved_policy_and_qualification_do_not_expire(setup_usage):
    store = setup_usage[0]
    policy = await save_policy(store, 'omm_one', UsagePolicy(
        owner='v5', mode='auto', native_policy_cleared=True, release_verified=True))
    assert await store.cache.ttl(PREFIX + 'policy:omm_one') == -1
    assert await store.get('policy:omm_one') == policy
    # Bookings stay bounded; the administrator's pause choice is durable.
    await store.put('record:temporary', {'state': 'blocked'})
    assert 0 < await store.cache.ttl(PREFIX + 'record:temporary') <= TTL
    assert await store.cas('paused', None, False, 'global', action='pause')
    assert await store.cache.ttl(PREFIX + 'paused') == -1
    await store.cache.delete(PREFIX + 'paused')
    assert await store.get('paused', True) is True


@pytest.mark.asyncio
async def test_policy_compare_and_swap_keeps_revision_on_conflict(setup_usage):
    store, _, _, _, policy, *_ = setup_usage
    key = 'policy:omm_one'
    assert not await store.cas(key, None, UsagePolicy().model_dump(), 'omm_one', action='policy')
    assert await store.get(key) == policy
