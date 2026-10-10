"""Real HTTP response shapes, sanitized error codes and bounded batch identity."""
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from app.connectors.feishu.calendar_errors import CalendarEvidenceError
from app.connectors.feishu.room_release import FeishuRoomReleaseClient


def client_for(monkeypatch, handler):
    client = FeishuRoomReleaseClient()
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(client, '_get_tenant_token', AsyncMock(return_value='private-token-fixture'))
    return client


@pytest.mark.asyncio
@pytest.mark.parametrize('status,code,reason', [
    (404, 193001, 'event_not_found'), (403, 191002, 'access_denied'),
    (403, 193003, 'access_denied'), (200, 193001, 'event_not_found'),
    (429, 99991400, 'rate_limited'), (503, 999, 'upstream_unavailable'),
    (200, '0', 'invalid_response'), (200, 0, 'invalid_response'),
])
async def test_safe_error_classification(monkeypatch, status, code, reason):
    def response(request):
        return httpx.Response(status, json={'code': code, 'msg': 'private-event-body', 'data': None},
                              headers={'Retry-After': '60'})
    client = client_for(monkeypatch, response)
    try:
        with pytest.raises(CalendarEvidenceError) as failure:
            await client.calendar_event('private-calendar', 'private-event_0')
        err = failure.value
        assert err.reason == reason
        assert 'private' not in str(err) and 'private' not in repr(err.__dict__)
        if reason == 'rate_limited': assert err.retry_after == 60
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure,reason', [('timeout', 'read_timeout'), ('network', 'network_error'), ('json', 'invalid_response')])
async def test_transport_failures_hide_request_and_body(monkeypatch, failure, reason):
    def response(request):
        if failure == 'timeout': raise httpx.ReadTimeout('secret-token-path', request=request)
        if failure == 'network': raise httpx.ConnectError('secret-token-path', request=request)
        return httpx.Response(200, text='private-response')
    client = client_for(monkeypatch, response)
    try:
        with pytest.raises(CalendarEvidenceError, match=reason):
            await client.calendar_event('private-calendar', 'private-event')
    finally: await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('status,reason', [(403, 'access_denied'), (429, 'rate_limited'), (503, 'upstream_unavailable')])
async def test_non_json_gateway_response_keeps_http_failure_class(monkeypatch, status, reason):
    client = client_for(monkeypatch, lambda request: httpx.Response(status, text='private gateway body', headers={'Retry-After': '90'}))
    try:
        with pytest.raises(CalendarEvidenceError) as failure:
            await client.calendar_event('private-calendar', 'event_0')
        assert failure.value.reason == reason
        assert failure.value.http_status == status
        assert failure.value.retry_after == 90
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('bad', [None, 'foreign', 'duplicate', 'wrong_type', 'missing_id', 'missing_rows'])
async def test_primary_batch_matches_users_and_never_exposes_metadata(monkeypatch, bad):
    requests = []
    def response(request):
        requests.append(request)
        assert request.method == 'POST' and request.url.path.endswith('/calendars/primarys')
        assert json.loads(request.content) == {'user_ids': ['ou_a', 'ou_b']}
        rows = [{'user_id': 'ou_a', 'calendar': {'calendar_id': 'calendar-a', 'type': 'primary'}}]
        if bad == 'foreign': rows[0]['user_id'] = 'ou_else'
        if bad == 'duplicate': rows *= 2
        if bad == 'wrong_type': rows[0]['calendar']['type'] = 'shared'
        if bad == 'missing_id': rows[0]['calendar'].pop('calendar_id')
        return httpx.Response(200, json={'code': 0, 'data': {} if bad == 'missing_rows' else {'calendars': rows}})
    client = client_for(monkeypatch, response)
    try:
        if bad:
            with pytest.raises(CalendarEvidenceError): await client.primary_calendars(['ou_b', 'ou_a', 'ou_a'])
        else:
            assert await client.primary_calendars(['ou_b', 'ou_a', 'ou_a']) == {'ou_a': 'calendar-a'}
        for ids in [[], ['bad-id'], ['ou_' + str(i) for i in range(51)]]:
            with pytest.raises(CalendarEvidenceError): await client.primary_calendars(ids)
        assert len(requests) == 1
    finally: await client.close()
