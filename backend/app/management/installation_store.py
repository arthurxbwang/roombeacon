"""Durable install queue. An expired lease is uncertain, never silently requeued."""
import json
import time

from ..core.exceptions import AppError

SCHEMA = """
CREATE TABLE IF NOT EXISTS install_executors (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, secret_hash TEXT NOT NULL,
 revoked INTEGER NOT NULL DEFAULT 0, expires INTEGER NOT NULL, last_seen INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS install_releases (
 id TEXT PRIMARY KEY, manifest TEXT NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS install_batches (
 id TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS install_jobs (
 id TEXT PRIMARY KEY, batch_id TEXT NOT NULL, executor_id TEXT NOT NULL, release_id TEXT NOT NULL,
 ip TEXT NOT NULL, port INTEGER NOT NULL, serial TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'queued', revision INTEGER NOT NULL DEFAULT 1,
 lease_hash TEXT NOT NULL DEFAULT '', lease_until INTEGER NOT NULL DEFAULT 0,
 result TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
 device_id TEXT NOT NULL DEFAULT '', acceptance TEXT NOT NULL DEFAULT '{}',
 created_at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS install_jobs_queue ON install_jobs(executor_id,state,created_at);
"""


def row(db, table, identity):
    # Table names are internal constants, never request data.
    value = db.execute(f'SELECT * FROM {table} WHERE id=?', (identity,)).fetchone()
    if not value:
        raise AppError(404, '安装对象不存在', 404)
    return value


def conflict(message='任务已变化，请刷新后重试'):
    return AppError(409, message, 409)


def expire(db):
    db.execute("UPDATE install_jobs SET state='uncertain', revision=revision+1 "
               "WHERE state='running' AND lease_until<=?", (int(time.time()),))


def current(db, identity, revision):
    expire(db)
    value = row(db, 'install_jobs', identity)
    if value['revision'] != revision:
        raise conflict()
    return value


def release_view(value):
    return dict(value) | {'manifest': json.loads(value['manifest'])}


def job_view(db, value):
    result = dict(value)
    result.pop('lease_hash')
    result['acceptance'] = json.loads(value['acceptance'])
    device = db.execute('SELECT * FROM devices WHERE id=?', (value['device_id'],)).fetchone()
    result['device_code'] = device['code'] if device else ''
    result['acceptance_current'] = bool(device and result['acceptance'] and
        device['status'] == 'active' and device['revision'] == result['acceptance']['device_revision'] and
        device['room_id'] == result['acceptance']['room_id'] and matches_release(db, device, value))
    result['device_ready'] = ready(device)
    return result


def ready(device):
    return bool(device and device['status'] == 'active' and device['room_id'] and not device['error'] and
                device['revision'] == device['reported_revision'] and time.time() - device['last_seen'] < 60)


def matches_release(db, device, job):
    manifest = json.loads(row(db, 'install_releases', job['release_id'])['manifest'])
    metadata = json.loads(device['metadata'])
    return (metadata.get('apk') == manifest['version_name'] and metadata.get('model') in manifest['models'] and
            (not metadata.get('serial') or metadata['serial'] == job['serial']))


def installation_audit(db, subject, action, target, detail=None):
    from .store import audit

    detail = dict(detail or {})
    executor = db.execute('SELECT name FROM install_executors WHERE id=?', (subject,)).fetchone()
    if executor:
        detail['actor_name'] = '安装助手 ' + executor['name']
    job = db.execute('SELECT ip,serial FROM install_jobs WHERE id=?', (target,)).fetchone()
    if job:
        detail['target_name'] = f"{job['ip']} / {job['serial']}"
    elif detail.get('name'):
        detail['target_name'] = detail['name']
    elif detail.get('version_name'):
        detail['target_name'] = 'APK ' + detail['version_name']
    elif detail.get('count'):
        detail['target_name'] = f"首装批次（{detail['count']} 台）"
    audit(db, subject, action, target, detail)
