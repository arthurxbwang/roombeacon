"""Editable templates, snapshot delivery and authorization failure boundaries."""
import pytest

from . import test_v6_management as v6

client = v6.client
admin, configure, enroll, session = v6.admin, v6.configure, v6.enroll, v6.session


def create(client, **extra):
    return client.post('/api/v6/admin/templates', headers=admin(),
                       json={'name': 'BX68 横版', 'config': {}} | extra)


def test_template_edit_conflict_and_no_implicit_publish(client):
    _, device = enroll(client)
    template = create(client).json()['data']
    assert template['revision'] == 1
    body = {'expected_revision': 1, 'name': 'BX68 竖版', 'config': {'portrait': True}}
    url = '/api/v6/admin/templates/' + template['id']
    assert client.put(url, headers=admin(), json=body).status_code == 200
    assert client.put(url, headers=admin(), json=body).status_code == 409
    rows = client.get('/api/v6/admin/devices', headers=admin()).json()['data']
    assert rows[0]['revision'] == 1
    assert configure(client, device['id'], template_id=template['id'], template_revision=1).status_code == 409
    result = configure(client, device['id'], template_id=template['id'], template_revision=2)
    assert result.status_code == 200
    config = result.json()['data']['config']
    assert config['portrait'] is True


@pytest.mark.parametrize('config', [{'device_profile': 'invalid'}, {'gpio': 116}])
def test_invalid_hardware_template(client, config):
    assert create(client, config=config).status_code == 422


def test_batch_uses_saved_template_and_stale_version_is_atomic(client):
    _, a = enroll(client)
    _, b = enroll(client)
    configure(client, a['id'])
    configure(client, b['id'])
    template = create(client, config={'portrait': True, 'language': 'en'}).json()['data']
    body = {'devices': {a['id']: 2, b['id']: 2}, 'config': {'portrait': False},
            'template_id': template['id'], 'template_revision': 99}
    assert client.post('/api/v6/admin/batch-config', headers=admin(), json=body).status_code == 409
    rows = client.get('/api/v6/admin/devices', headers=admin()).json()['data']
    assert all(row['revision'] == 2 for row in rows)
    body['template_revision'] = 1
    assert client.post('/api/v6/admin/batch-config', headers=admin(), json=body).status_code == 200
    rows = client.get('/api/v6/admin/devices', headers=admin()).json()['data']
    assert all(row['config']['portrait'] and row['config']['language'] == 'en' for row in rows)


def test_template_update_requires_auth_csrf_and_admin(client):
    template = create(client).json()['data']
    url = '/api/v6/admin/templates/' + template['id']
    body = {'expected_revision': 1, 'name': '模板', 'config': {}}
    assert client.put(url, json=body).status_code == 401
    me = session(client, 'viewer').json()['data']
    assert client.get('/api/v6/admin/templates').status_code == 200
    assert client.put(url, headers={'x-rb-csrf': me['csrf']}, json=body).status_code == 403


def test_blank_name_and_missing_template(client):
    assert create(client, name='   ').status_code == 422
    assert client.put('/api/v6/admin/templates/missing', headers=admin(), json={
        'expected_revision': 1, 'name': '模板', 'config': {}}).status_code == 404


def test_legacy_template_has_revision_and_edit_requires_csrf(client):
    from app.management.store import database
    with database() as db:
        db.execute('INSERT INTO templates VALUES (?,?,?)', ('old', '旧模板', '{"portrait": true}'))
    row = client.get('/api/v6/admin/templates', headers=admin()).json()['data'][0]
    assert row['revision'] == 1 and row['config']['portrait'] is True
    session(client, 'admin')
    assert client.put('/api/v6/admin/templates/old', json={
        'expected_revision': 1, 'name': '改名', 'config': {}}).status_code == 403
