"""One-time selection cleanup; immutable versions and live assignments stay intact."""
import json
import time

from .catalog_models import SoftwareSpec

KEY = 'configuration_catalog_selection_v2'


def encoded(spec):
    return json.dumps(spec, ensure_ascii=False, sort_keys=True)


def consolidate(db):
    if db.execute('SELECT 1 FROM meta WHERE key=?', (KEY,)).fetchone():
        return
    rows = list(db.execute('SELECT * FROM config_catalog WHERE archived=0 ORDER BY id'))
    keep = []
    for profile, name in [('bx68', 'BX68 · 13.3 寸 · 1920×1080 · 横屏'),
                          ('rk3568_r', 'RK3568_R · 10.1 寸 · 1280×800 · 横屏')]:
        baseline = db.execute('SELECT spec FROM config_versions WHERE template_id=? AND version=1',
                              ('builtin-' + profile,)).fetchone()
        wanted = json.loads(baseline['spec'])
        fields = ('model', 'firmware', 'width', 'height', 'portrait', 'room_light', 'pins', 'active_level')
        candidates = []
        for row in rows:
            if row['kind'] != 'hardware' or not row['published_version']:
                continue
            version = db.execute('SELECT spec FROM config_versions WHERE template_id=? AND version=?',
                                 (row['id'], row['published_version'])).fetchone()
            spec = json.loads(version['spec'])
            if all(spec.get(k) == wanted.get(k) for k in fields):
                uses = db.execute('SELECT COUNT(*) FROM device_installations WHERE hardware_id=?',
                                  (row['id'],)).fetchone()[0]
                candidates.append((uses, row['published_version'], row['id']))
        identity = max(candidates)[2] if candidates else 'builtin-' + profile
        db.execute('UPDATE config_catalog SET name=?,archived=0,revision=revision+1 WHERE id=?', (name, identity))
        keep.append(identity)
    for enabled, name, identity in [(True, '签到版', 'builtin-software-checkin'),
                                    (False, '未签到版', 'builtin-software-display')]:
        spec = SoftwareSpec(display_version='v7', checkin_enabled=enabled,
                            rules={'owner': 'v5' if enabled else 'official',
                                   'mode': 'auto' if enabled else 'off',
                                   'early_minutes': 5, 'grace_minutes': 5,
                                   'release_delay_seconds': 0}).model_dump()
        candidates = []
        for row in rows:
            if row['kind'] != 'software' or not row['published_version']:
                continue
            version = db.execute('SELECT spec FROM config_versions WHERE template_id=? AND version=?',
                                 (row['id'], row['published_version'])).fetchone()
            current = SoftwareSpec.model_validate_json(version['spec']).model_dump()
            if current == spec:
                uses = db.execute('SELECT COUNT(*) FROM room_configurations WHERE software_id=?',
                                  (row['id'],)).fetchone()[0]
                candidates.append((uses, row['published_version'], row['id']))
        if candidates:
            identity = max(candidates)[2]
            db.execute('UPDATE config_catalog SET name=?,revision=revision+1 WHERE id=?', (name, identity))
        else:
            value = encoded(spec)
            db.execute('INSERT INTO config_catalog VALUES (?,?,?,?,1,1,0,?)',
                       (identity, 'software', name, value, 'consolidated'))
            db.execute('INSERT INTO config_versions VALUES (?,1,?,?,?,?)',
                       (identity, name, value, 'migration', int(time.time())))
        keep.append(identity)
    for row in rows:
        if row['id'] not in keep:
            db.execute('INSERT OR IGNORE INTO catalog_retirements VALUES (?)', (row['id'],))
    db.execute('INSERT INTO meta VALUES (?,?)', (KEY, encoded(keep)))
    db.execute('INSERT INTO audit(time,actor,action,target,detail) VALUES (?,?,?,?,?)',
               (int(time.time()), 'migration', 'catalog-consolidate', KEY,
                encoded({'actor_name': '配置迁移', 'target_name': '软硬件模板选项', 'templates': keep})))
