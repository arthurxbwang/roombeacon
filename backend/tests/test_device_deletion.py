"""Deleted inventory entries must never regain device or browser access."""
import pytest

from app.core.exceptions import UnauthorizedError
from app.management.security import authenticate_web, current_usage_actor
from app.management.store import database

from . import test_v6_management as v6

client = v6.client


def remove(client, device, **extra):
    return client.request('DELETE', '/api/v6/admin/devices/' + device['id'],
                          headers=v6.admin(), json={'expected_revision': 2,
                                                   'confirm_code': device['code']} | extra)


def test_deletion_removes_inventory_and_invalidates_both_credentials(client):
    token, item = v6.enroll(client)
    assert v6.configure(client, item['id']).status_code == 200
    cookie = v6.web_cookie(client, token, reported_revision=2)['web_session']
    fingerprint = authenticate_web(cookie)['digest']
    with database() as db:
        db.execute("INSERT INTO device_installations VALUES (?, 'builtin-bx68', 1, 'old')", (item['id'],))
        db.execute("INSERT INTO room_configurations VALUES (?, 'software', 1, 1, ?, '{}', 'applied', '', '测试房', '', '')",
                   (v6.ROOM, item['id']))
        db.execute("INSERT INTO configuration_deployments VALUES ('old', ?, ?, 'builtin-bx68', 1, 'software', 1, 2, ?, 'test', 1)",
                   (item['id'], v6.ROOM, '{"after":{},"device_code":"' + item['code'] + '"}'))
    assert current_usage_actor(v6.ROOM, fingerprint)
    assert remove(client, item).status_code == 200
    assert client.get('/api/v6/admin/devices', headers=v6.admin()).json()['data'] == []
    state = client.get('/api/v6/admin/configuration', headers=v6.admin()).json()['data']
    assert state['devices'] == {} and state['deployments'][0]['state'] == 'inactive'
    assert client.post('/api/v6/device/enroll', headers={'Authorization': 'Bearer ' + token},
                       json=v6.BODY).status_code == 401
    assert client.post('/api/v6/device/sync', headers={'Authorization': 'Bearer ' + token},
                       json=v6.BODY).status_code == 401
    with pytest.raises(UnauthorizedError):
        authenticate_web(cookie)
    assert not current_usage_actor(v6.ROOM, fingerprint)
    assert v6.configure(client, item['id'], 3).status_code == 404
    assert remove(client, item).status_code == 404
    with database() as db:
        assert not db.execute('SELECT 1 FROM device_installations').fetchone()
        room = db.execute('SELECT * FROM room_configurations').fetchone()
        assert room['controller_id'] == '' and room['policy_state'] == 'pending'
        assert db.execute('SELECT COUNT(*) FROM history').fetchone()[0] == 3
        assert db.execute("SELECT detail FROM audit WHERE action='device-delete'").fetchone()


def test_deletion_requires_admin_confirmation_and_fresh_revision(client):
    _, item = v6.enroll(client)
    assert v6.configure(client, item['id']).status_code == 200
    assert remove(client, item, confirm_code='WRONG1').status_code == 422
    assert remove(client, item, expected_revision=1).status_code == 409
    path = '/api/v6/admin/devices/' + item['id']
    body = {'expected_revision': 2, 'confirm_code': item['code']}
    assert client.request('DELETE', path, json=body).status_code == 401
    me = v6.session(client, 'viewer').json()['data']
    assert client.request('DELETE', path, headers={'x-rb-csrf': me['csrf']}, json=body).status_code == 403
    with database() as db:
        db.execute("UPDATE users SET role='admin'")
    assert client.request('DELETE', path, json=body).status_code == 403
    assert client.request('DELETE', path, headers={'x-rb-csrf': me['csrf'], 'origin': 'https://evil.test'},
                          json=body).status_code == 403
    assert client.request('DELETE', path, headers={'x-rb-csrf': me['csrf']}, json=body).status_code == 200
