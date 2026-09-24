"""Deployment failures must preserve assignments and never grant release authority."""
import json
from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.management import configuration_delivery, deployment_batch, deployments
from app.management.store import database
from app.schemas.room_usage import UsagePolicy

from . import test_v6_management as v6
from .test_configuration_catalog import create, publish

client = v6.client


def directory(monkeypatch):
    rows = [{'room_id': v6.ROOM, 'name': '测试一'}, {'room_id': 'omm_second', 'name': '测试二'}]
    monkeypatch.setattr(deployments, 'cached_directory', AsyncMock(return_value=rows))
    monkeypatch.setattr(deployment_batch, 'cached_directory', AsyncMock(return_value=rows))
    monkeypatch.setattr(v6.devices, 'cached_directory', AsyncMock(return_value=rows))


def request(device, hw, sw, **extra):
    return {'device_id': device['id'], 'expected_revision': 1, 'room_id': v6.ROOM,
            'hardware_id': hw['id'], 'hardware_version': 1, 'software_id': sw['id'], 'software_version': 1,
            'expected_room_revision': 0} | extra


def test_stale_batch_does_not_partly_change_other_devices(client, monkeypatch):
    directory(monkeypatch)
    _, first = v6.enroll(client)
    _, second = v6.enroll(client)
    v6.configure(client, first['id'], config={'room_light': False})
    v6.configure(client, second['id'], room_id='omm_second', config={'room_light': False})
    hw, sw = publish(client, create(client, 'hardware')), publish(client, create(client))
    body = {'devices': {first['id']: 2, second['id']: 99}, 'room_revisions': {v6.ROOM: 0, 'omm_second': 0},
            'hardware_id': hw['id'], 'hardware_version': 1, 'software_id': sw['id'], 'software_version': 1}
    result = client.post('/api/v6/admin/deployment-batches', headers=v6.admin(), json=body)
    assert result.status_code == 409
    with database() as db:
        assert all(row['revision'] == 2 for row in db.execute('SELECT revision FROM devices'))
        assert not db.execute('SELECT 1 FROM room_configurations').fetchone()
    body['devices'][second['id']] = 2
    result = client.post('/api/v6/admin/deployment-batches', headers=v6.admin(), json=body)
    assert result.status_code == 200, result.text
    assert result.json()['data']['updated'] == 2


def test_refresh_keeps_template_history_and_partial_ack_is_not_success(client, monkeypatch):
    directory(monkeypatch)
    token, device = v6.enroll(client)
    hw, sw = publish(client, create(client, 'hardware')), publish(client, create(client))
    assert client.post('/api/v6/admin/deployments', headers=v6.admin(), json=request(device, hw, sw)).status_code == 200
    with database() as db:
        before = tuple(db.execute('SELECT * FROM configuration_deployments').fetchone())
    client.post(f"/api/v6/admin/devices/{device['id']}/reload", headers=v6.admin(), json={'expected_revision': 2})
    v6.web_cookie(client, token, reported_revision=3, error='灯控失败')
    state = client.get('/api/v6/admin/configuration', headers=v6.admin()).json()['data']
    assert state['deployments'][0]['state'] == 'partial'
    with database() as db:
        assert before == tuple(db.execute('SELECT * FROM configuration_deployments').fetchone())
    assert v6.configure(client, device['id'], revision=3).status_code == 409


@pytest.mark.asyncio
async def test_template_cannot_enable_unverified_room_release(client, monkeypatch):
    directory(monkeypatch)
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_ENABLED', True)
    token, device = v6.enroll(client)
    hw = publish(client, create(client, 'hardware'))
    sw = publish(client, create(client, spec={'rules': {'owner': 'v5', 'mode': 'auto'}}))
    response = client.post('/api/v6/admin/deployments', headers=v6.admin(), json=request(device, hw, sw))
    assert response.status_code == 200, response.text
    v6.web_cookie(client, token, reported_revision=2)
    store = AsyncMock()
    store.get.return_value = UsagePolicy().model_dump()
    save = AsyncMock()
    monkeypatch.setattr(configuration_delivery, 'save_policy', save)
    await configuration_delivery.reconcile_room(store, v6.ROOM)
    save.assert_not_called()
    with database() as db:
        row = db.execute('SELECT * FROM room_configurations').fetchone()
        assert row['policy_state'] == 'blocked'
        assert '核对' in row['error']
        assert 'release_verified' not in json.loads(row['rules'])


@pytest.mark.asyncio
async def test_matching_room_policy_is_not_rewritten(client, monkeypatch):
    directory(monkeypatch)
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_ENABLED', True)
    _, device = v6.enroll(client)
    hw, sw = publish(client, create(client, 'hardware')), publish(client, create(client))
    client.post('/api/v6/admin/deployments', headers=v6.admin(), json=request(device, hw, sw))
    store = AsyncMock()
    store.get.return_value = UsagePolicy(revision='keep-this-revision').model_dump()
    save = AsyncMock()
    monkeypatch.setattr(configuration_delivery, 'save_policy', save)
    await configuration_delivery.reconcile_room(store, v6.ROOM)
    save.assert_not_called()
    with database() as db:
        assert db.execute('SELECT policy_revision FROM room_configurations').fetchone()[0] == 'keep-this-revision'


def test_legacy_devices_in_same_room_can_adopt_without_revision_change(client, monkeypatch):
    from app.management import configuration_migration
    directory(monkeypatch)
    monkeypatch.setattr(configuration_migration, 'cached_directory', deployments.cached_directory)
    _, first = v6.enroll(client)
    _, second = v6.enroll(client)
    for device in (first, second):
        v6.configure(client, device['id'], config={'room_light': False})
        response = client.post(f"/api/v6/admin/devices/{device['id']}/adopt", headers=v6.admin(),
                               json={'expected_revision': 2})
        assert response.status_code == 200, response.text
    with database() as db:
        assert db.execute('SELECT count(*) FROM room_configurations').fetchone()[0] == 1
        assert db.execute('SELECT count(*) FROM device_installations').fetchone()[0] == 2
        assert all(row[0] == 2 for row in db.execute('SELECT revision FROM devices'))
    hw, sw = publish(client, create(client, 'hardware')), publish(client, create(client))
    body = request(first, hw, sw, expected_revision=2, room_id='omm_second')
    assert client.post('/api/v6/admin/deployments', headers=v6.admin(), json=body).status_code == 422


def test_moving_only_controller_clears_old_room_reference(client, monkeypatch):
    directory(monkeypatch)
    _, device = v6.enroll(client)
    hw, sw = publish(client, create(client, 'hardware')), publish(client, create(client))
    body = request(device, hw, sw)
    assert client.post('/api/v6/admin/deployments', headers=v6.admin(), json=body).status_code == 200
    body.update(expected_revision=2, room_id='omm_second')
    assert client.post('/api/v6/admin/deployments', headers=v6.admin(), json=body).status_code == 200
    with database() as db:
        assert db.execute('SELECT controller_id FROM room_configurations WHERE room_id=?', (v6.ROOM,)).fetchone()[0] == ''


@pytest.mark.asyncio
@pytest.mark.parametrize('legacy', [False, True])
async def test_directory_name_failure_retains_previous_location_tree(legacy):
    from datetime import UTC, datetime

    from app.services.room_display_collector import DIRECTORY, refresh_directory
    from app.services.room_display_directory import directory_rows
    raw = [{'room_id': v6.ROOM, 'name': '测试', 'path': ['org', 'cn', 'bj', 'a']}]
    previous = directory_rows(raw, {'org': '公司', 'cn': '中国', 'bj': '北京', 'a': 'A座'})
    if legacy:
        previous[0].pop('location_nodes')
        previous[0].pop('region_id')
    cache = AsyncMock()
    cache.get.side_effect = lambda key: json.dumps(previous) if key == DIRECTORY else '0'
    upstream = AsyncMock()
    upstream.list_rooms.return_value = raw
    upstream.room_levels.side_effect = TimeoutError('mock upstream unavailable')
    rows = await refresh_directory(cache, upstream, datetime.now(UTC))
    for key in ('location', 'region', 'floor', 'location_nodes', 'region_id'):
        assert rows[0].get(key) == previous[0].get(key)
