"""IP -> read-only probe -> explicit, idempotent initialization."""
import json
import logging
import secrets
import time
from ipaddress import IPv4Address
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Request
from pydantic import Field, field_validator

from ..core.exceptions import AppError
from ..core.response import ok
from . import installation_runtime as runtime
from .installation_models import Contract, Target
from .installation_store import conflict, expire
from .installation_store import installation_audit as audit
from .security import actor
from .store import database

router = APIRouter()
logger = logging.getLogger(__name__)


class Probe(Contract):
    ip: IPv4Address
    port: int = Field(default=5555, ge=1, le=65535)

    @field_validator('ip')
    @classmethod
    def lan_only(cls, value):
        return Target.lan_only(value)


class Initialize(Contract):
    probe_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    confirmed: Literal[True]


@router.get('/server')
def server_status(request: Request):
    actor(request)
    return ok(runtime.status())


@router.post('/probe')
def probe(body: Probe, request: Request):
    user = actor(request, write=True)
    ip = str(body.ip)
    runtime.allowed(ip, body.port)
    device = runtime.detect(ip, body.port)
    manifest, blocker = None, ''
    try:
        _, manifest = runtime.default_apk()
        if device['model'] not in manifest['models']:
            blocker = '该设备型号不适用于默认安装包，请联系运维'
    except AppError as exc:
        blocker = exc.message
    if device['existing']:
        blocker = '已检测到门牌应用，请在设备台账中核对屏幕短码并配置会议室'
    value = {'id': secrets.token_hex(16), 'ip': ip, 'port': body.port, **device,
             'manifest': manifest, 'can_initialize': not blocker, 'blocker': blocker,
             'expires': int(time.time()) + 300}
    with database() as db:
        db.execute('DELETE FROM install_probes WHERE expires<? AND job_id=?', (int(time.time()) - 86400, ''))
        db.execute('INSERT INTO install_probes(id,subject,payload,expires) VALUES (?,?,?,?)',
                   (value['id'], user['subject'], json.dumps(value), value['expires']))
        audit(db, user['subject'], 'installation-probe', ip,
              {'serial': device['serial'], 'model': device['model'], 'can_initialize': not blocker})
    return ok(value)


def get_probe(db, identity, subject):
    value = db.execute('SELECT * FROM install_probes WHERE id=?', (identity,)).fetchone()
    if not value or value['subject'] != subject:
        raise conflict('检测记录不存在，请重新检测设备')
    return value


@router.post('/initialize')
def initialize(body: Initialize, request: Request, background: BackgroundTasks):
    user = actor(request, write=True)
    with database() as db:
        saved = get_probe(db, body.probe_id, user['subject'])
        if saved['job_id']:
            return ok({'job_id': saved['job_id']})
        value = json.loads(saved['payload'])
        if saved['expires'] <= time.time() or not value['can_initialize']:
            raise conflict(value['blocker'] or '检测结果已过期，请重新检测设备')
    runtime.allowed(value['ip'], value['port'])
    apk, manifest = runtime.default_apk()
    if manifest != value['manifest']:
        raise conflict('默认安装包已变化，请重新检测并确认')
    identity = secrets.token_hex(16)
    with database() as db:
        saved = get_probe(db, body.probe_id, user['subject'])
        if saved['job_id']:
            return ok({'job_id': saved['job_id']})
        if saved['expires'] <= time.time():
            raise conflict('检测结果已过期，请重新检测设备')
        expire(db)
        if db.execute("SELECT 1 FROM install_jobs WHERE state IN ('queued','running','uncertain') "
                      "AND (ip=? OR serial=? OR executor_id='server')", (value['ip'], value['serial'])).fetchone():
            raise conflict('已有执行中或待核实的安装任务，请先处理原任务')
        release_id = secrets.token_hex(16)
        db.execute('INSERT INTO install_releases VALUES (?,?,?)',
                   (release_id, json.dumps(manifest), int(time.time())))
        db.execute("INSERT INTO install_jobs(id,batch_id,executor_id,release_id,ip,port,serial,state,lease_until,created_at) "
                   "VALUES (?,?,'server',?,?,?,?,'running',?,?)", (identity, body.probe_id, release_id,
                    value['ip'], value['port'], value['serial'], int(time.time()) + 600, int(time.time())))
        db.execute('UPDATE install_probes SET job_id=? WHERE id=?', (identity, body.probe_id))
        audit(db, user['subject'], 'installation-initialize', identity, {'ip': value['ip'], 'serial': value['serial']})
    background.add_task(execute, identity, value, apk, manifest)
    return ok({'job_id': identity})


def execute(identity, value, apk, manifest):
    started = time.monotonic()
    def authorize():
        with database() as db:
            expire(db)
            job = db.execute('SELECT state,lease_until FROM install_jobs WHERE id=?', (identity,)).fetchone()
            if (not job or job['state'] != 'running' or job['lease_until'] <= time.time() or
                    time.monotonic() - started > 360):
                raise runtime.installer.InstallError('server_failure')
        runtime.allowed(value['ip'], value['port'])
    state, result, error = 'installed', '', ''
    try:
        authorize()
        result = runtime.installer.install(value | {'id': identity, 'manifest': manifest},
                                           apk, *runtime.tools(), authorize)
    except runtime.installer.InstallError as exc:
        error = str(exc)
        if error not in ('apk_invalid', 'connection_failed', 'identity_mismatch', 'model_mismatch',
                         'existing_apk', 'install_failed', 'launch_failed', 'verification_failed', 'local_failure'):
            state, error = 'uncertain', 'local_failure'
        else:
            state = 'failed'
        result = 'failed'
    except Exception:  # noqa: BLE001 - worker boundary must persist uncertainty without secret output
        # No subprocess output, secrets or device responses in logs.
        logger.error('Server installation interrupted; job=%s requires verification', identity)
        state, result, error = 'uncertain', 'failed', 'local_failure'
    with database() as db:
        expire(db)
        changed = db.execute("UPDATE install_jobs SET state=?,result=?,error=?,revision=revision+1 "
                             "WHERE id=? AND state='running'", (state, result, error, identity)).rowcount
        if changed:
            audit(db, 'server', 'installation-result', identity, {'state': state, 'result': result, 'error': error})
