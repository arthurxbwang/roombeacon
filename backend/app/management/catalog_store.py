"""Additive schema and immutable configuration versions, independent of runtime state."""
import json
import time

from ..core.exceptions import AppError
from .catalog_models import HardwareSpec, SoftwareSpec
from .profiles import PROFILES

SCHEMA = '''
CREATE TABLE IF NOT EXISTS config_catalog (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL, spec TEXT NOT NULL,
 revision INTEGER NOT NULL, published_version INTEGER NOT NULL DEFAULT 0,
 archived INTEGER NOT NULL DEFAULT 0, source TEXT NOT NULL DEFAULT 'manual');
CREATE TABLE IF NOT EXISTS config_versions (
 template_id TEXT NOT NULL, version INTEGER NOT NULL, name TEXT NOT NULL,
 spec TEXT NOT NULL, actor TEXT NOT NULL, created_at INTEGER NOT NULL,
 PRIMARY KEY(template_id,version));
CREATE TABLE IF NOT EXISTS hardware_tests (
 id TEXT PRIMARY KEY, template_id TEXT NOT NULL, version INTEGER NOT NULL,
 device_id TEXT NOT NULL, value TEXT NOT NULL, actor TEXT NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS room_configurations (
 room_id TEXT PRIMARY KEY, software_id TEXT NOT NULL, software_version INTEGER NOT NULL,
 revision INTEGER NOT NULL, controller_id TEXT NOT NULL, rules TEXT NOT NULL,
 policy_state TEXT NOT NULL, error TEXT NOT NULL DEFAULT '', room_name TEXT NOT NULL,
 location TEXT NOT NULL, policy_revision TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS device_installations (
 device_id TEXT PRIMARY KEY, hardware_id TEXT NOT NULL, hardware_version INTEGER NOT NULL,
 deployment_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS configuration_deployments (
 id TEXT PRIMARY KEY, device_id TEXT NOT NULL, room_id TEXT NOT NULL,
 hardware_id TEXT NOT NULL, hardware_version INTEGER NOT NULL,
 software_id TEXT NOT NULL, software_version INTEGER NOT NULL,
 device_revision INTEGER NOT NULL, value TEXT NOT NULL, actor TEXT NOT NULL,
 created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS configuration_assets (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, mime TEXT NOT NULL, content BLOB NOT NULL,
 created_at INTEGER NOT NULL);
'''


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def initialize(db):
    if db.execute("SELECT 1 FROM meta WHERE key='configuration_catalog_v1'").fetchone():
        return
    for profile in PROFILES:
        identity = 'builtin-' + profile['id']
        spec = HardwareSpec(model=profile['model'], firmware=profile['firmware'],
                            device_profile=profile['id'], room_light=bool(profile['pins']),
                            **({'pins': profile['pins'], 'active_level': profile['active_level']}
                               if profile['pins'] else {})).model_dump()
        if profile['id'] == 'bx68':
            spec.update(width=1920, height=1080)
        if profile['id'] == 'rk3568_r':
            spec.update(width=1280, height=800)
        spec['notes'] = '接线来源：docs/android-device-profiles.md；安装到其他固件或设备仍需核验。'
        db.execute('INSERT OR IGNORE INTO config_catalog VALUES (?,?,?,?,1,1,0,?)',
                   (identity, 'hardware', profile['name'] + ' · 横屏', encode(spec), 'verified-profile'))
        db.execute('INSERT OR IGNORE INTO config_versions VALUES (?,1,?,?,?,?)',
                   (identity, profile['name'] + ' · 横屏', encode(spec), 'migration', int(time.time())))
    # Legacy templates have no trustworthy usage links. Split as drafts, never republish devices.
    for row in db.execute('SELECT * FROM templates').fetchall():
        old = json.loads(row['config'])
        profile = next((p for p in PROFILES if p['id'] == old.get('device_profile')), PROFILES[0])
        hardware = HardwareSpec(device_profile=old.get('device_profile', 'auto'),
                                portrait=old.get('portrait', False), room_light=old.get('room_light', True),
                                model=profile['model'], firmware=profile['firmware'],
                                **({'pins': profile['pins'], 'active_level': profile['active_level']}
                                   if profile['pins'] else {})).model_dump()
        software = SoftwareSpec(theme_mode=old.get('theme_mode', 'auto'),
                                language=old.get('language', 'zh-CN')).model_dump()
        for kind, spec in [('hardware', hardware), ('software', software)]:
            db.execute('INSERT OR IGNORE INTO config_catalog VALUES (?,?,?,?,1,0,0,?)',
                       ('legacy-' + kind + '-' + row['id'], kind, '迁移待核对 · ' + row['name'],
                        encode(spec), 'legacy:' + row['id']))
    db.execute("INSERT INTO meta VALUES ('configuration_catalog_v1','1')")


def template_row(db, identity):
    row = db.execute('SELECT * FROM config_catalog WHERE id=?', (identity,)).fetchone()
    if not row:
        raise AppError(404, '模板不存在', 404)
    return row


def version_row(db, identity, version, kind=None):
    template = template_row(db, identity)
    if template['archived'] or kind and template['kind'] != kind:
        raise AppError(422, '模板已归档或类型不符', 422)
    row = db.execute('SELECT * FROM config_versions WHERE template_id=? AND version=?',
                     (identity, version)).fetchone()
    if not row:
        raise AppError(422, '请选择已发布模板版本', 422)
    return dict(row) | {'spec': json.loads(row['spec'])}


def template_view(db, row):
    value = dict(row) | {'spec': json.loads(row['spec'])}
    value['versions'] = [dict(v) | {'spec': json.loads(v['spec'])} for v in db.execute(
        'SELECT * FROM config_versions WHERE template_id=? ORDER BY version DESC', (row['id'],))]
    value['tests'] = [dict(t) | {'value': json.loads(t['value'])} for t in db.execute(
        'SELECT * FROM hardware_tests WHERE template_id=? ORDER BY created_at DESC', (row['id'],))]
    value['devices'] = [dict(d) for d in db.execute(
        'SELECT d.id,d.code,d.room_id,i.hardware_version AS version FROM devices d '
        'JOIN device_installations i ON d.id=i.device_id WHERE i.hardware_id=?', (row['id'],))]
    value['rooms'] = [dict(r) for r in db.execute(
        'SELECT room_id,room_name,location,software_version AS version FROM room_configurations '
        'WHERE software_id=?', (row['id'],))]
    return value
