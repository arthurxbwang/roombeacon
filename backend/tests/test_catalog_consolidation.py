"""Selection cleanup preserves effective configuration and immutable releases."""
import json

import pytest

from app.management.catalog_consolidation import KEY, consolidate
from app.management.catalog_models import SoftwareSpec
from app.management.store import database

from . import test_v6_management as v6

client = v6.client


def test_catalog_has_two_hardware_and_three_software_choices(client):
    values = client.get('/api/v6/admin/catalog', headers=v6.admin()).json()['data']
    visible = [r for r in values if not r['archived'] and not r['retired']]
    assert {r['name'] for r in visible} == {
        'BX68 · 13.3 寸 · 1920×1080 · 横屏', 'RK3568_R · 10.1 寸 · 1280×800 · 横屏', '签到版', '未签到版', '签到保密版'}
    display = next(r for r in visible if r['name'] == '未签到版')
    assert display['spec']['roombeacon_checkin'] is False
    assert display['spec']['rules']['mode'] == 'off'


def test_existing_used_templates_selected_without_overwriting_versions_or_devices(client):
    _, item = v6.enroll(client)
    assert v6.configure(client, item['id']).status_code == 200
    with database() as db:
        db.execute('DELETE FROM meta WHERE key=?', (KEY,))
        db.execute('DELETE FROM catalog_retirements')
        hw = db.execute("SELECT spec FROM config_versions WHERE template_id='builtin-bx68'").fetchone()[0]
        sw = json.dumps(SoftwareSpec(display_version='v7', rules={
            'owner': 'v5', 'mode': 'auto', 'early_minutes': 5, 'grace_minutes': 5,
            'release_delay_seconds': 0}).model_dump(exclude={'roombeacon_checkin'}))
        for identity, kind, spec in [('used-hardware', 'hardware', hw), ('used-software', 'software', sw)]:
            db.execute('INSERT INTO config_catalog VALUES (?,?,?,?,1,2,0,?)',
                       (identity, kind, '原模板名称', spec, 'manual'))
            db.execute('INSERT INTO config_versions VALUES (?,2,?,?,?,1)', (identity, '原模板名称', spec, 'test'))
        db.execute("INSERT INTO device_installations VALUES (?, 'used-hardware', 2, 'old')", (item['id'],))
        db.execute("INSERT INTO room_configurations VALUES (?, 'used-software', 2, 1, ?, '{}', 'applied', '', '测试房', '', '')",
                   (v6.ROOM, item['id']))
        before = [tuple(r) for r in db.execute('SELECT * FROM devices')]
        versions = [tuple(r) for r in db.execute('SELECT * FROM config_versions')]
        room = tuple(db.execute('SELECT * FROM room_configurations').fetchone())
        consolidate(db)
        assert [tuple(r) for r in db.execute('SELECT * FROM devices')] == before
        assert [tuple(r) for r in db.execute('SELECT * FROM config_versions')] == versions
        assert tuple(db.execute('SELECT * FROM room_configurations').fetchone()) == room
        selected = json.loads(db.execute('SELECT value FROM meta WHERE key=?', (KEY,)).fetchone()[0])
        assert 'used-hardware' in selected and 'used-software' in selected
        count = db.execute('SELECT COUNT(*) FROM audit').fetchone()[0]
        consolidate(db)
        assert db.execute('SELECT COUNT(*) FROM audit').fetchone()[0] == count


@pytest.mark.parametrize('rules', [{'owner': 'v5', 'mode': 'auto'}, {'owner': 'v5', 'mode': 'off'}])
def test_display_only_rejects_checkin_rules(client, rules):
    assert client.post('/api/v6/admin/catalog', headers=v6.admin(), json={
        'kind': 'software', 'name': '非法未签到版', 'spec': {'roombeacon_checkin': False, 'rules': rules}}
    ).status_code == 422
