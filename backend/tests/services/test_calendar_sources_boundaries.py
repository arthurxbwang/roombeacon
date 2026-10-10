"""Cache isolation, paired publication and authenticated diagnostic boundaries."""
import asyncio
import json
from datetime import timedelta
from unittest.mock import AsyncMock

import httpx
import pytest

from app.connectors.feishu.calendar_errors import CalendarEvidenceError
from app.core.config import settings
from app.room_display_main import app
from app.services import room_usage_worker as worker
from app.services.room_calendar_sources import cache_for, primary_for
from app.services.room_schedule_cache import save_snapshot
from app.services.room_usage_autoverify import calendar_qualification
from app.services.room_usage_store import PREFIX
from tests.services import test_room_usage as support
from tests.services.test_room_usage_autoverify import detail
from tests.services.test_room_usage_sources import source_setup

redis_socket = support.redis_socket
setup_usage = support.setup_usage


@pytest.mark.asyncio
async def test_primary_batch_is_coalesced_and_credentials_isolate_cache(monkeypatch):
    client = AsyncMock()
    users = ['ou_' + str(i) for i in range(50)]
    client.primary_calendars.return_value = {u: 'calendar-' + u for u in users}
    result = await asyncio.gather(*(primary_for(client, u, users) for u in users))
    assert len(set(result)) == 50
    client.primary_calendars.assert_awaited_once_with(users)
    monkeypatch.setattr(settings, 'FEISHU_APP_SECRET', 'rotated')
    await primary_for(client, users[0], users)
    assert client.primary_calendars.await_count == 2
    for i in range(600):
        await primary_for(client, 'ou_more' + str(i), ['ou_more' + str(i)])
    assert len(cache_for(client)) <= 512


@pytest.mark.asyncio
async def test_stale_primary_is_refreshed_once_after_event_disappears(setup_usage, monkeypatch):
    store, client, _, _, _, now, _, _ = setup_usage
    occ, _ = await source_setup(setup_usage, monkeypatch)
    await calendar_qualification(client, 'omm_one', occ, store=store, now=now)
    client.primary_calendars.return_value = {'ou_new': 'new-primary'}
    async def moved(calendar, event_id):
        if calendar != 'new-primary': raise CalendarEvidenceError('event_not_found', http_status=404, code=193001)
        return detail(occ, organizer_calendar_id=calendar)
    client.calendar_event.side_effect = moved
    result = await calendar_qualification(client, 'omm_one', occ, store=store, now=now)
    assert result['_calendar_source']['calendar'] == 'new-primary'
    assert client.primary_calendars.await_count == 2


@pytest.mark.asyncio
async def test_unresolved_primary_negative_cache_prevents_repeated_directory_reads(setup_usage, monkeypatch):
    store, client, _, _, _, now, _, _ = setup_usage
    occ, _ = await source_setup(setup_usage, monkeypatch)
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_AUTO_VERIFY_CALENDARS', {})
    client.primary_calendars.return_value = {}
    for _ in range(4):
        with pytest.raises(CalendarEvidenceError, match='source_unresolved'):
            await calendar_qualification(client, 'omm_one', occ, store=store, now=now)
    client.primary_calendars.assert_awaited_once()
    client.calendar_event.assert_not_called()


@pytest.mark.asyncio
async def test_slow_snapshot_cannot_replace_newer_organizer_evidence(setup_usage):
    store, _, _, _, _, _, snapshot, _ = setup_usage
    event = snapshot.events[0]
    row = {**event.model_dump(mode='json'), 'organizer_info': {'open_id': 'ou_new'}}
    assert await save_snapshot(store.cache, snapshot, 300, source_rows=[row])
    old = snapshot.model_copy(update={'synced_at': snapshot.synced_at - timedelta(seconds=1)})
    assert not await save_snapshot(store.cache, old, 300, source_rows=[{**row, 'organizer_info': {'open_id': 'ou_old'}}])
    evidence = await store.get('sources:omm_one')
    assert set(evidence['organizers'].values()) == {'ou_new'}
    assert evidence['snapshot_at'] == snapshot.synced_at.isoformat()
    assert abs(await store.cache.ttl('rooms:snapshot:omm_one') - await store.cache.ttl(PREFIX + 'sources:omm_one')) <= 1
    assert 'ou_new' not in await store.cache.get('rooms:snapshot:omm_one')


@pytest.mark.asyncio
async def test_rate_limit_obeys_retry_after_without_extending_deadline(setup_usage, monkeypatch):
    store, client, _, actor, policy, now, snapshot, epoch = setup_usage
    _, ident = await source_setup(setup_usage, monkeypatch)
    old = await store.get('record:' + ident)
    client.calendar_event.side_effect = CalendarEvidenceError('rate_limited', http_status=429, retry_after=90)
    for seconds in [0, 30, 60, 89, 90]:
        at = now + timedelta(seconds=seconds)
        await store.put('heartbeat:omm_one', support.health(actor, policy, snapshot, at))
        await worker.tick_room(store, client, 'omm_one', epoch, at)
    failed = await store.get('record:' + ident)
    assert failed['verification_failures'] == 2
    assert failed['verification_retry_at'] == now.timestamp() + 180
    assert failed['deadline'] == old['deadline']
    assert sum(row['action'] == 'verification_failed' for row in await store.audit('omm_one')) == 1
    client.release.assert_not_called()


@pytest.mark.asyncio
async def test_diagnostics_are_authenticated_private_and_only_unresolved(setup_usage, monkeypatch):
    store, client, token, _, _, now, _, epoch = setup_usage
    _, ident = await source_setup(setup_usage, monkeypatch)
    client.calendar_event.side_effect = CalendarEvidenceError('event_not_found', http_status=404, code=193001)
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    key = 'record:' + ident
    record = await store.get(key)
    await store.put(key, {**record, '_calendar_source': {'calendar': 'secret-calendar', 'organizer': 'ou_private'}})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as http:
        path = '/api/room-control/usage/omm_one'
        for credential in ['', token]:
            assert (await http.get(path, headers={'Authorization': 'Bearer ' + credential})).status_code == 401
        headers = {'Authorization': 'Bearer ' + settings.ROOM_DISPLAY_CONTROL_TOKEN}
        response = await http.get(path, headers=headers)
        assert response.status_code == 200
        data = response.json()['data']
        assert data['verification_issues'][0]['verification_code'] == 193001
        public = json.dumps(data)
        assert 'secret-calendar' not in public and 'ou_private' not in public and '_calendar_source' not in public
        for state in ['confirmed', 'released', 'uncertain']:
            await store.put(key, {**record, 'state': state})
            assert (await http.get(path, headers=headers)).json()['data']['verification_issues'] == []
        await store.put(key, {**record, 'verification_error': None})
        assert (await http.get(path, headers=headers)).json()['data']['verification_issues'] == []
