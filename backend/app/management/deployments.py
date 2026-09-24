"""Durable device/room/template joins and explicit versioned deployment operations."""
import json
import secrets
import time

from fastapi import APIRouter, Request

from ..core.config import settings
from ..core.exceptions import AppError
from ..core.response import ok
from ..services.room_display_collector import cached_directory
from .catalog_models import DeployRequest, DeviceStatus
from .catalog_store import encode, version_row
from .devices import conflict, get_row, update
from .profiles import PROFILES
from .security import actor
from .store import audit, database

router = APIRouter(prefix='/api/v6/admin')


def installation_config(device, hardware, software, confirmed=False):
    hw, sw = hardware['spec'], software['spec']
    metadata = json.loads(device['metadata'])
    if hw['model'] and metadata.get('model') != hw['model'] and not confirmed:
        raise AppError(422, '设备型号与安装模板不同，请核对后确认', 422)
    if sw['orientation'] != 'any' and (sw['orientation'] == 'portrait') != hw['portrait']:
        raise AppError(422, '软件模板方向与安装方向不兼容', 422)
    screen = metadata.get('screen') or {}
    width, height = screen.get('viewport_width', 0), screen.get('viewport_height', 0)
    if width and height:
        width, height = (min(width, height), max(width, height)) if hw['portrait'] else (max(width, height), min(width, height))
    if sw['min_width'] or sw['min_height']:
        if not width or not height:
            raise AppError(422, '设备未上报网页尺寸，暂不能核验此软件模板的尺寸要求', 422)
        if width < sw['min_width'] or height < sw['min_height']:
            raise AppError(422, '设备网页尺寸小于软件模板的要求', 422)
    profile = next((p for p in PROFILES if p['pins'] == hw['pins'] and p['active_level'] == hw['active_level']), None)
    schema = metadata.get('config_schema', 1)
    if hw['room_light'] and not profile and schema < 3:
        raise AppError(422, '自定义接线需先升级支持配置协议 3 的 APK', 422)
    if hw['room_light'] and schema >= 3 and not metadata.get('light_supported'):
        raise AppError(422, '设备未上报可用灯控驱动，不能应用灯控模板', 422)
    config = {'version': 'v6', 'portrait': hw['portrait'], 'room_light': hw['room_light'],
              'node_id': 'central', 'reload': json.loads(device['config']).get('reload', 0),
              'device_profile': profile['id'] if hw['room_light'] and profile else 'generic',
              'theme_mode': sw['theme_mode'] if schema >= 3 or sw['theme_mode'] != 'dark' else 'auto',
              'language': sw['language'], 'presentation': {k: v for k, v in sw.items() if k != 'rules'}}
    if hw['room_light'] and schema >= 3:
        config['light_wiring'] = {'pins': hw['pins'], 'active_level': hw['active_level']}
    return config


def deployment_view(db, row):
    result = dict(row) | {'value': json.loads(row['value'])}
    device = get_row(db, row['device_id'])
    room = db.execute('SELECT * FROM room_configurations WHERE room_id=?', (row['room_id'],)).fetchone()
    installation = db.execute('SELECT * FROM device_installations WHERE device_id=?', (row['device_id'],)).fetchone()
    actual = json.loads(device['config'])
    intended = result['value']['after']
    matches = {k: v for k, v in actual.items() if k != 'reload'} == {k: v for k, v in intended.items() if k != 'reload'}
    if device['status'] != 'active':
        state = 'inactive'
    elif not installation or installation['deployment_id'] != row['id'] or device['room_id'] != row['room_id']:
        state = 'superseded'
    elif not matches:
        state = 'drifted'
    elif device['error']:
        state = 'partial' if device['reported_revision'] == device['revision'] else 'failed'
    elif device['reported_revision'] != device['revision']:
        state = 'waiting'
    elif room and room['policy_state'] != 'applied':
        state = 'partial'
    else:
        state = 'applied'
    result.update(state=state, online=time.time() - device['last_seen'] < 60,
                  error=device['error'] or (room['error'] if room else ''),
                  policy_state=room['policy_state'] if room else 'unknown',
                  reported_revision=device['reported_revision'], delivery_revision=device['revision'])
    return result


@router.post('/devices/{identity}/status')
def status(identity: str, body: DeviceStatus, request: Request):
    user = actor(request, write=True)
    with database() as db:
        row = get_row(db, identity)
        if row['revision'] != body.expected_revision:
            raise conflict()
        return ok(update(db, row, json.loads(row['config']), row['room_id'], body.status, user['subject'], 'device-status'))


@router.get('/configuration')
def configuration(request: Request):
    actor(request)
    with database() as db:
        rooms = {r['room_id']: dict(r) | {'rules': json.loads(r['rules'])}
                 for r in db.execute('SELECT * FROM room_configurations')}
        devices = {r['device_id']: dict(r) for r in db.execute('SELECT * FROM device_installations')}
        deployments = [deployment_view(db, r) for r in db.execute(
            'SELECT * FROM configuration_deployments WHERE id IN (SELECT deployment_id FROM device_installations) '
            'OR id IN (SELECT id FROM configuration_deployments ORDER BY created_at DESC,rowid DESC LIMIT 200) '
            'ORDER BY created_at DESC,rowid DESC')]
        return ok({'rooms': rooms, 'devices': devices, 'deployments': deployments})


def prepare(db, body, rooms):
    room = next((r for r in rooms if r['room_id'] == body.room_id), None)
    if not room:
        raise AppError(422, '请选择有效会议室', 422)
    device = get_row(db, body.device_id)
    if device['revision'] != body.expected_revision:
        raise conflict()
    if device['status'] == 'revoked':
        raise AppError(422, '已撤销设备不能部署', 422)
    if device['room_id'] and device['room_id'] != body.room_id:
        old_room = db.execute('SELECT controller_id FROM room_configurations WHERE room_id=?', (device['room_id'],)).fetchone()
        if old_room and old_room['controller_id'] == device['id'] and db.execute(
                "SELECT 1 FROM devices WHERE room_id=? AND id<>? AND status='active'",
                (device['room_id'], device['id'])).fetchone():
            raise AppError(422, '此设备是原会议室主控，请先在原会议室选择其他主控设备', 422)
    hw = version_row(db, body.hardware_id, body.hardware_version, 'hardware')
    sw = version_row(db, body.software_id, body.software_version, 'software')
    existing = db.execute('SELECT * FROM room_configurations WHERE room_id=?', (body.room_id,)).fetchone()
    if (existing['revision'] if existing else 0) != body.expected_room_revision:
        raise conflict()
    changed = bool(existing and (existing['software_id'], existing['software_version']) != (body.software_id, body.software_version))
    if changed and not body.replace_room_software:
        raise AppError(422, '会议室已有其他软件模板，请确认更换及受影响设备', 422)
    others = list(db.execute("SELECT * FROM devices WHERE room_id=? AND id<>? AND status='active'",
                            (body.room_id, body.device_id)))
    targets = [(device, hw)]
    # The room software and controller are one shared assignment; all displays get that revision.
    if changed or body.control_device:
        for other in others:
            link = db.execute('SELECT * FROM device_installations WHERE device_id=?', (other['id'],)).fetchone()
            if not link:
                raise AppError(422, '该会议室还有历史配置设备，请先转换其模板关联', 422)
            targets.append((other, version_row(db, link['hardware_id'], link['hardware_version'], 'hardware')))
    prepared = [(d, h, installation_config(d, h, sw, body.confirm_model_mismatch)) for d, h in targets]
    controller = body.device_id if body.control_device else (existing['controller_id'] if existing else '')
    if sw['spec']['rules']['owner'] == 'v5' and not controller:
        raise AppError(422, 'V5 会议室需指定一台业务主控设备', 422)
    return room, existing, sw, prepared, controller


@router.post('/deployments/preview')
async def preview(body: DeployRequest, request: Request):
    actor(request, write=True)
    rooms = await cached_directory()
    with database() as db:
        room, existing, sw, prepared, controller = prepare(db, body, rooms)
        return ok({'room': room, 'software': sw['name'], 'controller_id': controller,
                   'room_revision': existing['revision'] if existing else 0,
                   'devices': [{'code': d['code'], 'hardware': h['name'], 'before': json.loads(d['config']),
                                'after': config | {'usage_control': d['id'] == controller}} for d, h, config in prepared]})


def commit_deployment(db, body, rooms, user):
    room, existing, sw, prepared, controller = prepare(db, body, rooms)
    rules = sw['spec']['rules']
    rules_changed = not existing or json.loads(existing['rules']) != rules
    policy_state = ('pending' if settings.ROOM_DISPLAY_USAGE_ENABLED else
                    'applied' if rules['owner'] == 'official' else 'blocked') if rules_changed else existing['policy_state']
    error = ('服务器尚未启用 V5' if policy_state == 'blocked' else '') if rules_changed else existing['error']
    revision = (existing['revision'] if existing else 0) + 1
    db.execute('INSERT INTO room_configurations VALUES (?,?,?,?,?,?,?,?,?,?,?) '
               'ON CONFLICT(room_id) DO UPDATE SET software_id=excluded.software_id, '
               'software_version=excluded.software_version,revision=excluded.revision, '
               'controller_id=excluded.controller_id,rules=excluded.rules,policy_state=excluded.policy_state, '
               'error=excluded.error,room_name=excluded.room_name,location=excluded.location',
               (body.room_id, body.software_id, body.software_version, revision, controller, encode(rules),
                policy_state, error, room.get('name', body.room_id), room.get('location', ''),
                existing['policy_revision'] if existing else ''))
    identities = []
    for device, hardware, config in prepared:
        if device['room_id'] != body.room_id:
            db.execute("UPDATE room_configurations SET controller_id='',revision=revision+1,policy_state='pending',"
                       "error='业务主控已移至其他会议室' WHERE room_id=? AND controller_id=?",
                       (device['room_id'], device['id']))
        config['usage_control'] = device['id'] == controller
        changed = update(db, device, config, body.room_id, 'active', user['subject'], 'deploy', True)
        identity = secrets.token_hex(12)
        value = {'device_code': device['code'], 'room_name': room.get('name', body.room_id),
                 'location': room.get('location', ''), 'hardware_name': hardware['name'],
                 'software_name': sw['name'], 'before': json.loads(device['config']), 'after': config}
        db.execute('INSERT INTO configuration_deployments VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                   (identity, device['id'], body.room_id, hardware['template_id'], hardware['version'],
                    body.software_id, body.software_version, changed['revision'], encode(value),
                    user['subject'], int(time.time())))
        db.execute('INSERT INTO device_installations VALUES (?,?,?,?) ON CONFLICT(device_id) DO UPDATE '
                   'SET hardware_id=excluded.hardware_id,hardware_version=excluded.hardware_version,deployment_id=excluded.deployment_id',
                   (device['id'], hardware['template_id'], hardware['version'], identity))
        audit(db, user['subject'], 'deployment', identity, value | {'target_name': '设备 ' + device['code'],
              'hardware_version': hardware['version'], 'software_version': body.software_version})
        identities.append(identity)
    return {'deployment_ids': identities, 'room_revision': revision}


@router.post('/deployments')
async def deploy(body: DeployRequest, request: Request):
    user = actor(request, write=True)
    rooms = await cached_directory()
    with database() as db:
        return ok(commit_deployment(db, body, rooms, user))
