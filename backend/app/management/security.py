"""V6 browser sessions and independently revocable device credentials."""
import hashlib
import hmac
import re
import secrets
import time

from fastapi import Request

from ..core.config import settings
from ..core.exceptions import AppError, UnauthorizedError
from .store import database, digest

ADMIN_COOKIE = '__Host-rb_admin'
DEVICE_COOKIE = '__Host-rb_device'
DEVICE_PATTERN = re.compile(r'v6d:([a-f0-9]{32}):([A-Za-z0-9_-]{43})')


def legacy_admin(token):
    return any(bool(expected.strip()) and len(expected) >= minimum and
               hmac.compare_digest(token.encode(), expected.encode()) for expected, minimum in (
                   (settings.ROOM_DISPLAY_CONTROL_TOKEN, 32), (settings.ROOM_DISPLAY_CONTROL_TOKEN_SECONDARY, 1)))


def bearer(request):
    value = request.headers.get('authorization', '')
    return value[7:] if value.startswith('Bearer ') else ''


def check_origin(request):
    origin = request.headers.get('origin')
    if origin and origin != settings.ROOM_DISPLAY_PUBLIC_ORIGIN:
        raise AppError(403, '请求来源不受信任', 403)
    if request.headers.get('sec-fetch-site') == 'cross-site':
        raise AppError(403, '不允许跨站请求', 403)


def actor(request: Request, write=False):
    token = bearer(request)
    if token and legacy_admin(token):
        return {'subject': 'legacy-admin', 'name': '主控管理员', 'role': 'admin', 'csrf': ''}
    raw = request.cookies.get(ADMIN_COOKIE, '')
    if not raw:
        raise UnauthorizedError('请登录管理后台')
    with database() as db:
        row = db.execute('SELECT * FROM sessions WHERE digest=? AND expires>?',
                         (digest(raw), int(time.time()))).fetchone()
        if not row:
            raise UnauthorizedError('管理会话已过期')
        user = ({'subject': 'legacy-admin', 'name': '主控管理员', 'role': 'admin'}
                if row['subject'] == 'legacy-admin' else db.execute(
                    'SELECT subject,name,role FROM users WHERE subject=?', (row['subject'],)).fetchone())
        if not user or user['role'] not in ('admin', 'viewer'):
            raise AppError(403, '账号等待管理员授权或已被停用', 403)
        result = dict(user) | {'csrf': row['csrf']}
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        check_origin(request)
        if not hmac.compare_digest(request.headers.get('x-rb-csrf', ''), result['csrf']):
            raise AppError(403, '操作校验已失效，请刷新后台', 403)
    if write and result['role'] != 'admin':
        raise AppError(403, '只读账号不能执行管理操作', 403)
    return result


def new_session(db, subject):
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(24)
    now = int(time.time())
    db.execute('DELETE FROM sessions WHERE expires<?', (now,))
    db.execute('INSERT INTO sessions VALUES (?,?,?,?)', (digest(token), subject, csrf, now + 8 * 3600))
    return token


def parse_device(token):
    match = DEVICE_PATTERN.fullmatch(token)
    if not match:
        raise UnauthorizedError('设备凭证无效')
    return match[1]


def device(db, token, active=False):
    identity = parse_device(token)
    row = db.execute('SELECT * FROM devices WHERE id=?', (identity,)).fetchone()
    if not row or not hmac.compare_digest(row['secret_hash'], digest(token)):
        raise UnauthorizedError('设备凭证无效')
    if active and row['status'] != 'active':
        raise UnauthorizedError('设备尚未激活或已撤销')
    return row


def web_session(db, row):
    expires = int(time.time()) + 300
    payload = f"{row['id']}:{row['revision']}:{expires}"
    key = db.execute("SELECT value FROM meta WHERE key='signing_key'").fetchone()[0]
    signature = hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f'v6w:{payload}:{signature}'


def authenticate_web(token):
    match = re.fullmatch(r'v6w:([a-f0-9]{32}):(\d{1,10}):(\d{1,12}):([a-f0-9]{64})', token)
    if not match or int(match[3]) <= time.time():
        raise UnauthorizedError('设备网页会话已过期')
    with database() as db:
        key = db.execute("SELECT value FROM meta WHERE key='signing_key'").fetchone()[0]
        payload = ':'.join(match.group(1, 2, 3))
        expected = hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, match[4]):
            raise UnauthorizedError('设备网页会话无效')
        row = db.execute('SELECT * FROM devices WHERE id=?', (match[1],)).fetchone()
        if not row or row['status'] != 'active' or row['revision'] != int(match[2]) or not row['room_id']:
            raise UnauthorizedError('设备绑定已变化')
        # Stable throughout a binding: cookie renewal must not reset V5 business health.
        return {'room_id': row['room_id'], 'digest': digest(f"v6:{row['id']}:{row['revision']}")}
