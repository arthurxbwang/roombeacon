"""Real test preparation must never mutate unrelated calendars or whole series."""
import json
import stat
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest

from app.connectors.feishu.room_release import FeishuRoomReleaseClient
from app.services.room_usage_test_driver import (
    CALENDAR_NAME,
    TEST_ROOM,
    FixtureDriver,
    FixtureDriverError,
)


def driver(tmp_path):
    client = AsyncMock()
    client.calendar_read.return_value = {'calendar': {'summary': CALENDAR_NAME, 'type': 'shared', 'role': 'owner'}}
    result = FixtureDriver(client, tmp_path / 'ledger.json')
    result.data['calendar_id'] = 'fixture-calendar'
    result.write = AsyncMock()
    return result


@pytest.mark.asyncio
async def test_create_only_invites_test_room_and_waits_for_acceptance(tmp_path):
    d = driver(tmp_path)
    d.write.side_effect = [{'event': {'event_id': 'fixture_0'}}, {}]
    result = await d.create('daily', datetime.now(UTC) + timedelta(minutes=30), repeat='daily')
    assert result['stage'] == 'awaiting_room_acceptance'
    payload = d.write.call_args_list[1].args[2]
    assert payload == {'attendees': [{'type': 'resource', 'room_id': TEST_ROOM}],
                       'need_notification': False, 'is_enable_admin': False}
    assert stat.S_IMODE(d.path.stat().st_mode) == 0o600
    with pytest.raises(FixtureDriverError):
        await d.create('daily', datetime.now(UTC) + timedelta(minutes=30))
    assert d.write.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', ['personal', 'wrong_name', 'read_only'])
async def test_unrelated_calendars_are_rejected(tmp_path, bad):
    d = driver(tmp_path)
    cal = d.client.calendar_read.return_value['calendar']
    cal[{'personal': 'type', 'wrong_name': 'summary', 'read_only': 'role'}[bad]] = {
        'personal': 'primary', 'wrong_name': 'Business', 'read_only': 'reader'}[bad]
    with pytest.raises(FixtureDriverError):
        await d.create('one', datetime.now(UTC) + timedelta(minutes=30))
    d.write.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_case_and_zero_series_time_never_write(tmp_path):
    d = driver(tmp_path)
    with pytest.raises(FixtureDriverError): await d.change('business')
    d.data['cases']['series'] = {'event_id': 'fixture_0', 'repeat': 'weekly', 'stage': 'awaiting_room_acceptance'}
    with pytest.raises(FixtureDriverError): await d.change('series')
    d.write.assert_not_called()


@pytest.mark.asyncio
async def test_repeated_instance_move_preserves_positive_original(tmp_path):
    d = driver(tmp_path)
    d.data['cases']['series'] = {'event_id': 'fixture_0', 'repeat': 'weekly', 'stage': 'awaiting_room_acceptance'}
    original = int((datetime.now(UTC) + timedelta(days=7)).timestamp())
    d.client.calendar_instances.return_value = [{'event_id': f'fixture_{original}', 'status': 'confirmed'}]
    await d.change('series', original, datetime.now(UTC) + timedelta(minutes=30))
    assert d.write.call_args.args[0] == 'PATCH'
    assert d.write.call_args.args[1].endswith(f'/events/fixture_{original}')
    assert 'recurrence' not in d.write.call_args.args[2]


@pytest.mark.asyncio
async def test_write_timeout_is_durable_and_never_retried(tmp_path):
    d = driver(tmp_path)
    d.data['cases']['one'] = {'event_id': 'fixture_0', 'repeat': 'none', 'stage': 'awaiting_room_acceptance'}
    d.write.side_effect = httpx.ReadTimeout('fixture')
    with pytest.raises(httpx.ReadTimeout): await d.change('one')
    saved = json.loads(d.path.read_text())
    assert saved['cases']['one']['stage'] == 'cancelling'
    with pytest.raises(FixtureDriverError): await d.change('one')
    assert d.write.await_count == 1


@pytest.mark.asyncio
async def test_resource_invitation_success_is_not_booking_success(tmp_path):
    d = driver(tmp_path)
    d.data['cases']['one'] = {'event_id': 'fixture_0', 'repeat': 'none', 'stage': 'awaiting_room_acceptance'}
    d.client.calendar_event.return_value = {'status': 'confirmed'}
    calendar = d.client.calendar_read.return_value
    d.client.calendar_read.side_effect = [calendar, {'items': [{'type': 'resource', 'room_id': TEST_ROOM, 'rsvp_status': 'needs_action'}]}]
    assert (await d.inspect('one'))['room_accepted'] is False


@pytest.mark.asyncio
@pytest.mark.parametrize('condition', ['ok', 'denied', 'partial', 'malformed', 'timeout'])
async def test_calendar_connector_failure_boundaries(condition, monkeypatch):
    client = FeishuRoomReleaseClient()
    client._get_tenant_token = AsyncMock(return_value='fixture-token')
    requests = []

    def handler(request):
        requests.append(request)
        if condition == 'timeout': raise httpx.ReadTimeout('fixture')
        if condition == 'denied': return httpx.Response(403, json={'code': 99991672})
        if condition == 'malformed': return httpx.Response(200, json={'code': 0, 'data': {}})
        return httpx.Response(200, json={'code': 0, 'data': {'items': [], 'has_more': condition == 'partial'}})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client._get_client = AsyncMock(return_value=http)
    now = datetime.now(UTC)
    try:
        if condition == 'ok': assert await client.calendar_instances('calendar/id', 'uid_0', now, now + timedelta(hours=1)) == []
        else:
            with pytest.raises((httpx.HTTPError, ValueError)):
                await client.calendar_instances('calendar/id', 'uid_0', now, now + timedelta(hours=1))
        assert len(requests) == 1
        assert requests[0].headers['authorization'] == 'Bearer fixture-token'
        assert 'calendar%2Fid' in str(requests[0].url)
    finally:
        await http.aclose()
