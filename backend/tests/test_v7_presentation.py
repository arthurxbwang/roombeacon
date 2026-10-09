"""V7 presentation is versioned independently of Android and release permissions."""
import json

import pytest

from app.management.catalog_models import HardwareSpec, SoftwareSpec
from app.management.deployments import installation_config

from . import test_v6_management as v6
from .test_configuration_catalog import BASE, create, publish

client = v6.client


def test_v7_catalog_publication_and_validation(client):
    item = publish(client, create(client, spec={'display_version': 'v7'}))
    assert item['spec']['display_version'] == 'v7'
    assert item['spec']['rules']['owner'] == 'official'
    assert item['spec']['rules']['mode'] == 'off'
    assert client.post(BASE, headers=v6.admin(), json={
        'kind': 'software', 'name': '非法版本', 'spec': {'display_version': 'v99'}}).status_code == 422
    assert create(client)['spec']['display_version'] == 'v6'


def test_v7_presentation_preserves_android_entry_and_rules():
    device = {'config': '{}', 'metadata': json.dumps({'config_schema': 3})}
    hardware = {'spec': HardwareSpec().model_dump()}
    software = {'spec': SoftwareSpec(display_version='v7').model_dump()}
    config = installation_config(device, hardware, software)
    assert config['version'] == 'v6'
    assert config['presentation']['display_version'] == 'v7'
    assert 'rules' not in config['presentation']


def test_v7_roundtrips_through_schedule_preferences():
    from app.schemas.meeting_room import DisplayPreferences
    assert DisplayPreferences(**SoftwareSpec(display_version='v7').model_dump()).display_version == 'v7'
    assert DisplayPreferences().display_version == 'v6'


@pytest.mark.asyncio
async def test_release_hint_requires_server_write_authority(monkeypatch):
    from unittest.mock import AsyncMock

    from app.core.config import settings
    from app.schemas.room_usage import UsagePolicy
    from app.services import room_usage

    policy = UsagePolicy(owner='v5', mode='auto', native_policy_cleared=True, release_verified=True)
    monkeypatch.setattr(room_usage, 'policy_for', AsyncMock(return_value=policy.model_dump()))
    monkeypatch.setattr(room_usage, 'fresh_target', AsyncMock(return_value=None))
    monkeypatch.setattr(room_usage, 'fresh_monitor_targets', AsyncMock(return_value=[]))
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_ENABLED', True)
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_RELEASE_ROOM_IDS', {'omm_test'})
    store = AsyncMock()
    store.get.return_value = False
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_WRITES_ENABLED', False)
    assert not (await room_usage.view(store, 'omm_test'))['release_enabled']
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_WRITES_ENABLED', True)
    assert (await room_usage.view(store, 'omm_test'))['release_enabled']
    assert not (await room_usage.view(store, 'omm_other'))['release_enabled']
    store.get.return_value = True
    assert not (await room_usage.view(store, 'omm_test'))['release_enabled']


@pytest.mark.parametrize('enabled', [True, False])
def test_deployed_v7_reaches_authenticated_device_and_control_preview(client, monkeypatch, enabled):
    from datetime import UTC, datetime, timedelta
    from unittest.mock import AsyncMock

    from app import room_display_main
    from app.core.config import settings
    from app.management import deployments
    from app.management.security import DEVICE_COOKIE
    from app.schemas.meeting_room import Room, RoomSchedule

    monkeypatch.setattr(deployments, 'cached_directory', AsyncMock(return_value=[
        {'room_id': v6.ROOM, 'name': 'V7 模拟房间'}]))
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_ENABLED', False)
    now = datetime.now(UTC)
    snapshot = RoomSchedule(room=Room(room_id=v6.ROOM, name='V7 模拟房间'), events=[],
                            synced_at=now, valid_until=now + timedelta(minutes=5))
    monkeypatch.setattr(room_display_main, 'schedule_for', AsyncMock(return_value=snapshot))
    token, device = v6.enroll(client)
    hardware = publish(client, create(client, 'hardware'))
    software = publish(client, create(client, spec={'display_version': 'v7', 'checkin_enabled': enabled}))
    body = {'device_id': device['id'], 'expected_revision': 1, 'room_id': v6.ROOM,
            'hardware_id': hardware['id'], 'hardware_version': 1,
            'software_id': software['id'], 'software_version': 1, 'expected_room_revision': 0}
    assert client.post('/api/v6/admin/deployments', headers=v6.admin(), json=body).status_code == 200
    session = v6.web_cookie(client, token, reported_revision=2)
    client.cookies.set(DEVICE_COOKIE, session['web_session'])
    data = client.get('/api/meeting-rooms/display').json()['data']
    assert data['display_preferences']['display_version'] == 'v7'
    assert data['display_preferences']['checkin_enabled'] is enabled
    assert snapshot.display_preferences is None
    data = client.get('/api/room-control/preview', headers=v6.admin(), params={'room_id': v6.ROOM}).json()['data']
    assert data['display_preferences']['display_version'] == 'v7'
    assert data['display_preferences']['checkin_enabled'] is enabled
    client.cookies.delete(DEVICE_COOKIE)
    assert client.get('/api/meeting-rooms/display').status_code == 401
