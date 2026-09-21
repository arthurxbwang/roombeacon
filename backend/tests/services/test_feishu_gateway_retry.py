"""Transient freebusy gateway errors retry only bounded, explicitly read-only calls."""
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
from tenacity import wait_none

from app.connectors.feishu.client import FeishuClient
from app.connectors.feishu.room_release import FeishuRoomReleaseClient
from app.connectors.feishu.rooms import FeishuRoomsClient
from app.schemas.meeting_room import Room
from app.schemas.room_usage import Occurrence
from app.services import room_display_collector as collector

HttpClient = httpx.AsyncClient


@pytest.fixture
def gateway(monkeypatch):
    def setup(client, statuses):
        calls = []
        def respond(request):
            calls.append(request)
            status = statuses[min(len(calls) - 1, len(statuses) - 1)]
            return httpx.Response(status, json={'code': 0, 'data': {
                'free_busy': {'omm_one': []}, 'error_room_ids': [],
            }})
        client._client = HttpClient(transport=httpx.MockTransport(respond))
        client._get_tenant_token = AsyncMock(return_value='test-token')
        return calls
    monkeypatch.setattr(FeishuClient._api.retry, 'wait', wait_none())
    return setup


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [502, 503, 504])
async def test_freebusy_gateway_failure_recovers_in_same_refresh(gateway, status):
    client = FeishuRoomsClient()
    calls = gateway(client, [status, 200])
    now = datetime.now(UTC)
    try:
        result = await client.freebusy(['omm_one'], now, now + timedelta(hours=1))
        assert result['free_busy'] == {'omm_one': []}
        assert len(calls) == 2
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('status,attempts', [(504, 3), (400, 1), (401, 1), (403, 1), (429, 1)])
async def test_persistent_failure_is_bounded_and_not_a_success(gateway, status, attempts):
    client = FeishuRoomsClient()
    calls = gateway(client, [status])
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await client._api('GET', '/meeting_room/freebusy/batch_get')
        assert len(calls) == attempts
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('method,path', [('POST', '/meeting_room/instance/reply'),
                                        ('POST', '/meeting_room/freebusy/batch_get'),
                                        ('GET', '/unrelated')])
async def test_gateway_retry_does_not_expand_to_other_operations(gateway, method, path):
    client = FeishuClient()
    calls = gateway(client, [504, 200])
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await client._api(method, path)
        assert len(calls) == 1
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_real_release_transport_still_attempts_only_once(gateway):
    now = datetime.now(UTC)
    event = Occurrence(uid='fixture', original_time=0, start_time=now, end_time=now + timedelta(hours=1))
    client = FeishuRoomReleaseClient()
    calls = gateway(client, [504, 200])
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await client.release('omm_one', event, 'NOT_CHECK_IN')
        assert len(calls) == 1
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_failed_retry_keeps_cache_and_expiry_unchanged(world, gateway):
    client = FeishuRoomsClient()
    gateway(client, [200])
    now = datetime.now(UTC)
    try:
        await collector.refresh_batch(world.cache, client, [Room(room_id='omm_one', name='fixture')], now)
        previous = world.values['rooms:snapshot:omm_one']
        await client.close()
        calls = gateway(client, [504])
        with pytest.raises(httpx.HTTPStatusError):
            await collector.refresh_batch(world.cache, client, [Room(room_id='omm_one', name='fixture')], now + timedelta(seconds=10))
        assert len(calls) == 3
        assert world.values['rooms:snapshot:omm_one'] == previous
    finally:
        await client.close()
