"""型号模板、兼容默认和批量失败边界。"""
import pytest

from tests import test_v6_management as shared
from tests.test_v6_management import admin, configure, enroll, web_cookie

client = shared.client

BX = {'model': 'RK3568', 'firmware': 'RK3568_BX68_Android 11_64-20260331.094925_ZX-keys',
      'config_schema': 2, 'light_supported': True}


def test_template_roundtrip_and_invalid_modes(client):
    config = {'device_profile': 'bx68', 'theme_mode': 'light', 'language': 'en', 'room_light': True}
    assert client.post('/api/v6/admin/templates', headers=admin(),
                       json={'name': '1080P', 'config': config}).status_code == 200
    saved = client.get('/api/v6/admin/templates', headers=admin()).json()['data'][0]
    assert all(saved['config'][key] == value for key, value in config.items())
    for bad in [{'theme_mode': 'dark'}, {'language': 'xx'}, {'device_profile': 'other'},
                {'device_profile': 'generic', 'room_light': True}, {'gpio': 116}]:
        assert client.post('/api/v6/admin/templates', headers=admin(),
                           json={'name': 'bad', 'config': config | bad}).status_code == 422


def test_profile_match_and_atomic_batch(client):
    token, a = enroll(client)
    _, b = enroll(client)
    configure(client, a['id']); configure(client, b['id'])
    web_cookie(client, token, metadata=BX)
    config = {'device_profile': 'bx68', 'theme_mode': 'light', 'language': 'en'}
    result = client.post('/api/v6/admin/batch-config', headers=admin(),
                         json={'devices': {a['id']: 2, b['id']: 2}, 'config': config})
    assert result.status_code == 422
    rows = client.get('/api/v6/admin/devices', headers=admin()).json()['data']
    assert all(row['revision'] == 2 for row in rows)
    assert configure(client, a['id'], 2, config=config).status_code == 200
    assert web_cookie(client, token, metadata=BX)['config']['theme_mode'] == 'light'
    assert configure(client, b['id'], 2, config=config).status_code == 422


@pytest.mark.parametrize('change', [{'firmware': ''}, {'firmware': 'custom'}, {'config_schema': 1}])
def test_same_model_only_needs_normal_notice(client, change):
    token, item = enroll(client)
    web_cookie(client, token, metadata=BX | change)
    assert configure(client, item['id'], config={'device_profile': 'bx68', 'room_light': False}).status_code == 200


def test_mismatch_force_is_explicit_and_audited_without_sticking(client):
    token, item = enroll(client)
    config = {'device_profile': 'bx68'}
    assert configure(client, item['id'], config=config).status_code == 422
    assert configure(client, item['id'], config=config, confirm_model_mismatch=True).status_code == 200
    assert configure(client, item['id'], 2, config=config).status_code == 422
    result = client.post(f"/api/v6/admin/devices/{item['id']}/reload", headers=admin(),
                         json={'expected_revision': 2})
    assert result.status_code == 200
    assert 'confirm_model_mismatch' not in web_cookie(client, token)['config']
    audit = client.get('/api/v6/admin/audit', headers=admin()).json()['data']
    entry = next(row for row in audit if row['action'] == 'configure')
    assert entry['detail']['model_override'] is True
    assert entry['detail']['device_profile'] == 'bx68'


def test_force_batch_still_checks_revisions_and_preserves_bindings(client):
    token, a = enroll(client)
    _, b = enroll(client)
    configure(client, a['id']); configure(client, b['id'])
    web_cookie(client, token, metadata=BX)
    body = {'devices': {a['id']: 2, b['id']: 1}, 'config': {'device_profile': 'bx68'},
            'confirm_model_mismatch': True}
    assert client.post('/api/v6/admin/batch-config', headers=admin(), json=body).status_code == 409
    body['devices'][b['id']] = 2
    assert client.post('/api/v6/admin/batch-config', headers=admin(), json=body).status_code == 200
    rows = client.get('/api/v6/admin/devices', headers=admin()).json()['data']
    assert all(row['revision'] == 3 and row['room_id'] == 'omm_test' for row in rows)
    assert all(row['config']['device_profile'] == 'bx68' for row in rows)


def test_catalog_requires_manager_and_legacy_defaults(client):
    assert client.get('/api/v6/admin/device-profiles').status_code == 401
    catalog = client.get('/api/v6/admin/device-profiles', headers=admin()).json()['data']
    bx = next(p for p in catalog if p['id'] == 'bx68')
    assert bx['pins'] == {'red': 148, 'green': 154, 'blue': 147} and bx['active_level'] == 0
    token, item = enroll(client)
    assert configure(client, item['id']).status_code == 200
    config = web_cookie(client, token)['config']
    assert config['theme_mode'] == 'auto' and config['language'] == 'zh-CN'


def test_preferences_delivered_only_to_authenticated_device_without_mutating_cache(client, monkeypatch):
    from datetime import UTC, datetime, timedelta
    from unittest.mock import AsyncMock

    from app import room_display_main
    from app.core.config import settings
    from app.management.security import DEVICE_COOKIE
    from app.schemas.meeting_room import Room, RoomSchedule

    now = datetime.now(UTC)
    snapshot = RoomSchedule(room=Room(room_id='omm_test', name='测试'), events=[],
                            synced_at=now, valid_until=now + timedelta(minutes=5))
    monkeypatch.setattr(room_display_main, 'schedule_for', AsyncMock(return_value=snapshot))
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_ENABLED', False)
    token, item = enroll(client)
    configure(client, item['id'], config={'theme_mode': 'light', 'language': 'en'})
    value = web_cookie(client, token)
    client.cookies.set(DEVICE_COOKIE, value['web_session'])
    result = client.get('/api/meeting-rooms/display')
    assert result.status_code == 200
    assert result.json()['data']['display_preferences'] == {'theme_mode': 'light', 'language': 'en'}
    assert snapshot.display_preferences is None
    assert configure(client, item['id'], 2, status='revoked').status_code == 200
    assert client.get('/api/meeting-rooms/display').status_code == 401


def test_rollback_rechecks_hardware_and_preserves_room(client):
    token, item = enroll(client)
    web_cookie(client, token, metadata=BX)
    assert configure(client, item['id'], config={'device_profile': 'bx68'}).status_code == 200
    assert configure(client, item['id'], 2, config={'device_profile': 'generic', 'room_light': False}).status_code == 200
    web_cookie(client, token, metadata=BX | {'model': 'special'})
    response = client.post(f"/api/v6/admin/devices/{item['id']}/rollback", headers=admin(),
                           json={'expected_revision': 3, 'revision': 2})
    assert response.status_code == 422
    rows = client.get('/api/v6/admin/devices', headers=admin()).json()['data']
    assert rows[0]['revision'] == 3 and rows[0]['config']['device_profile'] == 'generic'
    response = client.post(f"/api/v6/admin/devices/{item['id']}/rollback", headers=admin(),
                           json={'expected_revision': 3, 'revision': 2, 'confirm_model_mismatch': True})
    assert response.status_code == 200
    assert response.json()['data']['config']['device_profile'] == 'bx68'


def test_firmware_change_does_not_prevent_revocation(client):
    token, item = enroll(client)
    web_cookie(client, token, metadata=BX)
    assert configure(client, item['id'], config={'device_profile': 'bx68'}).status_code == 200
    web_cookie(client, token, metadata=BX | {'firmware': 'changed'})
    assert configure(client, item['id'], 2, status='revoked', config={'device_profile': 'bx68'}).status_code == 200
    assert 'web_session' not in web_cookie(client, token)


def test_older_apk_ack_does_not_claim_template_light_applied(client):
    token, item = enroll(client)
    assert configure(client, item['id'], config={'device_profile': 'bx68'},
                     confirm_model_mismatch=True).status_code == 200
    web_cookie(client, token, reported_revision=2)
    row = client.get('/api/v6/admin/devices', headers=admin()).json()['data'][0]
    assert '升级 APK' in row['error']
    web_cookie(client, token, reported_revision=2, metadata=BX)
    row = client.get('/api/v6/admin/devices', headers=admin()).json()['data'][0]
    assert row['error'] == ''


def test_confirmation_cannot_bypass_authorization_or_be_saved_in_template(client):
    from tests.test_v6_management import session

    _, item = enroll(client)
    body = {'expected_revision': 1, 'status': 'active', 'room_id': 'omm_test',
            'config': {'device_profile': 'bx68'}, 'confirm_model_mismatch': True}
    assert client.put('/api/v6/admin/devices/' + item['id'], json=body).status_code == 401
    assert client.put('/api/v6/admin/devices/' + item['id'], headers=admin(),
                      json=body | {'confirm_model_mismatch': 'yes'}).status_code == 422
    assert client.post('/api/v6/admin/templates', headers=admin(),
                       json={'name': 'bad', 'config': body['config'] | {'confirm_model_mismatch': True}}).status_code == 422
    csrf = session(client, 'viewer').json()['data']['csrf']
    assert client.put('/api/v6/admin/devices/' + item['id'], headers={'x-rb-csrf': csrf}, json=body).status_code == 403
