"""Explicitly armed, durable election of exactly one initial employee administrator."""
import hashlib
import time
from urllib.parse import quote

import httpx

from ..core.config import settings
from ..core.exceptions import AppError
from .security import new_session
from .store import audit, database

MARKER = 'feishu_first_admin'
TENANT = 'feishu_login_tenant'


def needs_employee_check():
    if not settings.ROOM_DISPLAY_FEISHU_BOOTSTRAP_ADMIN_ONCE:
        return False
    with database() as db:
        return not db.execute('SELECT 1 FROM meta WHERE key=?', (MARKER,)).fetchone()


async def verify_employee(open_id):
    """Check membership using this app's tenant token, never a login user's token."""
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
            reply = await client.post('https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
                                      json={'app_id': settings.FEISHU_APP_ID, 'app_secret': settings.FEISHU_APP_SECRET})
            reply.raise_for_status()
            value = reply.json()
            token = value.get('tenant_access_token')
            if value.get('code') != 0 or not isinstance(token, str) or not token:
                raise ValueError('tenant token unavailable')
            reply = await client.get('https://open.feishu.cn/open-apis/contact/v3/users/' + quote(open_id, safe=''),
                                     params={'user_id_type': 'open_id'}, headers={'Authorization': 'Bearer ' + token})
            reply.raise_for_status()
            value = reply.json()
            user = value.get('data', {}).get('user', {})
            status = user.get('status', {})
            if (value.get('code') != 0 or user.get('open_id') != open_id
                    or any(status.get(k) for k in ('is_resigned', 'is_frozen', 'is_exited'))):
                raise ValueError('employee unavailable')
    except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
        raise AppError(502, '首次管理员员工身份核验失败，请检查通讯录可用范围后重试', 502) from exc


def complete_login(identity, employee_verified=False):
    subject = hashlib.sha256((identity['tenant_key'] + ':' + identity['open_id']).encode()).hexdigest()
    # BEGIN IMMEDIATE serializes election, tenant pinning, user and session creation.
    with database() as db:
        pinned = db.execute('SELECT value FROM meta WHERE key=?', (TENANT,)).fetchone()
        tenants = [settings.ROOM_DISPLAY_FEISHU_TENANT_KEY, pinned['value'] if pinned else '']
        if any(tenant and tenant != identity['tenant_key'] for tenant in tenants):
            raise AppError(403, '该飞书企业未获授权', 403)
        db.execute('INSERT INTO users(subject,tenant,name,created_at) VALUES (?,?,?,?) '
                   'ON CONFLICT(subject) DO UPDATE SET name=excluded.name',
                   (subject, identity['tenant_key'], str(identity.get('name', '飞书用户'))[:100], int(time.time())))
        if (settings.ROOM_DISPLAY_FEISHU_BOOTSTRAP_ADMIN_ONCE
                and not db.execute('SELECT 1 FROM meta WHERE key=?', (MARKER,)).fetchone()):
            if db.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
                db.execute('INSERT INTO meta VALUES (?,?)', (MARKER, 'existing-admin'))
                audit(db, subject, 'first-admin-skipped', subject)
            else:
                role = db.execute('SELECT role FROM users WHERE subject=?', (subject,)).fetchone()['role']
                if not employee_verified or role == 'disabled':
                    raise AppError(403, '首次管理员身份尚未通过核验', 403)
                db.execute('INSERT INTO meta VALUES (?,?)', (MARKER, subject))
                db.execute('INSERT OR IGNORE INTO meta VALUES (?,?)', (TENANT, identity['tenant_key']))
                db.execute("UPDATE users SET role='admin' WHERE subject=?", (subject,))
                audit(db, subject, 'first-admin', subject)
        token = new_session(db, subject)
        audit(db, subject, 'feishu-login', subject)
    return token
