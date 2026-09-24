"""Explicitly adopt existing effective values without refreshing or changing devices."""
import json
import secrets
import time

from fastapi import APIRouter, Request

from ..core.config import settings
from ..core.exceptions import AppError
from ..core.response import ok
from ..core.room_devices import room_cache
from ..services.room_display_collector import cached_directory
from ..services.room_usage import policy_for
from ..services.room_usage_store import UsageStore
from .catalog_models import HardwareSpec, Rules, SoftwareSpec
from .catalog_store import encode, version_row
from .devices import conflict, get_row
from .models import Revision
from .profiles import PROFILES
from .security import actor
from .store import audit, database

router = APIRouter(prefix='/api/v6/admin')


def imported_template(db, kind, name, spec, who):
    identity = secrets.token_hex(12)
    db.execute('INSERT INTO config_catalog VALUES (?,?,?,?,1,1,0,?)',
               (identity, kind, name, encode(spec), 'effective-config'))
    db.execute('INSERT INTO config_versions VALUES (?,1,?,?,?,?)',
               (identity, name, encode(spec), who, int(time.time())))
    return identity


@router.post('/devices/{identity}/adopt')
async def adopt(identity: str, body: Revision, request: Request):
    user = actor(request, write=True)
    rooms = await cached_directory()
    with database() as db:
        device = dict(get_row(db, identity))
    if device['revision'] != body.expected_revision:
        raise conflict()
    if device['status'] != 'active' or not device['room_id']:
        raise AppError(422, '只有已绑定的历史设备需要转换；新设备请选择模板部署', 422)
    policy = Rules().model_dump() | {'revision': ''}
    if settings.ROOM_DISPLAY_USAGE_ENABLED:
        async with room_cache() as cache:
            policy = await policy_for(UsageStore(cache), device['room_id'])
    config, metadata = json.loads(device['config']), json.loads(device['metadata'])
    profile = next((p for p in PROFILES if p['id'] == config.get('device_profile')), None)
    if not profile and config.get('device_profile', 'auto') == 'auto':
        profile = next((p for p in PROFILES if p['model'] == metadata.get('model') and p['firmware'] == metadata.get('firmware')), None)
    if config.get('room_light') and (not profile or not profile['pins']):
        raise AppError(422, '无法确认历史灯控接线，请核对硬件模板后显式部署', 422)
    screen = metadata.get('screen') or {}
    hw = HardwareSpec(width=screen.get('pixel_width', 0), height=screen.get('pixel_height', 0),
                      model=metadata.get('model', ''), firmware=metadata.get('firmware', ''),
                      portrait=config.get('portrait', False), room_light=config.get('room_light', False),
                      device_profile=profile['id'] if profile else 'generic',
                      notes='从设备当前实际配置转换；不代表新做过硬件测试。',
                      **({'pins': profile['pins'], 'active_level': profile['active_level']} if profile and profile['pins'] else {}))
    sw = SoftwareSpec(theme_mode=config.get('theme_mode', 'auto'), language=config.get('language', 'zh-CN'),
                      rules=Rules(**{k: policy[k] for k in Rules.model_fields}))
    room = next((r for r in rooms if r['room_id'] == device['room_id']), None)
    if not room:
        raise AppError(422, '会议室已不在当前目录中', 422)
    with database() as db:
        if get_row(db, identity)['revision'] != body.expected_revision:
            raise conflict()
        if db.execute('SELECT 1 FROM device_installations WHERE device_id=?', (identity,)).fetchone():
            raise AppError(409, '设备已有模板关联', 409)
        existing = db.execute('SELECT * FROM room_configurations WHERE room_id=?', (device['room_id'],)).fetchone()
        hw_name = '当前安装 · ' + device['code']
        hw_id = imported_template(db, 'hardware', hw_name, hw.model_dump(), user['subject'])
        if existing:
            software = version_row(db, existing['software_id'], existing['software_version'], 'software')
            if software['spec'] != sw.model_dump():
                raise AppError(409, '历史设备显示配置与房间软件模板不同，请先核对并统一配置', 409)
            sw_id, sw_version, sw_name = existing['software_id'], existing['software_version'], software['name']
        else:
            sw_name, sw_version = '当前软件 · ' + room.get('name', device['room_id']), 1
            sw_id = imported_template(db, 'software', sw_name, sw.model_dump(), user['subject'])
            db.execute("INSERT INTO room_configurations VALUES (?,?,1,1,?,?,?,'',?,?,?)",
                       (device['room_id'], sw_id, identity, encode(sw.rules.model_dump()), 'applied',
                        room.get('name', device['room_id']), room.get('location', ''), policy['revision']))
        deployment = secrets.token_hex(12)
        value = {'device_code': device['code'], 'room_name': room.get('name', device['room_id']),
                 'location': room.get('location', ''), 'hardware_name': hw_name, 'software_name': sw_name,
                 'before': config, 'after': config, 'migration': True}
        db.execute('INSERT INTO configuration_deployments VALUES (?,?,?,?,1,?,?,?,?,?,?)',
                   (deployment, identity, device['room_id'], hw_id, sw_id, sw_version, device['revision'], encode(value),
                    user['subject'], int(time.time())))
        db.execute('INSERT INTO device_installations VALUES (?,?,1,?)', (identity, hw_id, deployment))
        audit(db, user['subject'], 'configuration-adopt', identity, value)
    return ok({'hardware_id': hw_id, 'software_id': sw_id})
