"""Control confirmation is explicit, allowlisted and never supplies release health."""
from datetime import timedelta

import httpx
import pytest

from app.core.config import settings
from app.services import room_usage as service
from tests.services import test_room_usage as support

redis_socket = support.redis_socket
setup_usage = support.setup_usage


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['ok', 'no_admin', 'device', 'not_allowed', 'official', 'stale',
                                  'wrong_instance', 'wrong_revision', 'expired', 'releasing'])
async def test_control_confirmation_boundaries(setup_usage, monkeypatch, case):
    store, client, token, _, policy, now, snapshot, _ = setup_usage
    state = await service.view(store, 'omm_one', now)
    key = 'record:' + state['record']['id']
    record = await store.get(key)
    await store.put(key, {**record, 'state': 'blocked', 'reason': 'missed_window', 'session_id': None})
    before_health = await store.get('heartbeat:omm_one')
    payload = {'occurrence_id': record['id'], 'policy_revision': policy['revision']}
    credential = settings.ROOM_DISPLAY_CONTROL_TOKEN
    expected = 200
    if case == 'no_admin': credential = ''; expected = 401
    if case == 'device': credential = token; expected = 401
    if case == 'not_allowed':
        monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_RELEASE_ROOM_IDS', set()); expected = 403
    if case == 'official':
        await store.put('policy:omm_one', {**policy, 'owner': 'official', 'mode': 'off'}); expected = 409
    if case == 'stale': snapshot.valid_until = now; expected = 409
    if case == 'wrong_instance': payload['occurrence_id'] = 'f' * 64; expected = 409
    if case == 'wrong_revision': payload['policy_revision'] = 'old'; expected = 409
    if case == 'expired':
        await store.put(key, {**record, 'deadline': (now - timedelta(seconds=1)).isoformat()}); expected = 409
    if case == 'releasing':
        await store.put(key, {**record, 'state': 'releasing'}); expected = 409
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=support.app), base_url='http://test') as http:
        response = await http.post('/api/room-control/usage/omm_one/confirm', json=payload,
                                   headers={'Authorization': 'Bearer ' + credential})
        assert response.status_code == expected
        if expected == 200:
            assert response.json()['data']['record']['state'] == 'confirmed'
            assert (await http.post('/api/room-control/usage/omm_one/confirm', json=payload,
                                   headers={'Authorization': 'Bearer ' + credential})).status_code == 200
            saved = await store.get(key)
            assert not saved['verified'] and saved['session_id'] is None
        else:
            assert (await store.get(key))['state'] != 'confirmed'
    assert await store.get('heartbeat:omm_one') == before_health
    client.release.assert_not_called()
