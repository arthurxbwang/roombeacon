"""Restarted real terminals can sign protected bookings without arming release."""
import pytest

from app.core.exceptions import AppError
from app.schemas.room_usage import UsageHeartbeat
from app.services import room_usage as service
from app.services.room_usage_health import heartbeat
from tests.services import test_room_usage as support

redis_socket = support.redis_socket
setup_usage = support.setup_usage


@pytest.mark.asyncio
async def test_restart_allows_explicit_checkin_from_current_terminal(setup_usage):
    store, client, _, actor, policy, now, _, _ = setup_usage
    request = await support.request_for(store, now)
    request.session_id = 'b' * 32
    old = await store.get('heartbeat:omm_one')
    await store.put('heartbeat:omm_one', old | {'time': now.timestamp() - 46})
    report = UsageHeartbeat(protocol=2, session_id=request.session_id, occurrence_id=request.occurrence_id,
                            policy_revision=policy['revision'], operation_state='submitting')
    await heartbeat(store, 'omm_one', actor, report, now)
    state = await service.view(store, 'omm_one', now)
    assert state['record']['state'] == 'blocked' and state['can_confirm']
    state = await service.command(store, 'omm_one', actor, request, 'confirm', now)
    record = await store.get('record:' + request.occurrence_id)
    assert state['record']['state'] == 'confirmed'
    assert record['session_id'] == request.session_id and record['verified'] is False
    client.release.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['missing', 'stale', 'future', 'actor', 'occurrence', 'policy',
                                  'uncertain', 'not_blocked', 'session', 'protocol', 'revoked'])
async def test_session_recovery_needs_fresh_matching_real_heartbeat(setup_usage, fault):
    store, _, _, actor, _policy, now, _, _ = setup_usage
    request = await support.request_for(store, now)
    key = 'record:' + request.occurrence_id
    record = await store.get(key)
    await store.put(key, record | {'state': 'blocked' if fault != 'not_blocked' else 'pending'})
    request.session_id = 'b' * 32
    hb = await store.get('heartbeat:omm_one')
    hb.update(session_id=request.session_id, operation_state='submitting')
    if fault == 'stale': hb['time'] = now.timestamp() - 46
    if fault == 'future': hb['time'] = now.timestamp() + 1
    if fault == 'actor': hb['actor'] = 'another-device'
    if fault == 'occurrence': hb.update(occurrence_id='0' * 64, monitored_occurrence_ids=[])
    if fault == 'policy': hb['policy_revision'] = 'old'
    if fault == 'uncertain': hb['operation_state'] = 'uncertain'
    if fault == 'session': hb['session_id'] = 'c' * 32
    if fault == 'protocol': hb['protocol'] = 1
    await store.put('heartbeat:omm_one', hb)
    if fault == 'missing': await store.cache.delete('rooms:usage:v1:heartbeat:omm_one')
    if fault == 'revoked': await store.cache.delete('rooms:usage:v1:credential:omm_one')
    with pytest.raises(AppError):
        await service.command(store, 'omm_one', actor, request, 'confirm', now)
    assert (await store.get(key))['state'] == ('pending' if fault == 'not_blocked' else 'blocked')


@pytest.mark.asyncio
async def test_confirmed_retry_after_restart_is_read_only(setup_usage):
    store, _, _, actor, _, now, _, _ = setup_usage
    request = await support.request_for(store, now)
    await service.command(store, 'omm_one', actor, request, 'confirm', now)
    key = 'record:' + request.occurrence_id
    before = await store.get(key)
    request.session_id = 'b' * 32
    assert (await service.command(store, 'omm_one', actor, request, 'confirm', now))['record']['state'] == 'confirmed'
    assert await store.get(key) == before
