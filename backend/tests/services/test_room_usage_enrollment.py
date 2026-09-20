"""A newly collected booking waits for its own page heartbeat before enrollment."""
from datetime import timedelta

import pytest

from app.schemas.room_usage import UsageHeartbeat
from app.services import room_usage_worker as worker
from app.services.room_usage_health import heartbeat
from tests.services import test_room_usage as support

redis_socket = support.redis_socket
setup_usage = support.setup_usage


def new_occurrence(setup):
    now, snapshot = setup[5:7]
    snapshot.events[0].uid = 'newly-synced'
    snapshot.events[0].start_time = now + timedelta(minutes=3)
    snapshot.events[0].end_time = now + timedelta(minutes=30)
    snapshot.synced_at = now
    occurrence = worker.Occurrence.model_validate(snapshot.events[0].model_dump())
    return occurrence.identity('omm_one')


@pytest.mark.asyncio
@pytest.mark.parametrize('prior_health', ['old_occurrence', 'missing', 'stale', 'uncertain'])
async def test_new_booking_waits_for_its_own_heartbeat(setup_usage, prior_health):
    store, client, _, actor, policy, now, _snapshot, epoch = setup_usage
    ident = new_occurrence(setup_usage)
    old_hb = await store.get('heartbeat:omm_one')
    if prior_health == 'missing':
        await store.cache.delete(worker.PREFIX + 'heartbeat:omm_one')
    elif prior_health == 'stale':
        await store.put('heartbeat:omm_one', {**old_hb, 'time': now.timestamp() - 60})
    elif prior_health == 'uncertain':
        await store.put('heartbeat:omm_one', {**old_hb, 'operation_state': 'uncertain'})
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    assert await store.get('record:' + ident) is None
    assert not await store.cache.exists(worker.PREFIX + 'seen:' + ident)
    report = UsageHeartbeat(protocol=2, session_id='a' * 32, occurrence_id=ident,
                            policy_revision=policy['revision'], operation_state='ready')
    await heartbeat(store, 'omm_one', actor, report, now + timedelta(seconds=10))
    await worker.tick_room(store, client, 'omm_one', epoch, now + timedelta(seconds=10))
    assert (await store.get('record:' + ident))['state'] == 'pending'
    await worker.tick_room(store, client, 'omm_one', epoch, now + timedelta(seconds=12))
    assert (await store.get('record:' + ident))['state'] == 'pending'
    client.release.assert_not_called()


@pytest.mark.asyncio
async def test_missing_heartbeat_at_start_still_blocks_and_never_recovers(setup_usage):
    store, client, _, actor, policy, _now, snapshot, epoch = setup_usage
    ident = new_occurrence(setup_usage)
    await store.cache.delete(worker.PREFIX + 'heartbeat:omm_one')
    start = snapshot.events[0].start_time
    await worker.tick_room(store, client, 'omm_one', epoch, start)
    record = await store.get('record:' + ident)
    assert record['state'] == 'blocked' and record['reason'] == 'missed_window'
    await store.put('heartbeat:omm_one', support.health(actor, policy, snapshot, start))
    await worker.tick_room(store, client, 'omm_one', epoch, start + timedelta(seconds=2))
    assert (await store.get('record:' + ident))['state'] == 'blocked'
    client.release.assert_not_called()
