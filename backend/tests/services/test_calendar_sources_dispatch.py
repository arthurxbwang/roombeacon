"""Source changes during release preflight must never silently retarget a write."""
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from app.connectors.feishu.calendar_errors import CalendarEvidenceError
from app.core.config import settings
from app.services import room_usage_worker as worker
from app.services.room_usage_autoverify import calendar_qualification
from tests.services import test_room_usage as support
from tests.services.test_room_usage_autoverify import detail
from tests.services.test_room_usage_sources import source_setup

redis_socket = support.redis_socket
setup_usage = support.setup_usage


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['none', 'organizer', 'authority', 'disabled', 'mapping', 'late_config', 'denied', 'budget_timeout', 'malformed_instance'])
async def test_dispatch_rechecks_pinned_source_and_live_organizer(setup_usage, monkeypatch, change):
    store, client, _, _, _, now, _, _ = setup_usage
    occ, ident = await source_setup(setup_usage, monkeypatch)
    proof = await calendar_qualification(client, 'omm_one', occ, store=store, now=now)
    store, client, key, old, _, now, _, epoch = await support.make_due(setup_usage, monkeypatch)
    await store.put(key, {**old, **proof})
    row = {**occ.model_dump(mode='json'), 'organizer_info': {'open_id': 'ou_new'}}
    if change == 'organizer': row['organizer_info']['open_id'] = 'ou_other'
    if change == 'disabled': monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_ORGANIZER_SOURCE_ROOM_IDS', set())
    if change == 'mapping': monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_AUTO_VERIFY_CALENDARS', {})
    async def lookup(calendar, event_id):
        assert calendar == 'calendar-ou_new'
        if change == 'late_config': monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_AUTO_VERIFY_CALENDARS', {})
        if change == 'denied': raise CalendarEvidenceError('access_denied', http_status=403)
        return detail(occ, organizer_calendar_id='another-calendar' if change == 'authority' else calendar,
                      recurrence='FREQ=DAILY' if change == 'malformed_instance' else '')
    client.calendar_event.side_effect = lookup
    client.calendar_instances.return_value = [detail(occ, event_id='malformed')]
    if change == 'budget_timeout':
        monkeypatch.setattr('app.services.room_usage_autoverify.calendar_qualification', AsyncMock(side_effect=TimeoutError('private')))
    client.freebusy.side_effect = [{'free_busy': {'omm_one': [row]}}, {'free_busy': {'omm_one': []}}]
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    record = await store.get('record:' + ident)
    assert record['state'] == ('released' if change == 'none' else 'blocked')
    if change != 'none': assert record['verification_failures'] == 1
    if change == 'budget_timeout': assert record['verification_error'] == 'read_timeout'
    if change == 'malformed_instance': assert record['verification_error'] == 'invalid_response'
    assert client.release.await_count == (1 if change == 'none' else 0)
    await worker.tick_room(store, client, 'omm_one', epoch, now + timedelta(seconds=2))
    assert client.release.await_count <= 1


@pytest.mark.asyncio
async def test_confirm_wins_during_dynamic_calendar_read(setup_usage, monkeypatch):
    from app.services import room_usage as service
    store, client, _, actor, _, now, _, epoch = setup_usage
    occ, ident = await source_setup(setup_usage, monkeypatch)
    request = await support.request_for(store, now)
    async def confirming(calendar, event_id):
        await service.command(store, 'omm_one', actor, request, 'confirm', now)
        return detail(occ, organizer_calendar_id='calendar-ou_new')
    client.calendar_event.side_effect = confirming
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    assert (await store.get('record:' + ident))['state'] == 'confirmed'
    client.release.assert_not_called()
