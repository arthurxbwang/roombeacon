from unittest.mock import AsyncMock

import httpx
import pytest

from app.connectors.feishu.rooms import FeishuRoomsClient
from app.core.exceptions import ExternalAPIError
from app.services.meeting_rooms import schedule_for
from tests.fixtures.meeting_rooms import HttpClient


@pytest.mark.asyncio
async def test_missing_name_is_completed_without_unlocking_title(world, monkeypatch):
    world.events[0]['organizer_info'] = {'open_id': 'ou_test', 'name': ''}
    lookup = AsyncMock(return_value='李明')
    monkeypatch.setattr(FeishuRoomsClient, 'organizer_name', lookup, raising=False)
    first = await schedule_for('omm_one')
    assert first.events[0].organizer == '李明'
    assert first.events[0].summary is None
    assert not any('/summary/' in r.url.path for r in world.requests)
    for key in list(world.values):
        if key.startswith(('rooms:snapshot:', 'rooms:refresh:')):
            del world.values[key]
    assert (await schedule_for('omm_one')).events[0].organizer == '李明'
    lookup.assert_awaited_once_with('ou_test')


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', [ExternalAPIError('feishu', 'denied'), httpx.ConnectError('offline'), TimeoutError()])
async def test_lookup_failure_preserves_busy_and_is_negatively_cached(world, monkeypatch, failure):
    world.events[0]['organizer_info'] = {'open_id': 'ou_test'}
    lookup = AsyncMock(side_effect=failure)
    monkeypatch.setattr(FeishuRoomsClient, 'organizer_name', lookup, raising=False)
    for _ in range(2):
        for key in list(world.values):
            if key.startswith(('rooms:snapshot:', 'rooms:refresh:')):
                del world.values[key]
        result = await schedule_for('omm_one')
        assert len(result.events) == 1
        assert result.events[0].organizer is None
        assert result.valid_until > result.synced_at
    assert lookup.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('info', [None, {}, {'open_id': '../bad'}, {'name': '原姓名', 'open_id': 'ou_test'}])
async def test_no_lookup_without_valid_missing_name(world, monkeypatch, info):
    world.events[0]['organizer_info'] = info
    lookup = AsyncMock()
    monkeypatch.setattr(FeishuRoomsClient, 'organizer_name', lookup, raising=False)
    await schedule_for('omm_one')
    lookup.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('payload,expected', [({'name': ' 李明 '}, '李明'), ({}, None), ({'name': ''}, None)])
async def test_contact_connector_request_and_name_only(payload, expected):
    def respond(request):
        assert request.url.path == '/open-apis/contact/v3/users/ou_test'
        assert request.url.params['user_id_type'] == 'open_id'
        return httpx.Response(200, json={'code': 0, 'data': {'user': payload}})
    client = FeishuRoomsClient()
    client._get_tenant_token = AsyncMock(return_value='test')
    client._client = HttpClient(transport=httpx.MockTransport(respond))
    try:
        assert await client.organizer_name('ou_test') == expected
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_cache_expiry_and_app_change_do_not_reuse_names(world, monkeypatch):
    world.events[0]['organizer_info'] = {'open_id': 'ou_test'}
    lookup = AsyncMock(return_value='李明')
    monkeypatch.setattr(FeishuRoomsClient, 'organizer_name', lookup)
    await schedule_for('omm_one')
    names = [k for k in world.values if k.startswith('rooms:organizer:')]
    assert len(names) == 1
    assert any(c.kwargs.get('ex') == 300 for c in world.cache.set.call_args_list)
    from app.core.config import settings
    monkeypatch.setattr(settings, 'FEISHU_APP_ID', 'independent-app')
    for key in list(world.values):
        if key.startswith(('rooms:snapshot:', 'rooms:refresh:')):
            del world.values[key]
    lookup.side_effect = ExternalAPIError('feishu', 'revoked')
    assert (await schedule_for('omm_one')).events[0].organizer is None
    assert lookup.await_count == 2
    assert any(c.kwargs.get('ex') == 60 for c in world.cache.set.call_args_list)
    # Simulate Redis expiry; a formerly successful name is not a stale fallback.
    for key in list(world.values):
        if key.startswith(('rooms:organizer:', 'rooms:snapshot:', 'rooms:refresh:')):
            del world.values[key]
    assert (await schedule_for('omm_one')).events[0].organizer is None
    assert lookup.await_count == 3


@pytest.mark.asyncio
async def test_lookup_deadline_and_deduplication(world, monkeypatch):
    import asyncio

    from app.services import room_organizers
    monkeypatch.setattr(room_organizers, 'LOOKUP_SECONDS', .01)
    world.events[0]['organizer_info'] = {'open_id': 'ou_test'}
    world.busy['omm_one'].append({**world.events[0], 'uid': 'event2'})
    cancelled = []
    async def slow(_):
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.append(True)
    lookup = AsyncMock(side_effect=slow)
    monkeypatch.setattr(FeishuRoomsClient, 'organizer_name', lookup)
    result = await schedule_for('omm_one')
    assert len(result.events) == 2
    assert all(e.organizer is None for e in result.events)
    assert lookup.await_count == 1
    assert cancelled == [True]


@pytest.mark.asyncio
@pytest.mark.parametrize('payload', [{'name': 123}, None])
async def test_contact_malformed_data_rejected(payload):
    client = FeishuRoomsClient()
    client._api = AsyncMock(return_value={'data': {'user': payload}})
    with pytest.raises((ValueError, TypeError)):
        await client.organizer_name('ou_test')


@pytest.mark.asyncio
async def test_lookup_limit_defers_remaining_ids(world, monkeypatch):
    from app.services.meeting_rooms import parse_events
    from app.services.room_organizers import complete_organizers

    rows = [{**world.events[0], 'uid': f'event{i}',
             'organizer_info': {'open_id': f'ou_{i}'}} for i in range(21)]
    events = parse_events(rows)
    client = FeishuRoomsClient()
    client.organizer_name = AsyncMock(return_value='李明')
    await complete_organizers(world.cache, client, {'omm_one': rows}, {'omm_one': events})
    assert client.organizer_name.await_count == 20
    assert sum(e.organizer is not None for e in events) == 20
    await complete_organizers(world.cache, client, {'omm_one': rows},
                              {'omm_one': parse_events(rows)})
    assert client.organizer_name.await_count == 21
