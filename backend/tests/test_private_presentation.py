"""Private templates omit titles only on the configured terminal response."""
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.management.store import database
from app.schemas.meeting_room import Room, RoomEvent, RoomSchedule

from . import test_v6_management as v6
from .test_configuration_catalog import create, publish

client = v6.client


def test_private_builtin_is_additive_and_idempotent(client):
    items = client.get('/api/v6/admin/catalog', headers=v6.admin()).json()['data']
    private = next(t for t in items if t['id'] == 'builtin-software-private-checkin')
    normal = next(t for t in items if t['name'] == '签到版')
    assert private['name'] == '签到保密版'
    assert private['published_version'] == 1 and not private['retired']
    assert private['spec'] == normal['spec'] | {'show_meeting_titles': False}
    with database() as db:
        before = [tuple(r) for r in db.execute('SELECT * FROM config_versions')]
        count = db.execute('SELECT COUNT(*) FROM audit').fetchone()[0]
    client.get('/api/v6/admin/catalog', headers=v6.admin())
    with database() as db:
        assert [tuple(r) for r in db.execute('SELECT * FROM config_versions')] == before
        assert db.execute('SELECT COUNT(*) FROM audit').fetchone()[0] == count


@pytest.mark.parametrize('show_titles', [True, False])
def test_deployed_title_preference_redacts_device_only(client, monkeypatch, show_titles):
    from app import room_display_main
    from app.core.config import settings
    from app.management import deployments
    from app.management.security import DEVICE_COOKIE

    monkeypatch.setattr(deployments, 'cached_directory', AsyncMock(return_value=[
        {'room_id': v6.ROOM, 'name': '保密模拟房间'}]))
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_ENABLED', False)
    now = datetime.now(UTC)
    event = RoomEvent(uid='private-fixture', start_time=now, end_time=now + timedelta(hours=1),
                      organizer='测试组织者', summary='保密模拟主题')
    snapshot = RoomSchedule(room=Room(room_id=v6.ROOM, name='保密模拟房间'), events=[event],
                            synced_at=now, valid_until=now + timedelta(minutes=5))
    monkeypatch.setattr(room_display_main, 'schedule_for', AsyncMock(return_value=snapshot))
    token, device = v6.enroll(client)
    hardware = publish(client, create(client, 'hardware'))
    spec = {'display_version': 'v7'} if show_titles else {'display_version': 'v7', 'show_meeting_titles': False}
    software = publish(client, create(client, spec=spec))
    body = {'device_id': device['id'], 'expected_revision': 1, 'room_id': v6.ROOM,
            'hardware_id': hardware['id'], 'hardware_version': 1,
            'software_id': software['id'], 'software_version': 1, 'expected_room_revision': 0}
    assert client.post('/api/v6/admin/deployments', headers=v6.admin(), json=body).status_code == 200
    cookie = v6.web_cookie(client, token, reported_revision=2)['web_session']
    client.cookies.set(DEVICE_COOKIE, cookie)
    response = client.get('/api/meeting-rooms/display')
    data = response.json()['data']
    assert response.headers['cache-control'] == 'no-store'
    assert data['display_preferences']['show_meeting_titles'] is show_titles
    assert data['events'][0]['summary'] == ('保密模拟主题' if show_titles else None)
    assert data['titles_available'] is show_titles
    assert data['events'][0]['organizer'] == '测试组织者'
    assert data['room']['name'] == '保密模拟房间'
    assert snapshot.events[0].summary == '保密模拟主题'
    assert snapshot.display_preferences is None and snapshot.titles_available
    preview = client.get('/api/room-control/preview', headers=v6.admin(), params={'room_id': v6.ROOM}).json()['data']
    assert preview['events'][0]['summary'] == '保密模拟主题'
    assert preview['display_preferences']['show_meeting_titles'] is show_titles
    client.cookies.delete(DEVICE_COOKIE)
    assert client.get('/api/meeting-rooms/display').status_code == 401
    with database() as db:
        config = json.loads(db.execute('SELECT config FROM devices WHERE id=?', (device['id'],)).fetchone()[0])
        config['presentation']['show_meeting_titles'] = not show_titles
        db.execute('UPDATE devices SET config=?,revision=revision+1 WHERE id=?', (json.dumps(config), device['id']))
    client.cookies.set(DEVICE_COOKIE, cookie)
    assert client.get('/api/meeting-rooms/display').status_code == 401


def test_add_private_template_keeps_effective_records(client):
    from app.management.private_template import KEY, add_private_template
    _, device = v6.enroll(client)
    v6.configure(client, device['id'])
    with database() as db:
        db.execute('DELETE FROM meta WHERE key=?', (KEY,))
        db.execute("DELETE FROM config_versions WHERE template_id='builtin-software-private-checkin'")
        db.execute("DELETE FROM config_catalog WHERE id='builtin-software-private-checkin'")
        before = {table: [tuple(r) for r in db.execute('SELECT * FROM ' + table)] for table in
                  ['devices', 'history', 'room_configurations', 'configuration_deployments', 'config_versions']}
        add_private_template(db)
        for table, rows in before.items():
            actual = [tuple(r) for r in db.execute('SELECT * FROM ' + table)]
            assert (actual[:-1] if table == 'config_versions' else actual) == rows
