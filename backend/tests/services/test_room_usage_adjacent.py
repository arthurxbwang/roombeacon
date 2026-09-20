"""Adjacent bookings retain independent monitoring and failure protection."""
from datetime import timedelta

import pytest

from app.core.exceptions import AppError
from app.schemas.meeting_room import RoomEvent
from app.schemas.room_usage import TerminalCommand, UsageHeartbeat
from app.services import room_usage as service
from app.services import room_usage_worker as worker
from app.services.room_usage_health import heartbeat
from tests.services import test_room_usage as support

redis_socket = support.redis_socket
setup_usage = support.setup_usage


async def adjacent(setup, prior='confirmed'):
    store, _, _, _, _, now, snapshot, _ = setup
    old = (await service.view(store, 'omm_one', now))['record']
    snapshot.events[0].end_time = now + timedelta(minutes=2)
    snapshot.events.append(RoomEvent(uid='next-booking', original_time=0,
                                    start_time=now + timedelta(minutes=2), end_time=now + timedelta(minutes=17)))
    snapshot.valid_until = now + timedelta(minutes=30)
    first, following = [worker.Occurrence.model_validate(e.model_dump()) for e in snapshot.events]
    first_id, next_id = first.identity('omm_one'), following.identity('omm_one')
    await store.put('record:' + first_id, {**old, 'id': first_id, 'occurrence': first.model_dump(mode='json'),
                                         'state': prior, 'session_id': 'a' * 32, 'last_seen': now.timestamp()})
    return first_id, next_id


def report(policy, current, following, operation='ready'):
    return UsageHeartbeat(protocol=2, session_id='a' * 32, occurrence_id=current,
                          monitored_occurrence_ids=list(dict.fromkeys([current, following])),
                          policy_revision=policy['revision'], operation_state=operation)


@pytest.mark.asyncio
@pytest.mark.parametrize('prior', ['confirmed', 'blocked', 'pending'])
async def test_next_monitored_while_current_retained(setup_usage, prior):
    store, client, _, actor, policy, now, snapshot, epoch = setup_usage
    first, second = await adjacent(setup_usage, prior)
    state = await service.view(store, 'omm_one', now)
    assert state['target_id'] == first
    assert state['monitored_occurrence_ids'] == [first, second]
    await heartbeat(store, 'omm_one', actor, report(policy, first, second), now)
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    assert (await store.get('record:' + second))['state'] == 'pending'
    for seconds in range(20, 141, 20):
        at = now + timedelta(seconds=seconds)
        target = first if at < snapshot.events[1].start_time else second
        await heartbeat(store, 'omm_one', actor, report(policy, target, second), at)
        await worker.tick_room(store, client, 'omm_one', epoch, at)
    assert (await store.get('record:' + second))['state'] == 'pending'
    assert (await store.get('record:' + first))['state'] == prior
    client.release.assert_not_called()


@pytest.mark.asyncio
async def test_confirming_current_does_not_confirm_or_block_next(setup_usage):
    store, client, _, actor, policy, now, _, epoch = setup_usage
    first, second = await adjacent(setup_usage, 'pending')
    await heartbeat(store, 'omm_one', actor, report(policy, first, second), now)
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    await heartbeat(store, 'omm_one', actor, report(policy, first, second, 'submitting'), now)
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    await service.command(store, 'omm_one', actor, TerminalCommand(
        occurrence_id=first, policy_revision=policy['revision'], session_id='a' * 32), 'confirm', now)
    assert (await store.get('record:' + first))['state'] == 'confirmed'
    assert (await store.get('record:' + second))['state'] == 'pending'
    assert not (await store.get('record:' + second))['verified']
    client.release.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['offline', 'uncertain', 'session', 'restart', 'omitted'])
async def test_next_keeps_failure_protection(setup_usage, fault):
    store, client, _, actor, policy, now, _, epoch = setup_usage
    first, second = await adjacent(setup_usage)
    await heartbeat(store, 'omm_one', actor, report(policy, first, second), now)
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    at = now + timedelta(seconds=2)
    if fault == 'offline':
        await store.cache.delete(worker.PREFIX + 'heartbeat:omm_one')
    elif fault == 'restart':
        epoch = 'new-epoch'
    elif fault == 'uncertain':
        await heartbeat(store, 'omm_one', actor, report(policy, first, second, 'uncertain'), at)
    else:
        hb = await store.get('heartbeat:omm_one')
        hb.update({'session_id': 'b' * 32} if fault == 'session' else {'monitored_occurrence_ids': [first]})
        await store.put('heartbeat:omm_one', hb)
    await worker.tick_room(store, client, 'omm_one', epoch, at)
    assert (await store.get('record:' + second))['state'] == 'blocked'
    await store.cache.delete(worker.PREFIX + 'heartbeat:omm_one')
    await heartbeat(store, 'omm_one', actor, report(policy, first, second), at)
    await worker.tick_room(store, client, 'omm_one', epoch, at)
    assert (await store.get('record:' + second))['state'] == 'blocked'
    client.release.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['cross_room', 'deleted', 'rescheduled', 'overlap', 'outside_window'])
async def test_cannot_report_stale_or_unrelated_upcoming(setup_usage, change):
    store, client, _, actor, policy, now, snapshot, _ = setup_usage
    first, second = await adjacent(setup_usage)
    request = report(policy, first, second)
    if change == 'cross_room': request.monitored_occurrence_ids = [first, 'f' * 64]
    if change == 'deleted': snapshot.events.pop()
    if change == 'rescheduled': snapshot.events[1].end_time += timedelta(minutes=1)
    if change == 'overlap': snapshot.events[1].start_time -= timedelta(seconds=1)
    if change == 'outside_window':
        snapshot.events[1].start_time += timedelta(minutes=10)
        snapshot.events[1].end_time += timedelta(minutes=10)
    previous = await store.get('heartbeat:omm_one')
    with pytest.raises(AppError):
        await heartbeat(store, 'omm_one', actor, request, now)
    assert await store.get('heartbeat:omm_one') == previous
    client.release.assert_not_called()


@pytest.mark.asyncio
async def test_legacy_heartbeat_does_not_implicitly_cover_next(setup_usage):
    store, client, _, actor, policy, now, snapshot, epoch = setup_usage
    first, second = await adjacent(setup_usage)
    old_client = UsageHeartbeat(protocol=2, session_id='a' * 32, occurrence_id=first,
                                policy_revision=policy['revision'], operation_state='ready')
    await heartbeat(store, 'omm_one', actor, old_client, now)
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    assert await store.get('record:' + second) is None
    old_client.occurrence_id = second
    await heartbeat(store, 'omm_one', actor, old_client, snapshot.events[1].start_time)
    await worker.tick_room(store, client, 'omm_one', epoch, snapshot.events[1].start_time)
    assert (await store.get('record:' + second))['state'] == 'blocked'
    client.release.assert_not_called()


@pytest.mark.asyncio
async def test_adjacent_no_show_releases_only_second_after_full_challenge(setup_usage, monkeypatch):
    from app.core.config import settings
    from app.schemas.room_usage import VerifiedOccurrence

    store, client, _, actor, policy, now, snapshot, epoch = setup_usage
    first, second = await adjacent(setup_usage)
    policy.update(mode='auto', grace_minutes=1, native_policy_cleared=True, release_verified=True)
    await store.put('policy:omm_one', policy)
    await store.put('paused', False)
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_WRITES_ENABLED', True)
    later = RoomEvent(uid='later-untouched', original_time=0, start_time=now + timedelta(minutes=20),
                      end_time=now + timedelta(minutes=35))
    snapshot.events.append(later)
    client.freebusy.side_effect = [
        {'free_busy': {'omm_one': [snapshot.events[1].model_dump(mode='json'), later.model_dump(mode='json')]}},
        {'free_busy': {'omm_one': [later.model_dump(mode='json')]}},
    ]
    at = now
    class Clock:
        @staticmethod
        def now(tz):
            return at
    monkeypatch.setattr(worker, 'datetime', Clock)
    # view/verify also need fromisoformat, while sharing the injected test clock.
    from datetime import datetime
    Clock.fromisoformat = staticmethod(datetime.fromisoformat)
    monkeypatch.setattr(service, 'datetime', Clock)
    for seconds in range(0, 271, 5):
        at = now + timedelta(seconds=seconds)
        current = first if seconds < 120 else second
        request = report(policy, current, second)
        record = await store.get('record:' + second)
        if record and record['state'] == 'checking':
            request.challenge_id = record['challenge_id']
        await heartbeat(store, 'omm_one', actor, request, at)
        if seconds == 120:
            await service.verify_occurrence(store, 'omm_one', VerifiedOccurrence(
                occurrence_id=second, policy_revision=policy['revision'], non_recurring_verified=True))
        await worker.tick_room(store, client, 'omm_one', epoch, at)
    assert (await store.get('record:' + first))['state'] == 'confirmed'
    assert (await store.get('record:' + second))['state'] == 'released'
    client.release.assert_awaited_once()
    assert client.release.await_args.args[1].identity('omm_one') == second
    assert client.release.await_args.args[2] == 'NOT_CHECK_IN'
    assert await store.get('record:' + worker.Occurrence.model_validate(later.model_dump()).identity('omm_one')) is None


@pytest.mark.asyncio
async def test_slow_current_preflight_cannot_backdate_next_enrollment(setup_usage, monkeypatch):
    from datetime import datetime

    store, client, _, actor, policy, now, snapshot, _ = setup_usage
    first, second = await adjacent(setup_usage)
    from app.core.config import settings
    policy.update(mode='auto', native_policy_cleared=True, release_verified=True)
    await store.put('policy:omm_one', policy)
    await store.put('paused', False)
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_WRITES_ENABLED', True)
    old = await store.get('record:' + first)
    old.update(state='checking', verified=True, ack_at=now.timestamp(), challenge_started=now.timestamp(),
               challenge_expires=now.timestamp() + 15, challenge_id='c' * 32)
    await store.put('record:' + first, old)
    await heartbeat(store, 'omm_one', actor, report(policy, first, second), now)
    current = now
    class Clock(datetime):
        @classmethod
        def now(cls, tz):
            return current
    async def slow_preflight(*args):
        nonlocal current
        current = now + timedelta(minutes=2, seconds=1)
        return {'free_busy': {'omm_one': [e.model_dump(mode='json') for e in snapshot.events]}}
    monkeypatch.setattr(worker, 'datetime', Clock)
    client.freebusy.side_effect = slow_preflight
    await worker.tick_room(store, client, 'omm_one', 'epoch1')
    assert (await store.get('record:' + second))['state'] == 'blocked'
    assert (await store.get('record:' + second))['reason'] == 'missed_window'
    client.release.assert_not_called()
