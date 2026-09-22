"""Credential bootstrap, native sync and the durable device configuration lifecycle."""
import json
import secrets
import sqlite3
import time

from fastapi import APIRouter, Request

from ..core.exceptions import AppError, UnauthorizedError
from ..core.response import ok
from ..services.room_display_collector import cached_directory
from .models import Batch, Configure, Revision, Rollback, Sync, Template
from .security import actor, bearer, device, parse_device, web_session
from .store import (
    DEFAULT_CONFIG,
    audit,
    database,
    device_view,
    digest,
    rate_limit,
    save_history,
)

router = APIRouter(prefix='/api/v6')
ALPHABET = '23456789ABCDEFGHJKMNPQRSTUVWXYZ'


def conflict():
    return AppError(409, '配置已变化，请刷新后重新操作', 409)


def get_row(db, identity):
    row = db.execute('SELECT * FROM devices WHERE id=?', (identity,)).fetchone()
    if not row:
        raise AppError(404, '设备不存在', 404)
    return row


def update(db, row, config, room_id, status, who, action):
    db.execute('UPDATE devices SET config=?, room_id=?, status=?, revision=revision+1 WHERE id=?',
               (json.dumps(config), room_id, status, row['id']))
    result = get_row(db, row['id'])
    save_history(db, result)
    audit(db, who, action, row['id'], {'revision': result['revision'], 'room_id': room_id, 'status': status})
    return device_view(result)


@router.post('/device/enroll')
def enroll(body: Sync, request: Request):
    token = bearer(request)
    identity = parse_device(token)
    rate_limit('enroll:' + (request.client.host if request.client else 'unknown'), 30)
    now = int(time.time())
    with database() as db:
        row = db.execute('SELECT * FROM devices WHERE id=?', (identity,)).fetchone()
        if row:
            row = device(db, token)
            if row['status'] == 'revoked':
                raise UnauthorizedError('设备已撤销，请联系管理员')
        else:
            count = db.execute("SELECT COUNT(*) FROM devices WHERE status='pending'").fetchone()[0]
            if count >= 500:
                raise AppError(429, '待激活设备已达上限，请联系管理员', 429)
            for _ in range(10):
                code = ''.join(secrets.choice(ALPHABET) for _ in range(6))
                try:
                    db.execute('INSERT INTO devices(id,code,secret_hash,config,metadata,last_seen,created_at) '
                               'VALUES (?,?,?,?,?,?,?)', (identity, code, digest(token), json.dumps(DEFAULT_CONFIG),
                                                        body.metadata.model_dump_json(), now, now))
                    break
                except sqlite3.IntegrityError:
                    continue
            else:
                raise AppError(503, '设备编号暂不可用，请重试', 503)
            row = get_row(db, identity)
            save_history(db, row)
            audit(db, identity, 'enroll', identity)
        return ok({'id': identity, 'code': row['code'], 'status': row['status']})


@router.post('/device/sync')
def sync(body: Sync, request: Request):
    with database() as db:
        row = device(db, bearer(request))
        if body.reported_revision > row['revision']:
            raise conflict()
        db.execute('UPDATE devices SET metadata=?,last_seen=?,reported_revision=?,error=? WHERE id=?',
                   (body.metadata.model_dump_json(), int(time.time()), body.reported_revision, body.error, row['id']))
        value = {'protocol': 1, 'id': row['id'], 'code': row['code'], 'status': row['status'],
                 'room_id': row['room_id'], 'revision': row['revision'], 'config': json.loads(row['config']),
                 'poll_seconds': 15, 'node_id': 'central'}
        if row['status'] == 'active':
            value['web_session'] = web_session(db, row)
        return ok(value)


@router.get('/admin/devices')
def devices(request: Request):
    actor(request)
    with database() as db:
        return ok([device_view(row) for row in db.execute('SELECT * FROM devices ORDER BY created_at DESC LIMIT 5000')])


@router.put('/admin/devices/{identity}')
async def configure(identity: str, body: Configure, request: Request):
    user = actor(request, write=True)
    if body.status == 'active' and (not body.room_id or
                                    not any(r['room_id'] == body.room_id for r in await cached_directory())):
        raise AppError(422, '请选择有效会议室', 422)
    with database() as db:
        row = get_row(db, identity)
        if row['revision'] != body.expected_revision:
            raise conflict()
        config = body.config.model_dump()
        config['reload'] = json.loads(row['config'])['reload']
        return ok(update(db, row, config, body.room_id, body.status, user['subject'], 'configure'))


@router.post('/admin/devices/{identity}/reload')
def reload_device(identity: str, body: Revision, request: Request):
    user = actor(request, write=True)
    with database() as db:
        row = get_row(db, identity)
        if row['revision'] != body.expected_revision:
            raise conflict()
        config = json.loads(row['config'])
        config['reload'] += 1
        return ok(update(db, row, config, row['room_id'], row['status'], user['subject'], 'reload'))


@router.get('/admin/devices/{identity}/history')
def history(identity: str, request: Request):
    actor(request)
    with database() as db:
        get_row(db, identity)
        return ok([{'revision': row['revision'], **json.loads(row['value'])} for row in db.execute(
            'SELECT * FROM history WHERE device_id=? ORDER BY revision DESC LIMIT 50', (identity,))])


@router.post('/admin/devices/{identity}/rollback')
async def rollback(identity: str, body: Rollback, request: Request):
    user = actor(request, write=True)
    rooms = await cached_directory()
    with database() as db:
        row = get_row(db, identity)
        old = db.execute('SELECT value FROM history WHERE device_id=? AND revision=?',
                         (identity, body.revision)).fetchone()
        if row['revision'] != body.expected_revision or row['status'] != 'active':
            raise conflict()
        if not old:
            raise AppError(404, '配置历史不存在', 404)
        value = json.loads(old[0])
        if value['status'] != 'active' or not any(r['room_id'] == value['room_id'] for r in rooms):
            raise AppError(422, '只能回退到有效的已激活配置', 422)
        value['config']['reload'] = json.loads(row['config'])['reload'] + 1
        return ok(update(db, row, value['config'], value['room_id'], 'active', user['subject'], 'rollback'))


@router.get('/admin/templates')
def templates(request: Request):
    actor(request)
    with database() as db:
        return ok([dict(row) | {'config': json.loads(row['config'])} for row in db.execute('SELECT * FROM templates')])


@router.post('/admin/templates')
def template(body: Template, request: Request):
    user = actor(request, write=True)
    identity = secrets.token_hex(8)
    with database() as db:
        db.execute('INSERT INTO templates VALUES (?,?,?)', (identity, body.name, body.config.model_dump_json()))
        audit(db, user['subject'], 'template', identity, {'name': body.name})
    return ok({'id': identity})


@router.post('/admin/batch-config')
def batch(body: Batch, request: Request):
    user = actor(request, write=True)
    with database() as db:
        rows = [get_row(db, identity) for identity in body.devices]
        if any(row['revision'] != body.devices[row['id']] or row['status'] != 'active' for row in rows):
            raise conflict()
        for row in rows:
            config = body.config.model_dump()
            config['reload'] = json.loads(row['config'])['reload']
            update(db, row, config, row['room_id'], 'active', user['subject'], 'batch-config')
    return ok({'updated': len(rows)})


@router.get('/admin/audit')
def audit_log(request: Request):
    actor(request)
    with database() as db:
        return ok([dict(row) | {'detail': json.loads(row['detail'])} for row in db.execute(
            'SELECT * FROM audit ORDER BY id DESC LIMIT 200')])


@router.get('/admin/nodes')
def nodes(request: Request):
    actor(request)
    return ok({'protocol': 1, 'nodes': [{'id': 'central', 'name': '主服务器', 'status': 'active'}],
               'capabilities': ['device-sync', 'config-revision', 'ack', 'central-auth'], 'edge_enabled': False})
