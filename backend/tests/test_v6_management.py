"""V6 authorization, bootstrap isolation and config delivery failure regressions."""
import json
import secrets
import time
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.management import auth, devices
from app.management.security import (
    ADMIN_COOKIE,
    DEVICE_COOKIE,
    authenticate_web,
    new_session,
)
from app.management.store import database
from app.room_display_main import app

MASTER = 'x' * 40
ROOM = 'omm_test'
BODY = {'metadata': {'model': 'BX68', 'network': 'wifi'}}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_V6_DB', str(tmp_path / 'v6.db'))
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_CONTROL_TOKEN', MASTER)
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_CONTROL_TOKEN_SECONDARY', '')
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_FEISHU_LOGIN_ENABLED', True)
    monkeypatch.setattr(settings, 'FEISHU_APP_ID', 'test-app')
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_FEISHU_TENANT_KEY', '')
    monkeypatch.setattr(devices, 'cached_directory', AsyncMock(return_value=[{'room_id': ROOM}]))
    # Deliberately no TestClient context: collector never contacts external systems.
    return TestClient(app, base_url='https://roombeacon.thundersoft.com')


def admin():
    return {'Authorization': 'Bearer ' + MASTER}


def enroll(client, token=None):
    token = token or f'v6d:{secrets.token_hex(16)}:{secrets.token_urlsafe(32)}'
    response = client.post('/api/v6/device/enroll', headers={'Authorization': 'Bearer ' + token}, json=BODY)
    assert response.status_code == 200, response.text
    return token, response.json()['data']


def configure(client, identity, revision=1, **changes):
    body = {'expected_revision': revision, 'room_id': ROOM, 'status': 'active',
            'config': {'version': 'v6', 'room_light': True}}
    body.update(changes)
    return client.put('/api/v6/admin/devices/' + identity, headers=admin(), json=body)


def web_cookie(client, token, **extra):
    result = client.post('/api/v6/device/sync', headers={'Authorization': 'Bearer ' + token}, json=BODY | extra)
    assert result.status_code == 200
    return result.json()['data']


def session(client, role):
    with database() as db:
        db.execute('INSERT INTO users VALUES (?,?,?,?,?)', ('user', 'tenant', 'User', role, int(time.time())))
        token = new_session(db, 'user')
    client.cookies.set(ADMIN_COOKIE, token)
    me = client.get('/api/v6/auth/me')
    return me


def test_pending_isolated_idempotent_no_mac_takeover(client):
    token, item = enroll(client)
    _, again = enroll(client, token)
    assert again == item
    data = web_cookie(client, token)
    assert 'web_session' not in data
    assert len(item['code']) == 6
    attacker = token.rsplit(':', 1)[0] + ':' + secrets.token_urlsafe(32)
    assert client.post('/api/v6/device/enroll', headers={'Authorization': 'Bearer ' + attacker},
                       json=BODY).status_code == 401
    _, second = enroll(client)
    assert second['id'] != item['id'] and second['code'] != item['code']
    assert client.get('/api/v6/admin/devices', headers={'Authorization': 'Bearer ' + token}).status_code == 401
    assert client.get('/api/meeting-rooms/display', headers={'Authorization': 'Bearer ' + token}).status_code == 401


def test_binding_version_revocation_and_network_change(client):
    token, item = enroll(client)
    assert configure(client, item['id']).status_code == 200
    value = web_cookie(client, token)
    assert authenticate_web(value['web_session'])['room_id'] == ROOM
    before = authenticate_web(value['web_session'])['digest']
    updated = web_cookie(client, token, metadata={'network': 'ethernet', 'serial': 'same'})
    assert updated['id'] == item['id']
    assert authenticate_web(updated['web_session'])['digest'] == before
    assert configure(client, item['id']).status_code == 409
    assert configure(client, item['id'], 2, status='revoked').status_code == 200
    assert 'web_session' not in web_cookie(client, token)
    client.cookies.set(DEVICE_COOKIE, value['web_session'])
    assert client.get('/api/meeting-rooms/display').status_code == 401
    assert client.post('/api/v6/device/enroll', headers={'Authorization': 'Bearer ' + token}, json=BODY).status_code == 401


def test_reported_version_and_invalid_config(client):
    token, item = enroll(client)
    assert client.post('/api/v6/device/sync', headers={'Authorization': 'Bearer ' + token},
                       json=BODY | {'reported_revision': 99}).status_code == 409
    assert configure(client, item['id'], config={'node_id': 'evil'}).status_code == 422
    assert configure(client, item['id'], room_id='omm_missing').status_code == 422
    assert configure(client, item['id']).status_code == 200
    web_cookie(client, token, reported_revision=1, error='灯控不可用')
    rows = client.get('/api/v6/admin/devices', headers=admin()).json()['data']
    assert rows[0]['revision'] == 2 and rows[0]['reported_revision'] == 1
    assert rows[0]['error'] == '灯控不可用' and 'secret_hash' not in rows[0]


def test_login_csrf_viewer_and_old_admin_api(client):
    assert client.post('/api/v6/auth/session', headers=admin() | {'Origin': 'https://evil.test'}).status_code == 403
    result = client.post('/api/v6/auth/session', headers=admin())
    assert result.status_code == 200
    assert all(x in result.headers['set-cookie'] for x in ['Secure', 'HttpOnly', 'SameSite=lax'])
    csrf = client.get('/api/v6/auth/me').json()['data']['csrf']
    assert client.post('/api/v6/admin/templates', json={'name': 'test', 'config': {}}).status_code == 403
    assert client.post('/api/v6/admin/templates', headers={'x-rb-csrf': csrf},
                       json={'name': 'test', 'config': {}}).status_code == 200
    client.cookies.clear()
    me = session(client, 'viewer')
    assert me.status_code == 200
    assert client.get('/api/v6/admin/devices').status_code == 200
    assert client.get('/api/v6/auth/users').status_code == 403
    csrf = me.json()['data']['csrf']
    assert client.post('/api/v6/admin/templates', headers={'x-rb-csrf': csrf},
                       json={'name': 'test', 'config': {}}).status_code == 403
    # Existing V5 write endpoints also reject the new read-only session.
    assert client.put('/api/room-control/usage-pause', headers={'x-rb-csrf': csrf},
                      json={'paused': True}).status_code == 403


def test_session_revocation_immediate(client):
    session(client, 'viewer')
    with database() as db:
        db.execute("UPDATE users SET role='disabled' WHERE subject='user'")
    assert client.get('/api/v6/admin/devices').status_code == 403


def test_batch_atomic_history_rollback(client):
    _, a = enroll(client)
    _, b = enroll(client)
    configure(client, a['id'])
    configure(client, b['id'])
    result = client.post('/api/v6/admin/batch-config', headers=admin(),
                         json={'devices': {a['id']: 2, b['id']: 1}, 'config': {'portrait': True}})
    assert result.status_code == 409
    rows = client.get('/api/v6/admin/devices', headers=admin()).json()['data']
    assert all(row['revision'] == 2 for row in rows)
    result = client.post('/api/v6/admin/batch-config', headers=admin(),
                         json={'devices': {a['id']: 2, b['id']: 2}, 'config': {'portrait': True}})
    assert result.status_code == 200
    result = client.post(f"/api/v6/admin/devices/{a['id']}/rollback", headers=admin(),
                         json={'expected_revision': 3, 'revision': 2})
    assert result.status_code == 200
    assert result.json()['data']['revision'] == 4
    assert result.json()['data']['config']['portrait'] is False
    audit = client.get('/api/v6/admin/audit', headers=admin()).text
    assert MASTER not in audit and 'secret_hash' not in audit


def test_oauth_browser_binding_replay_pending(client, monkeypatch):
    monkeypatch.setattr(auth, 'feishu_identity', AsyncMock(return_value={
        'tenant_key': 'tenant', 'open_id': 'ou_test', 'name': 'Tester'}))
    result = client.get('/api/v6/auth/feishu/start', follow_redirects=False)
    state = parse_qs(urlparse(result.headers['location']).query)['state'][0]
    url = '/api/v6/auth/feishu/callback?code=test&state=' + state
    saved = client.cookies.get(auth.STATE_COOKIE)
    client.cookies.clear()
    assert client.get(url, follow_redirects=False).status_code == 401
    client.cookies.set(auth.STATE_COOKIE, saved)
    assert client.get(url, follow_redirects=False).status_code == 302
    assert client.get('/api/v6/auth/me').status_code == 403
    assert client.get(url, follow_redirects=False).status_code == 401
    with database() as db:
        assert db.execute('SELECT role FROM users').fetchone()[0] == 'pending'


def test_oauth_upstream_failure_consumes_state(client, monkeypatch):
    from app.core.exceptions import AppError
    monkeypatch.setattr(auth, 'feishu_identity', AsyncMock(side_effect=AppError(502, 'failure', 502)))
    result = client.get('/api/v6/auth/feishu/start', follow_redirects=False)
    state = parse_qs(urlparse(result.headers['location']).query)['state'][0]
    url = '/api/v6/auth/feishu/callback?code=secret&state=' + state
    result = client.get(url, follow_redirects=False)
    assert result.status_code == 302 and 'secret' not in result.headers['location']
    assert client.get(url, follow_redirects=False).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize('response', [httpx.Response(503, text='secret'), httpx.Response(200, json={'code': 1}),
                                     httpx.Response(200, text='invalid'), httpx.Response(200, json=[])] )
async def test_feishu_error_sanitized(monkeypatch, response):
    from app.core.exceptions import AppError
    response.request = httpx.Request('POST', 'https://open.feishu.cn')
    monkeypatch.setattr(httpx.AsyncClient, 'post', AsyncMock(return_value=response))
    with pytest.raises(AppError) as error:
        await auth.feishu_identity('sensitive-code')
    assert 'secret' not in str(error.value) and 'sensitive' not in str(error.value)


def test_enrollment_rate_limit_and_expired_web_cookie(client):
    for _ in range(30):
        enroll(client)
    token = f'v6d:{secrets.token_hex(16)}:{secrets.token_urlsafe(32)}'
    assert client.post('/api/v6/device/enroll', headers={'Authorization': 'Bearer ' + token}, json=BODY).status_code == 429
    client.cookies.set(DEVICE_COOKIE, 'v6w:' + 'a' * 32 + ':1:1:' + 'b' * 64)
    assert client.get('/api/meeting-rooms/display').status_code == 401
    with database() as db:
        assert json.loads(db.execute('SELECT config FROM devices LIMIT 1').fetchone()[0])['node_id'] == 'central'


@pytest.mark.asyncio
@pytest.mark.parametrize('bad_user', [False, True])
async def test_feishu_exchange_contract_and_user_validation(monkeypatch, bad_user):
    from app.core.exceptions import AppError
    token_reply = httpx.Response(200, json={'code': 0, 'access_token': 'private-user-token'},
                                request=httpx.Request('POST', 'https://open.feishu.cn'))
    user_reply = httpx.Response(200, json={'code': 0, 'data': {} if bad_user else {
        'open_id': 'ou_user', 'tenant_key': 'tenant', 'name': '姓名'}},
        request=httpx.Request('GET', 'https://open.feishu.cn'))
    post = AsyncMock(return_value=token_reply)
    get = AsyncMock(return_value=user_reply)
    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    monkeypatch.setattr(httpx.AsyncClient, 'get', get)
    if bad_user:
        with pytest.raises(AppError):
            await auth.feishu_identity('auth-code')
    else:
        assert (await auth.feishu_identity('auth-code'))['open_id'] == 'ou_user'
        assert post.call_args.kwargs['json']['grant_type'] == 'authorization_code'
        assert get.call_args.kwargs['headers']['Authorization'] == 'Bearer private-user-token'


def test_cookie_cannot_manage_and_device_actions_reject_cross_site(client):
    token, item = enroll(client)
    configure(client, item['id'])
    value = web_cookie(client, token)
    client.cookies.set(DEVICE_COOKIE, value['web_session'])
    assert client.get('/api/v6/admin/devices').status_code == 401
    assert client.post('/api/meeting-rooms/usage/heartbeat', json={},
                       headers={'Origin': 'https://evil.test', 'x-rb-device': '1'}).status_code == 403


def test_user_authorization_revokes_session_and_never_self_demotes(client):
    me = session(client, 'admin').json()['data']
    csrf = {'x-rb-csrf': me['csrf']}
    assert client.put('/api/v6/auth/users/user', headers=csrf, json={'role': 'viewer'}).status_code == 409
    with database() as db:
        db.execute('INSERT INTO users VALUES (?,?,?,?,?)', ('other', 'tenant', 'Other', 'viewer', 1))
        new_session(db, 'other')
    assert client.put('/api/v6/auth/users/other', headers=csrf, json={'role': 'disabled'}).status_code == 200
    with database() as db:
        assert db.execute("SELECT COUNT(*) FROM sessions WHERE subject='other'").fetchone()[0] == 0
