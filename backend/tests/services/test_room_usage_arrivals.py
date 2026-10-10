"""Late additions get one fixed window, only after continuous complete observation."""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import AppError
from app.schemas.meeting_room import RoomEvent
from app.schemas.room_usage import TerminalCommand, UsageHeartbeat
from app.services import room_usage as service
from app.services import room_usage_worker as worker
from app.services.room_usage_health import heartbeat
from tests.services import test_room_usage as support
from tests.services.test_room_usage_autoverify import auto_policy, detail, enable

redis_socket = support.redis_socket
setup_usage = support.setup_usage


async def baseline(setup, monkeypatch):
    store, client, _, _actor, policy, now, original, epoch = setup
    policy.update(early_minutes=5, grace_minutes=5, release_delay_seconds=0)
    await store.put('policy:omm_one', policy)
    before = now - timedelta(seconds=20)
    snapshot = original.model_copy(update={
        'events': [], 'synced_at': before, 'valid_until': now + timedelta(minutes=10),
        'query_start': now - timedelta(days=1), 'query_end': now + timedelta(days=1),
    })
    monkeypatch.setattr(service, 'cached_schedule', AsyncMock(return_value=snapshot))
    hb = await store.get('heartbeat:omm_one')
    await store.put('heartbeat:omm_one', hb | {'time': before.timestamp(), 'occurrence_id': None})
    await worker.tick_room(store, client, 'omm_one', epoch, before)
    return snapshot


async def appear(setup, snapshot, age=600, at=None, matching=True):
    store, _, _, actor, policy, now, _, _ = setup
    at = at or now
    event = RoomEvent(uid='late-addition', start_time=at - timedelta(seconds=age),
                      end_time=at + timedelta(minutes=30))
    snapshot.events = [event]
    snapshot.synced_at = at
    snapshot.valid_until = at + timedelta(minutes=10)
    hb = support.health(actor, policy, snapshot, at)
    if not matching:
        hb['occurrence_id'] = None
    await store.put('heartbeat:omm_one', hb)
    return worker.Occurrence.model_validate(event.model_dump()).identity('omm_one')


@pytest.mark.asyncio
@pytest.mark.parametrize('age', [0, 120, 300, 600])
async def test_new_late_booking_has_fixed_five_minute_window(setup_usage, monkeypatch, age):
    store, client, _, _, _, now, _, epoch = setup_usage
    snapshot = await baseline(setup_usage, monkeypatch)
    ident = await appear(setup_usage, snapshot, age)
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    state = await service.view(store, 'omm_one', now)
    assert state['record']['state'] == 'pending'
    assert state['can_confirm']
    assert state['record']['deadline'] == (now + timedelta(minutes=5)).isoformat()
    await worker.tick_room(store, client, 'omm_one', epoch, now + timedelta(seconds=2))
    assert (await store.get('record:' + ident))['deadline'] == state['record']['deadline']
    client.release.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['restart', 'gap', 'offline', 'session', 'actor', 'policy',
                                  'missing_coverage', 'widened_query', 'stale_prior', 'future', 'same_snapshot'])
async def test_uncertain_history_cannot_arm_late_booking(setup_usage, monkeypatch, fault):
    store, client, _, _, policy, now, _, epoch = setup_usage
    snapshot = await baseline(setup_usage, monkeypatch)
    old = await store.get('observation:omm_one')
    if fault == 'widened_query':
        old['query_start'] = (now - timedelta(seconds=60)).timestamp()
    if fault == 'stale_prior': old['valid_until'] = now.timestamp()
    await store.put('observation:omm_one', old)
    await appear(setup_usage, snapshot)
    at = now + timedelta(seconds=46) if fault == 'gap' else now
    if fault == 'restart': epoch = 'restarted'
    if fault == 'offline': await store.cache.delete(worker.PREFIX + 'heartbeat:omm_one')
    if fault in {'session', 'actor'}:
        hb = await store.get('heartbeat:omm_one')
        hb['session_id' if fault == 'session' else 'actor'] = 'b' * 32
        await store.put('heartbeat:omm_one', hb)
    if fault == 'policy':
        policy['revision'] = 'changed'
        await store.put('policy:omm_one', policy)
    if fault == 'missing_coverage': snapshot.query_start = None
    if fault == 'future': snapshot.synced_at = now + timedelta(seconds=1)
    if fault == 'same_snapshot': snapshot.synced_at = now - timedelta(seconds=20)
    await worker.tick_room(store, client, 'omm_one', epoch, at)
    state = await service.view(store, 'omm_one', at)
    assert state['record']['state'] == 'blocked'
    assert not state['can_confirm']
    client.release.assert_not_called()


@pytest.mark.asyncio
async def test_expired_cache_breaks_observation_even_when_recovered_quickly(setup_usage, monkeypatch):
    store, client, _, _, _, now, _, epoch = setup_usage
    snapshot = await baseline(setup_usage, monkeypatch)
    snapshot.valid_until = now
    with pytest.raises(AppError):
        await worker.tick_room(store, client, 'omm_one', epoch, now)
    await appear(setup_usage, snapshot, at=now + timedelta(seconds=2))
    await worker.tick_room(store, client, 'omm_one', epoch, now + timedelta(seconds=2))
    assert (await service.view(store, 'omm_one', now + timedelta(seconds=2)))['record']['state'] == 'blocked'
    client.release.assert_not_called()


@pytest.mark.asyncio
async def test_wait_for_matching_page_does_not_move_deadline(setup_usage, monkeypatch):
    store, client, _, actor, policy, now, _, epoch = setup_usage
    snapshot = await baseline(setup_usage, monkeypatch)
    ident = await appear(setup_usage, snapshot, matching=False)
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    assert await store.get('record:' + ident) is None
    at = now + timedelta(seconds=20)
    await store.put('heartbeat:omm_one', support.health(actor, policy, snapshot, at))
    await worker.tick_room(store, client, 'omm_one', epoch, at)
    record = await store.get('record:' + ident)
    assert record['state'] == 'pending'
    assert record['first_observed_at'] == now.isoformat()
    assert record['deadline'] == (now + timedelta(minutes=5)).isoformat()


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['restart', 'lost_record', 'protected'])
async def test_enrolled_late_booking_never_rearms_after_fault(setup_usage, monkeypatch, fault):
    store, client, _, _, _, now, _, epoch = setup_usage
    snapshot = await baseline(setup_usage, monkeypatch)
    ident = await appear(setup_usage, snapshot)
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    record = await store.get('record:' + ident)
    if fault == 'restart': epoch = 'new-worker'
    if fault == 'lost_record': await store.cache.delete(worker.PREFIX + 'record:' + ident)
    if fault == 'protected': await store.put('record:' + ident, record | {'state': 'blocked'})
    await worker.tick_room(store, client, 'omm_one', epoch, now + timedelta(seconds=2))
    assert (await store.get('record:' + ident))['state'] == 'blocked'
    await worker.tick_room(store, client, 'omm_one', epoch, now + timedelta(seconds=4))
    assert (await store.get('record:' + ident))['state'] == 'blocked'
    client.release.assert_not_called()


@pytest.mark.asyncio
async def test_deleted_and_reappearing_addition_keeps_first_deadline(setup_usage, monkeypatch):
    store, client, _, _, _, now, _, epoch = setup_usage
    snapshot = await baseline(setup_usage, monkeypatch)
    ident = await appear(setup_usage, snapshot, matching=False)
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    event = snapshot.events[0]
    snapshot.events = []
    snapshot.synced_at = now + timedelta(seconds=2)
    await worker.tick_room(store, client, 'omm_one', epoch, now + timedelta(seconds=2))
    snapshot.events = [event]
    snapshot.synced_at = now + timedelta(seconds=4)
    await worker.tick_room(store, client, 'omm_one', epoch, now + timedelta(seconds=4))
    proof = await store.get('arrival:' + ident)
    assert proof['first_observed_at'] == now.isoformat()
    assert proof['deadline'] == (now + timedelta(minutes=5)).isoformat()


@pytest.mark.asyncio
async def test_window_never_outlives_booking(setup_usage, monkeypatch):
    store, client, _, actor, policy, now, _, epoch = setup_usage
    snapshot = await baseline(setup_usage, monkeypatch)
    await appear(setup_usage, snapshot)
    snapshot.events[0].end_time = now + timedelta(seconds=60)
    await store.put('heartbeat:omm_one', support.health(actor, policy, snapshot, now))
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    state = await service.view(store, 'omm_one', now)
    assert state['record']['deadline'] == snapshot.events[0].end_time.isoformat()


@pytest.mark.asyncio
async def test_first_snapshot_after_start_is_not_new_booking_evidence(setup_usage, monkeypatch):
    store, client, _, _, _, now, _, epoch = setup_usage
    snapshot = await baseline(setup_usage, monkeypatch)
    await store.cache.delete(worker.PREFIX + 'observation:omm_one')
    await appear(setup_usage, snapshot)
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    assert (await service.view(store, 'omm_one', now))['record']['state'] == 'blocked'
    client.release.assert_not_called()


@pytest.mark.asyncio
async def test_new_booking_before_start_keeps_original_deadline(setup_usage, monkeypatch):
    store, client, _, _, _, now, _, epoch = setup_usage
    snapshot = await baseline(setup_usage, monkeypatch)
    await appear(setup_usage, snapshot, age=-120)
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    state = await service.view(store, 'omm_one', now)
    assert state['record']['state'] == 'pending'
    assert state['record']['deadline'] == (now + timedelta(minutes=7)).isoformat()


@pytest.mark.asyncio
async def test_signed_booking_rescheduled_into_past_requires_new_checkin(setup_usage, monkeypatch):
    store, client, _, actor, policy, now, original, epoch = setup_usage
    request = await support.request_for(store, now)
    await service.command(store, 'omm_one', actor, request, 'confirm', now)
    snapshot = await baseline(setup_usage, monkeypatch)
    await appear(setup_usage, snapshot)
    snapshot.events[0].uid = original.events[0].uid
    await store.put('heartbeat:omm_one', support.health(actor, policy, snapshot, now))
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    state = await service.view(store, 'omm_one', now)
    assert state['record']['id'] != request.occurrence_id
    assert state['record']['state'] == 'pending' and state['can_confirm']
    assert not state['record']['verified']
    assert (await store.get('record:' + request.occurrence_id))['state'] == 'confirmed'
    client.release.assert_not_called()


@pytest.mark.asyncio
async def test_late_checkin_survives_polling_without_release(setup_usage, monkeypatch):
    store, client, _, actor, policy, now, _, epoch = setup_usage
    snapshot = await baseline(setup_usage, monkeypatch)
    ident = await appear(setup_usage, snapshot)
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    request = TerminalCommand(occurrence_id=ident, policy_revision=policy['revision'], session_id='a' * 32)
    state = await service.command(store, 'omm_one', actor, request, 'confirm', now + timedelta(seconds=10))
    assert state['record']['state'] == 'confirmed'
    await worker.tick_room(store, client, 'omm_one', epoch, now + timedelta(minutes=6))
    assert (await store.get('record:' + ident))['state'] == 'confirmed'
    client.release.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('calendar_ok', [True, False])
@pytest.mark.parametrize('recurring', [True, False])
async def test_late_no_show_uses_effective_deadline_and_all_release_checks(setup_usage, monkeypatch, calendar_ok, recurring):
    store, client, _, actor, policy, now, _, epoch = setup_usage
    snapshot = await baseline(setup_usage, monkeypatch)
    enable(monkeypatch)
    await auto_policy(store, policy)
    # Re-establish a baseline with the actual automatic policy.
    before = now - timedelta(seconds=10)
    hb = await store.get('heartbeat:omm_one')
    await store.put('heartbeat:omm_one', hb | {'time': before.timestamp()})
    await worker.tick_room(store, client, 'omm_one', epoch, before)
    ident = await appear(setup_usage, snapshot)
    event = snapshot.events[0]
    client.calendar_event.return_value = detail(event)
    later = event.model_copy(update={'start_time': event.start_time + timedelta(days=1),
                                    'end_time': event.end_time + timedelta(days=1)})
    if recurring:
        client.calendar_event.return_value = detail(event, recurrence='FREQ=DAILY')
        client.calendar_instances.return_value = [detail(event, event_id=f'{event.uid}_{int(event.start_time.timestamp())}')]
    if not calendar_ok: client.calendar_event.side_effect = PermissionError('fixture')
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    for seconds in range(20, 301, 20):
        at = now + timedelta(seconds=seconds)
        await store.put('heartbeat:omm_one', support.health(actor, policy, snapshot, at))
        await worker.tick_room(store, client, 'omm_one', epoch, at)
        client.release.assert_not_called()
    state = await service.view(store, 'omm_one', at)
    assert not state['can_confirm']
    assert state['record']['state'] == ('waiting' if calendar_ok else 'blocked')
    request = TerminalCommand(occurrence_id=ident, policy_revision=policy['revision'], session_id='a' * 32)
    with pytest.raises(AppError):
        await service.command(store, 'omm_one', actor, request, 'confirm', at)
    if not calendar_ok:
        return
    at += timedelta(seconds=2)
    await worker.tick_room(store, client, 'omm_one', epoch, at)
    record = await store.get('record:' + ident)
    assert record['state'] == 'checking'
    await heartbeat(store, 'omm_one', actor, UsageHeartbeat(
        protocol=2, session_id='a' * 32, occurrence_id=ident, policy_revision=policy['revision'],
        operation_state='ready', challenge_id=record['challenge_id']), at)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return at

    monkeypatch.setattr(worker, 'datetime', Clock)
    later_rows = [later.model_dump(mode='json')] if recurring else []
    client.freebusy.side_effect = [{'free_busy': {'omm_one': [event.model_dump(mode='json'), *later_rows]}},
                                 {'free_busy': {'omm_one': later_rows}}]
    await store.cache.set('rooms:snapshot:omm_one', snapshot.model_dump_json())
    await worker.tick_room(store, client, 'omm_one', epoch, at)
    assert (await store.get('record:' + ident))['state'] == 'released'
    await worker.tick_room(store, client, 'omm_one', epoch, at)
    client.release.assert_awaited_once()
    assert client.release.call_args.args[2] == 'NOT_CHECK_IN'
    assert client.release.call_args.args[1].original_time == (int(event.start_time.timestamp()) if recurring else 0)
