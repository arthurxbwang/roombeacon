"""Add a private check-in choice without changing existing versions or deployments."""
import time

from .catalog_models import SoftwareSpec
from .catalog_store import encode

KEY = 'configuration_private_template_v1'
IDENTITY = 'builtin-software-private-checkin'


def add_private_template(db):
    if db.execute('SELECT 1 FROM meta WHERE key=?', (KEY,)).fetchone():
        return
    name = '签到保密版'
    spec = SoftwareSpec(display_version='v7', show_meeting_titles=False,
                        rules={'owner': 'v5', 'mode': 'auto', 'early_minutes': 5,
                               'grace_minutes': 5, 'release_delay_seconds': 0}).model_dump()
    value = encode(spec)
    db.execute('INSERT INTO config_catalog VALUES (?,?,?,?,1,1,0,?)',
               (IDENTITY, 'software', name, value, 'private-template'))
    db.execute('INSERT INTO config_versions VALUES (?,1,?,?,?,?)',
               (IDENTITY, name, value, 'migration', int(time.time())))
    db.execute('INSERT INTO meta VALUES (?,?)', (KEY, IDENTITY))
    db.execute('INSERT INTO audit(time,actor,action,target,detail) VALUES (?,?,?,?,?)',
               (int(time.time()), 'migration', 'private-template-add', IDENTITY,
                encode({'actor_name': '配置迁移', 'target_name': name})))
