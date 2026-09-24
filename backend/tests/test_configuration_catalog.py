"""Configuration provenance, immutable versions and deployment boundaries."""
from unittest.mock import AsyncMock

import pytest

from . import test_v6_management as v6

client = v6.client
BASE = '/api/v6/admin/catalog'


def create(client, kind='software', spec=None):
    response = client.post(BASE, headers=v6.admin(), json={
        'kind': kind, 'name': '测试模板', 'spec': spec or {}})
    assert response.status_code == 200, response.text
    return response.json()['data']


def publish(client, item):
    response = client.post(f"{BASE}/{item['id']}/publish", headers=v6.admin(),
                           json={'expected_revision': item['revision']})
    assert response.status_code == 200, response.text
    return response.json()['data']


def test_published_versions_survive_draft_edits(client):
    item = publish(client, create(client))
    response = client.put(f"{BASE}/{item['id']}", headers=v6.admin(), json={
        'expected_revision': item['revision'], 'kind': 'software',
        'name': '新版', 'spec': {'language': 'en'}})
    assert response.status_code == 200, response.text
    row = next(r for r in client.get(BASE, headers=v6.admin()).json()['data'] if r['id'] == item['id'])
    assert row['versions'][0]['spec']['language'] == 'zh-CN'
    assert row['spec']['language'] == 'en'
    assert row['published_version'] == 1
    assert client.post(f"{BASE}/{item['id']}/publish", headers=v6.admin(),
                       json={'expected_revision': item['revision']}).status_code == 409


def test_catalog_requires_admin_and_csrf(client):
    assert client.get(BASE).status_code == 401
    me = v6.session(client, 'viewer').json()['data']
    assert client.get(BASE).status_code == 200
    assert client.post(BASE, headers={'x-rb-csrf': me['csrf']}, json={
        'kind': 'software', 'name': '不允许', 'spec': {}}).status_code == 403


@pytest.mark.parametrize('spec', [{'pins': {'red': 116, 'green': 148, 'blue': 147}},
                                 {'active_level': 2}, {'width': -1}])
def test_unsupported_wiring_rejected(client, spec):
    assert client.post(BASE, headers=v6.admin(), json={
        'kind': 'hardware', 'name': '非法', 'spec': spec}).status_code == 422


def test_read_catalog_preserves_device_revision_and_config(client):
    from app.management.store import database
    _, device = v6.enroll(client)
    v6.configure(client, device['id'])
    with database() as db:
        before = tuple(db.execute('SELECT config,revision,room_id FROM devices').fetchone())
    assert client.get(BASE, headers=v6.admin()).status_code == 200
    with database() as db:
        after = tuple(db.execute('SELECT config,revision,room_id FROM devices').fetchone())
    assert before == after


def test_deployment_persists_references_and_no_upstream_write(client, monkeypatch):
    from app.management import deployments
    monkeypatch.setattr(deployments, 'cached_directory', AsyncMock(return_value=[
        {'room_id': v6.ROOM, 'name': '测试会议室', 'region': '北京', 'location': '北京 / 7F'}]))
    _, device = v6.enroll(client)
    hardware = publish(client, create(client, 'hardware', {'room_light': False}))
    software = publish(client, create(client))
    body = {'device_id': device['id'], 'expected_revision': 1, 'room_id': v6.ROOM,
            'hardware_id': hardware['id'], 'hardware_version': 1,
            'software_id': software['id'], 'software_version': 1,
            'expected_room_revision': 0}
    response = client.post('/api/v6/admin/deployments', headers=v6.admin(), json=body)
    assert response.status_code == 200, response.text
    data = client.get('/api/v6/admin/configuration', headers=v6.admin()).json()['data']
    assert data['devices'][device['id']]['hardware_id'] == hardware['id']
    assert data['rooms'][v6.ROOM]['software_id'] == software['id']
    assert data['deployments'][0]['state'] == 'waiting'
    assert client.post('/api/v6/admin/deployments', headers=v6.admin(), json=body).status_code == 409


def test_software_cannot_copy_room_qualifications(client):
    assert client.post(BASE, headers=v6.admin(), json={
        'kind': 'software', 'name': '非法资格', 'spec': {'rules': {'release_verified': True}}}
    ).status_code == 422


def test_adopt_effective_configuration_without_changing_device(client, monkeypatch):
    from app.management import configuration_migration
    from app.management.store import database
    monkeypatch.setattr(configuration_migration, 'cached_directory', AsyncMock(return_value=[
        {'room_id': v6.ROOM, 'name': '测试会议室', 'location': '北京 / 7F'}]))
    _, device = v6.enroll(client)
    v6.configure(client, device['id'], config={'room_light': False, 'language': 'en'})
    with database() as db:
        before = tuple(db.execute('SELECT secret_hash,room_id,config,revision FROM devices').fetchone())
    result = client.post(f"/api/v6/admin/devices/{device['id']}/adopt", headers=v6.admin(),
                         json={'expected_revision': 2})
    assert result.status_code == 200, result.text
    with database() as db:
        after = tuple(db.execute('SELECT secret_hash,room_id,config,revision FROM devices').fetchone())
    assert before == after
    state = client.get('/api/v6/admin/configuration', headers=v6.admin()).json()['data']
    assert state['rooms'][v6.ROOM]['software_id'] == result.json()['data']['software_id']


def test_asset_authorization_validation_and_missing_reference(client):
    assert client.post('/api/v6/admin/assets', json={'name': 'x', 'data': 'x'}).status_code == 401
    assert client.post('/api/v6/admin/assets', headers=v6.admin(), json={
        'name': 'x', 'data': 'PHN2Zz48L3N2Zz4='}).status_code == 422
    template = create(client, spec={'background_day': 'a' * 64})
    assert client.post(f"{BASE}/{template['id']}/publish", headers=v6.admin(),
                       json={'expected_revision': 1}).status_code == 422


def test_installation_capabilities_and_custom_pins(client):
    import json

    from app.core.exceptions import AppError
    from app.management.catalog_models import HardwareSpec, SoftwareSpec
    from app.management.deployments import installation_config
    device = {'config': '{}', 'metadata': json.dumps({'config_schema': 2})}
    hw = {'spec': HardwareSpec(room_light=True, pins={'red': 147, 'green': 148, 'blue': 154}).model_dump()}
    sw = {'spec': SoftwareSpec().model_dump()}
    with pytest.raises(AppError, match='协议 3'):
        installation_config(device, hw, sw)
    device['metadata'] = json.dumps({'config_schema': 3, 'light_supported': True})
    assert installation_config(device, hw, sw)['light_wiring']['pins']['red'] == 147
    sw['spec']['min_width'] = 1280
    with pytest.raises(AppError, match='未上报网页尺寸'):
        installation_config(device, hw, sw)
    device['metadata'] = json.dumps({'config_schema': 3, 'light_supported': True,
                                     'screen': {'viewport_width': 1280, 'viewport_height': 720}})
    assert installation_config(device, hw, sw)['room_light'] is True


def test_room_scope_retains_node_identity():
    from app.services.room_display_directory import directory_rows
    row = directory_rows([{'room_id': 'omm_one', 'name': '同名', 'path': ['org', 'cn', 'bj', 'a']}],
                         {'org': '公司', 'cn': '中国', 'bj': '北京', 'a': 'A座'})[0]
    assert row['region_id'] == 'bj'
    assert row['location_nodes'][-1] == {'id': 'a', 'name': 'A座'}


def test_uploaded_png_requires_assigned_device_or_admin(client, monkeypatch):
    import base64
    import struct
    import zlib

    from app.management import deployments
    from app.management.security import DEVICE_COOKIE
    def chunk(kind, content):
        return struct.pack('>I', len(content)) + kind + content + struct.pack('>I', zlib.crc32(kind + content))
    png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00')) + chunk(b'IEND', b'')
    response = client.post('/api/v6/admin/assets', headers=v6.admin(), json={
        'name': 'red.png', 'data': base64.b64encode(png).decode()})
    assert response.status_code == 200, response.text
    asset = response.json()['data']['id']
    path = '/api/v6/assets/' + asset
    assert client.get(path).status_code == 401
    assert client.get(path, headers=v6.admin()).content == png
    monkeypatch.setattr(deployments, 'cached_directory', AsyncMock(return_value=[{'room_id': v6.ROOM, 'name': '测试'}]))
    token, device = v6.enroll(client)
    hw = publish(client, create(client, 'hardware'))
    sw = publish(client, create(client, spec={'background_day': asset}))
    body = {'device_id': device['id'], 'expected_revision': 1, 'room_id': v6.ROOM,
            'hardware_id': hw['id'], 'hardware_version': 1, 'software_id': sw['id'],
            'software_version': 1, 'expected_room_revision': 0}
    assert client.post('/api/v6/admin/deployments', headers=v6.admin(), json=body).status_code == 200
    client.cookies.set(DEVICE_COOKIE, v6.web_cookie(client, token)['web_session'])
    assert client.get(path).content == png
    assert client.get('/api/v6/assets/' + 'a' * 64).status_code == 403
