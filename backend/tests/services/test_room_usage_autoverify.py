"""Automatic qualification follows fresh calendar evidence, never an old check-in."""
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.schemas.room_usage import Occurrence
from app.services import room_usage as service
from app.services import room_usage_worker as worker
from tests.services import test_room_usage as support

redis_socket = support.redis_socket
setup_usage = support.setup_usage


def detail(occ, **extra):
    return {'event_id': occ.uid + '_0', 'status': 'confirmed', 'is_exception': False,
            'recurrence': '', 'start_time': {'timestamp': str(occ.start_time.timestamp())},
            'end_time': {'timestamp': str(occ.end_time.timestamp())}, **extra}


def enable(monkeypatch):
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_AUTO_VERIFY_CALENDARS', {'omm_one': 'test-calendar'})
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_WRITES_ENABLED', True)


async def auto_policy(store, policy):
    policy.update(mode='auto', native_policy_cleared=True, release_verified=True)
    await store.put('policy:omm_one', policy)
    await store.put('paused', False)


@pytest.mark.asyncio
async def test_signed_booking_moved_requalifies_without_inheriting_confirmation(setup_usage, monkeypatch):
    store, client, _, actor, policy, now, snapshot, epoch = setup_usage
    enable(monkeypatch)
    request = await support.request_for(store, now)
    await service.command(store, 'omm_one', actor, request, 'confirm', now)
    await auto_policy(store, policy)
    moved = snapshot.events[0].model_copy(update={
        'start_time': now + timedelta(minutes=2), 'end_time': now + timedelta(minutes=20)})
    snapshot.events = [moved]
    await store.put('heartbeat:omm_one', support.health(actor, policy, snapshot, now))
    client.calendar_event = AsyncMock(return_value=detail(moved))
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    await worker.tick_room(store, client, 'omm_one', epoch, now + timedelta(seconds=2))
    ident = Occurrence.model_validate(moved.model_dump()).identity('omm_one')
    record = await store.get('record:' + ident)
    assert record['state'] == 'pending'
    assert record['verified'] is True
    assert record['release_scope'] == 'non_recurring'
    assert record['verification_source'] == 'calendar'
    assert (await store.get('record:' + request.occurrence_id))['state'] == 'confirmed'
    client.release.assert_not_called()


@pytest.mark.asyncio
async def test_disabled_mapping_never_auto_approves(setup_usage):
    store, client, _, _, _, now, _, epoch = setup_usage
    request = await support.request_for(store, now)
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    assert not (await store.get('record:' + request.occurrence_id))['verified']
    client.calendar_event.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', ['cancelled', 'changed', 'wrong_uid', 'incomplete', 'exception', 'denied'])
async def test_invalid_metadata_cannot_approve(setup_usage, monkeypatch, bad):
    store, client, _, _, policy, now, snapshot, epoch = setup_usage
    enable(monkeypatch)
    await auto_policy(store, policy)
    data = detail(snapshot.events[0])
    if bad == 'cancelled': data['status'] = 'cancelled'
    if bad == 'changed': data['start_time'] = {'timestamp': '1'}
    if bad == 'wrong_uid': data['event_id'] = 'another_0'
    if bad == 'incomplete': data.pop('is_exception')
    if bad == 'exception': data['is_exception'] = True
    client.calendar_event = AsyncMock(return_value=data)
    if bad == 'denied': client.calendar_event.side_effect = PermissionError('fixture')
    request = await support.request_for(store, now)
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    record = await store.get('record:' + request.occurrence_id)
    assert record['state'] == 'pending'
    assert not record['verified']
    client.release.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('condition', ['blocked', 'paused', 'official', 'not_allowlisted'])
async def test_protection_cannot_be_reset(setup_usage, monkeypatch, condition):
    store, client, _, _, policy, now, snapshot, epoch = setup_usage
    enable(monkeypatch)
    await auto_policy(store, policy)
    request = await support.request_for(store, now)
    key = 'record:' + request.occurrence_id
    if condition == 'blocked':
        old = await store.get(key)
        await store.put(key, {**old, 'state': 'blocked', 'reason': 'monitoring_interrupted'})
    if condition == 'paused': await store.put('paused', True)
    if condition == 'official': await store.put('policy:omm_one', {**policy, 'owner': 'official', 'mode': 'off'})
    if condition == 'not_allowlisted': monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_RELEASE_ROOM_IDS', set())
    client.calendar_event = AsyncMock(return_value=detail(snapshot.events[0]))
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    assert not (await store.get(key))['verified']
    client.calendar_event.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('recurrence', ['FREQ=WEEKLY', 'FREQ=MONTHLY'])
async def test_single_visible_series_instance_uses_authoritative_id(setup_usage, monkeypatch, recurrence):
    from app.services.room_usage_autoverify import calendar_qualification

    _, client, _, _, _, _, snapshot, _ = setup_usage
    enable(monkeypatch)
    occ = Occurrence.model_validate(snapshot.events[0].model_dump())
    original = int(occ.start_time.timestamp())
    client.calendar_event = AsyncMock(return_value=detail(occ, recurrence=recurrence))
    client.calendar_instances = AsyncMock(return_value=[detail(occ, event_id=f'{occ.uid}_{original}')])
    result = await calendar_qualification(client, 'omm_one', occ)
    assert result['release_scope'] == 'recurring_instance'
    assert result['release_original_time'] == original


@pytest.mark.asyncio
async def test_moved_exception_keeps_original_instance_time(setup_usage, monkeypatch):
    from app.services.room_usage_autoverify import calendar_qualification

    _, client, _, _, _, _, snapshot, _ = setup_usage
    enable(monkeypatch)
    occ = Occurrence.model_validate(snapshot.events[0].model_dump()).model_copy(update={'original_time': 1770000000})
    client.calendar_event = AsyncMock(return_value=detail(
        occ, event_id=f'{occ.uid}_{occ.original_time}', is_exception=True, recurring_event_id=occ.uid + '_0'))
    result = await calendar_qualification(client, 'omm_one', occ)
    assert result['release_original_time'] == 1770000000


@pytest.mark.asyncio
@pytest.mark.parametrize('condition', ['ok', 'changed', 'mapping_removed', 'mapping_changed'])
async def test_dispatch_revalidates_calendar_metadata(setup_usage, monkeypatch, condition):
    from app.services.room_usage_autoverify import calendar_qualification

    store, client, key, old, _, now, snapshot, epoch = await support.make_due(setup_usage, monkeypatch)
    enable(monkeypatch)
    occ = Occurrence.model_validate(snapshot.events[0].model_dump())
    client.calendar_event = AsyncMock(return_value=detail(occ))
    old.update(await calendar_qualification(client, 'omm_one', occ))
    await store.put(key, old)
    await store.cache.set('rooms:snapshot:omm_one', snapshot.model_dump_json())
    client.freebusy.side_effect = [
        {'free_busy': {'omm_one': [occ.model_dump(mode='json')]}}, {'free_busy': {'omm_one': []}}]
    if condition == 'changed': client.calendar_event.return_value = detail(occ, recurrence='FREQ=DAILY')
    if condition == 'mapping_removed': monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_AUTO_VERIFY_CALENDARS', {})
    if condition == 'mapping_changed': monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_AUTO_VERIFY_CALENDARS', {'omm_one': 'other'})
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    assert (await store.get(key))['state'] == ('released' if condition == 'ok' else 'blocked')
    assert client.release.await_count == (1 if condition == 'ok' else 0)


@pytest.mark.asyncio
async def test_calendar_nonrecurring_claim_cannot_override_busy_series_evidence(setup_usage, monkeypatch):
    from app.services.room_usage_autoverify import calendar_qualification

    store, client, key, old, _, now, snapshot, epoch = await support.make_due(setup_usage, monkeypatch)
    enable(monkeypatch)
    occ = Occurrence.model_validate(snapshot.events[0].model_dump())
    client.calendar_event = AsyncMock(return_value=detail(occ))
    old.update(await calendar_qualification(client, 'omm_one', occ))
    await store.put(key, old)
    later = occ.model_copy(update={'start_time': occ.start_time + timedelta(days=1), 'end_time': occ.end_time + timedelta(days=1)})
    client.freebusy.return_value = {'free_busy': {'omm_one': [occ.model_dump(mode='json'), later.model_dump(mode='json')]}}
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    assert (await store.get(key))['state'] == 'blocked'
    client.release.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('sign_again', [True, False])
async def test_moved_signed_meeting_full_automatic_lifecycle(setup_usage, monkeypatch, sign_again):
    from datetime import datetime

    store, client, _, actor, policy, now, snapshot, epoch = setup_usage
    enable(monkeypatch)
    old_request = await support.request_for(store, now)
    await service.command(store, 'omm_one', actor, old_request, 'confirm', now)
    policy['grace_minutes'] = 1
    await auto_policy(store, policy)
    moved = snapshot.events[0].model_copy(update={'start_time': now + timedelta(minutes=2), 'end_time': now + timedelta(minutes=20)})
    snapshot.events = [moved]
    client.calendar_event = AsyncMock(return_value=detail(moved))
    client.freebusy.side_effect = [{'free_busy': {'omm_one': [moved.model_dump(mode='json')]}}, {'free_busy': {'omm_one': []}}]
    ident = Occurrence.model_validate(moved.model_dump()).identity('omm_one')
    at = now

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return at

    monkeypatch.setattr(worker, 'datetime', Clock)
    for second in range(0, 271, 10):
        at = now + timedelta(seconds=second)
        await store.put('heartbeat:omm_one', support.health(actor, policy, snapshot, at))
        await worker.tick_room(store, client, 'omm_one', epoch, at)
        record = await store.get('record:' + ident)
        if sign_again and second == 140:
            request = await support.request_for(store, at)
            await service.command(store, 'omm_one', actor, request, 'confirm', at)
        if record['state'] == 'checking':
            await store.put('record:' + ident, {**record, 'ack_at': at.timestamp()})
    record = await store.get('record:' + ident)
    assert record['state'] == ('confirmed' if sign_again else 'released')
    assert client.release.await_count == (0 if sign_again else 1)
    assert (await store.get('record:' + old_request.occurrence_id))['state'] == 'confirmed'


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['confirm', 'offline', 'reschedule', 'pause'])
async def test_calendar_read_cannot_override_changed_admission(setup_usage, monkeypatch, change):
    store, client, _, actor, policy, now, snapshot, epoch = setup_usage
    enable(monkeypatch)
    await auto_policy(store, policy)
    request = await support.request_for(store, now)
    event = detail(snapshot.events[0])

    async def racing_read(*args):
        if change == 'confirm':
            await service.command(store, 'omm_one', actor, request, 'confirm', now)
        if change == 'offline':
            await store.put('heartbeat:omm_one', {})
        if change == 'reschedule':
            snapshot.events[0].start_time += timedelta(minutes=1)
        if change == 'pause':
            await store.put('paused', True)
        return event

    client.calendar_event = AsyncMock(side_effect=racing_read)
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    record = await store.get('record:' + request.occurrence_id)
    assert record['verified'] is False
    assert record['state'] == ('confirmed' if change == 'confirm' else 'pending')
    client.release.assert_not_called()


@pytest.mark.asyncio
async def test_calendar_read_must_not_outlive_terminal_release_ack(setup_usage, monkeypatch):
    from datetime import datetime

    from app.services.room_usage_autoverify import calendar_qualification

    store, client, key, old, _, now, snapshot, epoch = await support.make_due(setup_usage, monkeypatch)
    enable(monkeypatch)
    occ = Occurrence.model_validate(snapshot.events[0].model_dump())
    client.calendar_event = AsyncMock(return_value=detail(occ))
    old.update(await calendar_qualification(client, 'omm_one', occ))
    await store.put(key, old)
    at = now

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return at

    async def slow_read(*args):
        nonlocal at
        at = now + timedelta(seconds=20)
        return detail(occ)

    monkeypatch.setattr(worker, 'datetime', Clock)
    client.calendar_event = AsyncMock(side_effect=slow_read)
    client.freebusy.return_value = {'free_busy': {'omm_one': [occ.model_dump(mode='json')]}}
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    assert (await store.get(key))['state'] == 'blocked'
    client.release.assert_not_called()
