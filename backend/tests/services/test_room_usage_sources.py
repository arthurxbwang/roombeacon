"""Different organizers must qualify their own bookings without room remapping."""
import hashlib
import json
from datetime import timedelta
from unittest.mock import AsyncMock

import httpx
import pytest

from app.connectors.feishu.calendar_errors import CalendarEvidenceError
from app.core.config import settings
from app.core.exceptions import AppError
from app.schemas.room_usage import Occurrence
from app.services import room_usage as service
from app.services import room_usage_worker as worker
from app.services.room_usage_autoverify import calendar_qualification
from app.services.room_usage_store import PREFIX
from tests.services import test_room_usage as support
from tests.services.test_room_usage_autoverify import auto_policy, detail, enable

redis_socket = support.redis_socket
setup_usage = support.setup_usage


def app_scope():
    return hashlib.sha256((settings.FEISHU_APP_ID + '\0' + settings.FEISHU_APP_SECRET).encode()).hexdigest()


async def source_setup(setup, monkeypatch, organizer='ou_new'):
    store, client, _, _, policy, _, snapshot, _ = setup
    enable(monkeypatch)
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_ORGANIZER_SOURCE_ROOM_IDS', {'omm_one'})
    await auto_policy(store, policy)
    occurrence = Occurrence.model_validate(snapshot.events[0].model_dump())
    ident = occurrence.identity('omm_one')
    await store.cache.set('rooms:snapshot:omm_one', snapshot.model_dump_json())
    await store.put('sources:omm_one', {
        'app_scope': app_scope(), 'snapshot_at': snapshot.synced_at.isoformat(),
        'valid_until': snapshot.valid_until.isoformat(), 'organizers': {ident: organizer},
    })
    client.primary_calendars = AsyncMock(return_value={organizer: 'calendar-' + organizer} if organizer else {})

    async def lookup(calendar, event_id):
        if calendar == 'test-calendar':
            response = httpx.Response(404, json={'code': 193001}, request=httpx.Request('GET', 'https://fixture'))
            response.raise_for_status()
        assert calendar == 'calendar-' + organizer
        return detail(occurrence, organizer_calendar_id=calendar)

    client.calendar_event = AsyncMock(side_effect=lookup)
    return occurrence, ident


@pytest.mark.asyncio
@pytest.mark.parametrize('organizer', ['ou_employee_a', 'ou_employee_b', 'ou_first_time_c'])
async def test_different_organizers_qualify_without_changing_room_mapping(setup_usage, monkeypatch, organizer):
    store, client, _, _, _, now, _, epoch = setup_usage
    _, ident = await source_setup(setup_usage, monkeypatch, organizer)
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    record = await store.get('record:' + ident)
    assert record['verified'] is True
    assert record['verification_calendar'] == hashlib.sha256(('calendar-' + organizer).encode()).hexdigest()
    assert settings.ROOM_DISPLAY_USAGE_AUTO_VERIFY_CALENDARS == {'omm_one': 'test-calendar'}
    client.release.assert_not_called()
    public = json.dumps(await service.view(store, 'omm_one', now))
    assert organizer not in public and 'calendar-' + organizer not in public
    raw_snapshot = await store.cache.get('rooms:snapshot:omm_one')
    assert organizer not in raw_snapshot
    assert await store.cache.exists(PREFIX + 'sources:omm_one')


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', ['missing', 'stale', 'snapshot_changed', 'app_changed', 'removed', 'overlap'])
async def test_incomplete_or_stale_source_evidence_cannot_qualify(setup_usage, monkeypatch, bad):
    store, client, _, _, _, now, snapshot, epoch = setup_usage
    _, ident = await source_setup(setup_usage, monkeypatch)
    if bad == 'missing': await store.cache.delete(PREFIX + 'sources:omm_one')
    if bad == 'stale': snapshot.valid_until = now
    if bad == 'snapshot_changed': snapshot.synced_at += timedelta(seconds=1)
    if bad == 'app_changed': monkeypatch.setattr(settings, 'FEISHU_APP_SECRET', 'rotated-test-secret')
    if bad == 'removed': snapshot.events = []
    if bad == 'overlap': snapshot.events.append(snapshot.events[0].model_copy(update={'uid': 'overlap'}))
    if bad in {'stale', 'overlap'}:
        with pytest.raises(AppError):
            await worker.tick_room(store, client, 'omm_one', epoch, now)
    else:
        await worker.tick_room(store, client, 'omm_one', epoch, now)
    assert not (await store.get('record:' + ident))['verified']
    client.primary_calendars.assert_not_called()
    client.release.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', ['foreign_event', 'wrong_time', 'missing_authority', 'authority_cycle', 'conflicting_sources'])
async def test_candidate_200_must_prove_unique_authoritative_source(setup_usage, monkeypatch, bad):
    store, client, _, _, _, now, _, epoch = setup_usage
    occ, ident = await source_setup(setup_usage, monkeypatch)

    async def lookup(calendar, event_id):
        data = detail(occ, organizer_calendar_id=calendar)
        if bad == 'foreign_event': data['event_id'] = 'other_0'
        if bad == 'wrong_time': data['end_time'] = {'timestamp': '1'}
        if bad == 'missing_authority': data.pop('organizer_calendar_id')
        if bad == 'authority_cycle': data['organizer_calendar_id'] = 'cycle' if calendar != 'cycle' else 'calendar-ou_new'
        return data

    client.calendar_event.side_effect = lookup
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    record = await store.get('record:' + ident)
    assert not record['verified'] and record['verification_error']
    client.release.assert_not_called()
    assert client.calendar_event.await_count <= 6


@pytest.mark.asyncio
async def test_primary_candidate_follows_shared_authority_and_deduplicates_lookup(setup_usage, monkeypatch):
    store, client, _, _, _, now, _, _ = setup_usage
    occ, _ = await source_setup(setup_usage, monkeypatch)
    client.calendar_event.side_effect = lambda calendar, event_id: detail(occ, organizer_calendar_id='shared-authority')
    for _ in range(2):
        result = await calendar_qualification(client, 'omm_one', occ, store=store, now=now)
        assert result['_calendar_source']['calendar'] == 'shared-authority'
    client.primary_calendars.assert_awaited_once()


@pytest.mark.asyncio
async def test_dynamic_source_does_not_require_fixed_personal_calendar(setup_usage, monkeypatch):
    store, _, _, _, _, now, _, epoch = setup_usage
    _, ident = await source_setup(setup_usage, monkeypatch)
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_AUTO_VERIFY_CALENDARS', {})
    await worker.tick_room(store, setup_usage[1], 'omm_one', epoch, now)
    assert (await store.get('record:' + ident))['verified']
    assert (await service.view(store, 'omm_one', now))['auto_verify_enabled']


@pytest.mark.asyncio
async def test_missing_organizer_uses_only_explicit_fixed_source(setup_usage, monkeypatch):
    store, client, _, _, _, now, _, _ = setup_usage
    occ, _ = await source_setup(setup_usage, monkeypatch, None)
    client.calendar_event.side_effect = lambda calendar, event_id: detail(occ, organizer_calendar_id='test-calendar')
    result = await calendar_qualification(client, 'omm_one', occ, store=store, now=now)
    assert result['_calendar_source']['organizer'] is None
    client.primary_calendars.assert_not_called()
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_AUTO_VERIFY_CALENDARS', {})
    with pytest.raises(CalendarEvidenceError, match='source_unresolved'):
        await calendar_qualification(client, 'omm_one', occ, store=store, now=now)


@pytest.mark.asyncio
async def test_negative_cache_bounds_wrong_source_reads(setup_usage, monkeypatch):
    store, client, _, _, _, now, _, _ = setup_usage
    occ, _ = await source_setup(setup_usage, monkeypatch)
    for _ in range(4):
        await calendar_qualification(client, 'omm_one', occ, store=store, now=now)
    assert sum(call.args[0] == 'test-calendar' for call in client.calendar_event.await_args_list) == 1
    client.primary_calendars.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['organizer', 'configuration', 'credential'])
async def test_source_change_during_read_cannot_publish_qualification(setup_usage, monkeypatch, change):
    store, client, _, _, _, now, _, epoch = setup_usage
    occ, ident = await source_setup(setup_usage, monkeypatch)
    async def changed(calendar, event_id):
        if change == 'organizer':
            evidence = await store.get('sources:omm_one')
            evidence['organizers'][ident] = 'ou_changed'
            await store.put('sources:omm_one', evidence)
        if change == 'configuration': monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_AUTO_VERIFY_CALENDARS', {})
        if change == 'credential': monkeypatch.setattr(settings, 'FEISHU_APP_SECRET', 'rotated')
        return detail(occ, organizer_calendar_id='calendar-ou_new')
    client.calendar_event.side_effect = changed
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    assert not (await store.get('record:' + ident))['verified']
    client.release.assert_not_called()


@pytest.mark.asyncio
async def test_error_visible_before_deadline_retained_after_and_cleared_only_on_success(setup_usage, monkeypatch):
    store, client, _, actor, policy, now, snapshot, epoch = setup_usage
    occ, ident = await source_setup(setup_usage, monkeypatch)
    client.calendar_event.side_effect = CalendarEvidenceError('access_denied', http_status=403, code=191002)
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    failed = await store.get('record:' + ident)
    assert failed['state'] == 'pending' and failed['verification_error'] == 'access_denied'
    assert (await store.audit('omm_one'))[0]['verification_error'] == 'access_denied'
    client.calendar_event.side_effect = lambda cal, eid: detail(occ, organizer_calendar_id='calendar-ou_new')
    at = now + timedelta(seconds=31)
    await store.put('heartbeat:omm_one', support.health(actor, policy, snapshot, at))
    await worker.tick_room(store, client, 'omm_one', epoch, at)
    fixed = await store.get('record:' + ident)
    assert fixed['verified'] and fixed['verification_error'] is None and fixed['verification_succeeded_at']
    # A failed pending instance reaches an explicit reason at its fixed deadline.
    await store.put('record:' + ident, {**failed, 'deadline': at.isoformat(), 'last_seen': at.timestamp()})
    await worker.tick_room(store, client, 'omm_one', epoch, at)
    assert (await store.get('record:' + ident))['reason'] == 'calendar_verification_failed'
