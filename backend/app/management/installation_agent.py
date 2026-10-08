"""Narrow, expiring executor credentials; leases are never returned to the admin UI."""
import hmac
import json
import re
import secrets
import time

from fastapi import APIRouter, Request

from ..core.exceptions import AppError, UnauthorizedError
from ..core.response import ok
from .installation_models import Lease, Report
from .installation_store import conflict, expire, row
from .installation_store import installation_audit as audit
from .security import bearer
from .store import database, digest

router = APIRouter(prefix='/api/v6/installer')
LEASE_SECONDS = 600


def executor(db, request):
    token = bearer(request)
    match = re.fullmatch(r'rbi:([a-f0-9]{32}):[A-Za-z0-9_-]{43}', token)
    value = db.execute('SELECT * FROM install_executors WHERE id=?', (match[1],)).fetchone() if match else None
    if not value or value['revoked'] or value['expires'] <= time.time() or not hmac.compare_digest(value['secret_hash'], digest(token)):
        raise UnauthorizedError('安装助手凭证无效、已撤销或已过期')
    db.execute('UPDATE install_executors SET last_seen=? WHERE id=?', (int(time.time()), value['id']))
    return value


@router.post('/claim')
def claim(request: Request):
    with database() as db:
        who = executor(db, request)
        expire(db)
        # Sequential per executor; a lost response must not cause a second active lease.
        if db.execute("SELECT 1 FROM install_jobs WHERE executor_id=? AND state IN ('running','uncertain')",
                      (who['id'],)).fetchone():
            return ok(None)
        value = db.execute("SELECT * FROM install_jobs WHERE executor_id=? AND state='queued' ORDER BY created_at,rowid LIMIT 1",
                           (who['id'],)).fetchone()
        if not value:
            return ok(None)
        lease = secrets.token_urlsafe(32)
        until = int(time.time()) + LEASE_SECONDS
        db.execute("UPDATE install_jobs SET state='running',lease_hash=?,lease_until=?,revision=revision+1 WHERE id=?",
                   (digest(lease), until, value['id']))
        audit(db, who['id'], 'installation-claim', value['id'])
        return ok({'id': value['id'], 'ip': value['ip'], 'port': value['port'], 'serial': value['serial'],
                   'lease': lease, 'lease_until': until,
                   'manifest': json.loads(row(db, 'install_releases', value['release_id'])['manifest'])})


def leased(db, request, identity, lease):
    who = executor(db, request)
    value = row(db, 'install_jobs', identity)
    if who['id'] != value['executor_id'] or not hmac.compare_digest(value['lease_hash'], digest(lease)):
        raise UnauthorizedError('任务不属于此安装助手或执行凭证已失效')
    return who, value


@router.post('/jobs/{identity}/check')
def check(identity: str, body: Lease, request: Request):
    with database() as db:
        _, value = leased(db, request, identity, body.lease)
        if value['state'] != 'running' or value['lease_until'] <= time.time():
            raise conflict('执行期限结束，请停止安装并核实现场结果')
        return ok({'lease_until': value['lease_until']})


@router.post('/jobs/{identity}/report')
def report(identity: str, body: Report, request: Request):
    if (body.result == 'failed') != bool(body.error):
        raise AppError(422, '失败结果必须包含错误类别；成功结果不能包含错误', 422)
    with database() as db:
        who, value = leased(db, request, identity, body.lease)
        if value['state'] in ('installed', 'failed', 'associated', 'accepted'):
            if value['result'] == body.result and value['error'] == body.error:
                return ok()  # A lost acknowledgement can be safely replayed, without overwriting it.
            raise conflict('任务已有其他结果')
        if value['state'] != 'running' or value['lease_until'] <= time.time():
            raise conflict('结果超过执行期限，请人工核实')
        state = 'failed' if body.result == 'failed' else 'installed'
        db.execute('UPDATE install_jobs SET state=?,result=?,error=?,revision=revision+1 WHERE id=?',
                   (state, body.result, body.error, identity))
        audit(db, who['id'], 'installation-report', identity, {'result': body.result, 'error': body.error})
    return ok()
