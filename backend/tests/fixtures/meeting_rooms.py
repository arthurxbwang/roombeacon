import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core import room_devices

HttpClient = httpx.AsyncClient


@pytest.fixture
def world(monkeypatch):
    now = datetime.now(UTC)
    event = {'uid': 'event1', 'original_time': 0,
             'start_time': (now - timedelta(minutes=20)).isoformat(),
             'end_time': (now + timedelta(minutes=40)).isoformat(),
             'organizer_info': {'name': '张明'}}
    state = SimpleNamespace(
        values={}, requests=[], rooms=[{'room_id': 'omm_one', 'name': '望岳', 'capacity': 12}],
        busy={'omm_one': [event]}, error_rooms=[], title_error=False, busy_error=False,
        page_loop=False, events=[event], complete_busy_envelope=False,
    )
    cache = AsyncMock()

    async def get(key):
        return state.values.get(key)

    async def put(key, value, ex=None, nx=False):
        if nx and key in state.values:
            return False
        state.values[key] = value
        return True

    async def delete(*keys):
        for key in keys:
            state.values.pop(key, None)

    async def evaluate(script, count, key, expected, value, ttl):
        from app.services.room_schedule_cache import SNAPSHOT_CAS
        assert script == SNAPSHOT_CAS and count == 1
        if state.values.get(key, "") != expected:
            return 0
        state.values[key] = value
        return 1

    cache.eval.side_effect = evaluate
    cache.get.side_effect = get
    cache.set.side_effect = put
    cache.delete.side_effect = delete
    monkeypatch.setattr(room_devices.redis, 'from_url', lambda *a, **k: cache)
    state.cache = cache

    def respond(request):
        state.requests.append(request)
        path = request.url.path
        if path.endswith('/auth/v3/tenant_access_token/internal'):
            return httpx.Response(200, json={'code': 0, 'tenant_access_token': 'test-feishu-token', 'expire': 7200})
        if path.endswith('/vc/v1/rooms'):
            data = {'rooms': state.rooms, 'has_more': state.page_loop, 'page_token': 'same'}
        elif path.endswith('/freebusy/batch_get'):
            if state.busy_error:
                return httpx.Response(200, json={'code': 99991403, 'msg': 'quota exceeded'})
            data = {'free_busy': state.busy, 'error_room_ids': state.error_rooms}
            if state.complete_busy_envelope:
                data.update(time_min=request.url.params['time_min'], time_max=request.url.params['time_max'])
        elif path.endswith('/summary/batch_get'):
            if state.title_error:
                return httpx.Response(200, json={'code': 99991672, 'msg': 'permission denied'})
            refs = json.loads(request.content)['EventUids']
            data = {'EventInfos': [{**ref, 'summary': '产品设计评审'} for ref in refs]}
        else:
            raise AssertionError(f'Unexpected external request {path}')
        return httpx.Response(200, json={'code': 0, 'data': data})

    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: HttpClient(transport=httpx.MockTransport(respond)))
    return state
