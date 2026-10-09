"""Administrator-approved first installation and separately recorded field acceptance."""
import json
import secrets
import time

from fastapi import APIRouter, Request

from ..core.exceptions import AppError
from ..core.response import ok
from .installation_models import (
    Acceptance,
    Association,
    Batch,
    Executor,
    Manifest,
    Retry,
    Revision,
)
from .installation_server import router as server_router
from .installation_store import (
    conflict,
    current,
    expire,
    job_view,
    ready,
    release_view,
    row,
)
from .installation_store import installation_audit as audit
from .security import actor
from .store import database, digest

router = APIRouter(prefix='/api/v6/admin/installation')
router.include_router(server_router)


@router.get('')
def overview(request: Request):
    actor(request)
    with database() as db:
        expire(db)
        return ok({
            'executors': [dict(r) for r in db.execute(
                'SELECT id,name,revoked,expires,last_seen FROM install_executors ORDER BY expires DESC')],
            'releases': [release_view(r) for r in db.execute('SELECT * FROM install_releases ORDER BY created_at DESC')],
            'jobs': [job_view(db, r) for r in db.execute('SELECT * FROM install_jobs ORDER BY created_at DESC,rowid DESC LIMIT 1000')],
        })


@router.post('/executors')
def create_executor(body: Executor, request: Request):
    user = actor(request, write=True)
    identity, secret = secrets.token_hex(16), secrets.token_urlsafe(32)
    token = f'rbi:{identity}:{secret}'
    with database() as db:
        db.execute('INSERT INTO install_executors(id,name,secret_hash,expires) VALUES (?,?,?,?)',
                   (identity, body.name, digest(token), int(time.time()) + 86400))
        audit(db, user['subject'], 'installation-executor-create', identity, {'name': body.name})
    return ok({'id': identity, 'token': token})


@router.post('/executors/{identity}/revoke')
def revoke_executor(identity: str, request: Request):
    user = actor(request, write=True)
    with database() as db:
        row(db, 'install_executors', identity)
        db.execute('UPDATE install_executors SET revoked=1 WHERE id=?', (identity,))
        # An already started ADB command cannot be undone by revoking HTTP access.
        db.execute("UPDATE install_jobs SET state=CASE WHEN state='queued' THEN 'cancelled' ELSE 'uncertain' END, "
                   "revision=revision+1 WHERE executor_id=? AND state IN ('queued','running')", (identity,))
        audit(db, user['subject'], 'installation-executor-revoke', identity)
    return ok()


@router.post('/releases')
def create_release(body: Manifest, request: Request):
    user = actor(request, write=True)
    identity = secrets.token_hex(16)
    with database() as db:
        db.execute('INSERT INTO install_releases VALUES (?,?,?)',
                   (identity, body.model_dump_json(), int(time.time())))
        audit(db, user['subject'], 'installation-release', identity, body.model_dump())
    return ok({'id': identity})


@router.post('/batches')
def create_batch(body: Batch, request: Request):
    user = actor(request, write=True)
    payload = body.model_dump_json()
    with database() as db:
        existing = db.execute('SELECT payload FROM install_batches WHERE id=?', (body.request_id,)).fetchone()
        if existing:
            if existing['payload'] != payload:
                raise conflict('提交标识已用于其他任务')
            return ok({'batch_id': body.request_id})
        executor = row(db, 'install_executors', body.executor_id)
        if executor['revoked'] or executor['expires'] <= time.time():
            raise conflict('安装助手已撤销或过期，请重新登记')
        row(db, 'install_releases', body.release_id)
        if (len({str(t.ip) for t in body.targets}) != len(body.targets) or
                len({t.serial for t in body.targets}) != len(body.targets)):
            raise AppError(422, '同一批次不能重复 IP 或序列号', 422)
        for target in body.targets:
            busy_target(db, str(target.ip), target.serial)
        db.execute('INSERT INTO install_batches VALUES (?,?)', (body.request_id, payload))
        for target in body.targets:
            identity = secrets.token_hex(16)
            db.execute('INSERT INTO install_jobs(id,batch_id,executor_id,release_id,ip,port,serial,created_at) '
                       'VALUES (?,?,?,?,?,?,?,?)', (identity, body.request_id, body.executor_id, body.release_id,
                                                  str(target.ip), target.port, target.serial, int(time.time())))
        audit(db, user['subject'], 'installation-batch', body.request_id,
              {'count': len(body.targets), 'executor_id': body.executor_id, 'release_id': body.release_id})
    return ok({'batch_id': body.request_id})


def busy_target(db, ip, serial, excluding=''):
    if db.execute("SELECT 1 FROM install_jobs WHERE id<>? AND (ip=? OR serial=?) "
                  "AND state IN ('queued','running','uncertain')", (excluding, ip, serial)).fetchone():
        raise conflict('目标已有排队、执行中或待核实任务；请先处理原任务')


@router.post('/jobs/{identity}/cancel')
def cancel(identity: str, body: Revision, request: Request):
    user = actor(request, write=True)
    with database() as db:
        value = current(db, identity, body.revision)
        if value['state'] != 'queued':
            raise conflict('只能取消尚未领取的任务；已执行动作不能撤回')
        db.execute("UPDATE install_jobs SET state='cancelled',revision=revision+1 WHERE id=?", (identity,))
        audit(db, user['subject'], 'installation-cancel', identity)
    return ok()


@router.post('/jobs/{identity}/retry')
def retry(identity: str, body: Retry, request: Request):
    user = actor(request, write=True)
    with database() as db:
        value = current(db, identity, body.revision)
        executor = row(db, 'install_executors', value['executor_id'])
        if (value['state'] not in ('failed', 'uncertain') or value['lease_until'] > time.time() or
                executor['revoked'] or executor['expires'] <= time.time()):
            raise conflict('须等待执行期限结束且助手有效，核实现场结果并停止旧助手后重试')
        busy_target(db, value['ip'], value['serial'], identity)
        db.execute("UPDATE install_jobs SET state='queued',revision=revision+1,lease_hash='',lease_until=0,"
                   "result='',error='' WHERE id=?", (identity,))
        audit(db, user['subject'], 'installation-retry', identity, {'previous_executor_stopped': True})
    return ok()


@router.post('/jobs/{identity}/resolve')
def resolve(identity: str, body: Retry, request: Request):
    user = actor(request, write=True)
    with database() as db:
        value = current(db, identity, body.revision)
        if value['state'] != 'uncertain' or value['lease_until'] > time.time():
            raise conflict('须等待执行期限结束并停止旧助手后，才能结束待核实任务')
        db.execute("UPDATE install_jobs SET state='cancelled',revision=revision+1 WHERE id=?", (identity,))
        audit(db, user['subject'], 'installation-resolve', identity, {'previous_executor_stopped': True})
    return ok()


@router.post('/jobs/{identity}/associate')
def associate(identity: str, body: Association, request: Request):
    user = actor(request, write=True)
    with database() as db:
        value = current(db, identity, body.revision)
        if value['state'] != 'installed':
            raise conflict('须先取得安装及启动回执')
        device = db.execute('SELECT * FROM devices WHERE code=?', (body.code,)).fetchone()
        if not device or device['status'] in ('revoked', 'deleted') or time.time() - device['last_seen'] >= 60:
            raise conflict('短码对应的设备不存在、已撤销或离线')
        metadata = json.loads(device['metadata'])
        manifest = json.loads(row(db, 'install_releases', value['release_id'])['manifest'])
        if metadata.get('serial') and metadata['serial'] != value['serial']:
            raise conflict('设备上报的序列号不一致')
        if metadata.get('apk') != manifest['version_name'] or metadata.get('model') not in manifest['models']:
            raise conflict('设备上报的 APK 版本或型号不一致')
        if db.execute("SELECT 1 FROM install_jobs WHERE device_id=? AND id<>? AND state IN ('associated','accepted')",
                      (device['id'], identity)).fetchone():
            raise conflict('该设备已关联其他交付任务')
        db.execute("UPDATE install_jobs SET device_id=?,state='associated',revision=revision+1 WHERE id=?",
                   (device['id'], identity))
        audit(db, user['subject'], 'installation-associate', identity,
              {'device_id': device['id'], 'device_code': body.code, 'physical_identity_confirmed': True})
    return ok()


@router.post('/jobs/{identity}/accept')
def accept(identity: str, body: Acceptance, request: Request):
    user = actor(request, write=True)
    with database() as db:
        value = current(db, identity, body.revision)
        device = db.execute('SELECT * FROM devices WHERE id=?', (value['device_id'],)).fetchone()
        if value['state'] not in ('associated', 'accepted') or not ready(device) or device['revision'] != body.device_revision:
            raise conflict('设备未激活、离线、配置未应用或有异常，不能交付')
        manifest = json.loads(row(db, 'install_releases', value['release_id'])['manifest'])
        metadata = json.loads(device['metadata'])
        if (metadata.get('apk') != manifest['version_name'] or metadata.get('model') not in manifest['models'] or
                metadata.get('serial') and metadata['serial'] != value['serial']):
            raise conflict('设备版本或身份已变化，请重新核实')
        evidence = body.model_dump() | {'room_id': device['room_id'], 'actor': user['subject'],
                                       'at': int(time.time()), 'source': 'manual'}
        db.execute("UPDATE install_jobs SET state='accepted',acceptance=?,revision=revision+1 WHERE id=?",
                   (json.dumps(evidence), identity))
        audit(db, user['subject'], 'installation-accept', identity, evidence)
    return ok()
