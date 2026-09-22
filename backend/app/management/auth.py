"""Feishu login binds browser state, exchanges codes server-side and defaults to no role."""
import hmac
import secrets
import time
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from ..core.config import settings
from ..core.exceptions import AppError, UnauthorizedError
from ..core.response import ok
from . import bootstrap
from .models import Role
from .security import (
    ADMIN_COOKIE,
    actor,
    bearer,
    check_origin,
    legacy_admin,
    new_session,
)
from .store import audit, database, digest, rate_limit

router = APIRouter(prefix='/api/v6/auth')
STATE_COOKIE = '__Host-rb_oauth'


def cookie(response, name, value, seconds):
    response.set_cookie(name, value, max_age=seconds, secure=True, httponly=True, samesite='lax', path='/')


@router.get('/options')
def options():
    # Public login bootstrap only; never returns business data or credentials.
    return ok({'feishu': settings.ROOM_DISPLAY_FEISHU_LOGIN_ENABLED and bool(settings.FEISHU_APP_ID),
               'version': 'V6'})


@router.post('/session')
def login(request: Request):
    check_origin(request)
    rate_limit('login:' + (request.client.host if request.client else 'unknown'), 10, 60)
    if not legacy_admin(bearer(request)):
        raise UnauthorizedError('主控凭证无效')
    with database() as db:
        token = new_session(db, 'legacy-admin')
        audit(db, 'legacy-admin', 'login', 'legacy-admin')
    from fastapi.responses import JSONResponse
    response = JSONResponse({'code': 0, 'message': 'ok', 'data': {'authenticated': True}})
    cookie(response, ADMIN_COOKIE, token, 8 * 3600)
    return response


@router.get('/me')
def me(request: Request):
    return ok(actor(request))


@router.post('/logout')
def logout(request: Request):
    check_origin(request)
    # Also permit pending users to sign out; origin + custom header prevents CSRF.
    if request.headers.get('x-rb-logout') != '1':
        raise AppError(403, '操作来源无效', 403)
    with database() as db:
        db.execute('DELETE FROM sessions WHERE digest=?', (digest(request.cookies.get(ADMIN_COOKIE, '')),))
    from fastapi.responses import JSONResponse
    response = JSONResponse({'code': 0, 'message': 'ok', 'data': {}})
    response.delete_cookie(ADMIN_COOKIE, secure=True, httponly=True, samesite='lax')
    return response


@router.get('/feishu/start')
def start(request: Request):
    if not settings.ROOM_DISPLAY_FEISHU_LOGIN_ENABLED or not settings.FEISHU_APP_ID:
        raise AppError(503, '飞书登录尚未配置，请使用主控入口', 503)
    rate_limit('oauth:' + (request.client.host if request.client else 'unknown'), 15)
    state, browser = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with database() as db:
        db.execute('DELETE FROM oauth WHERE expires<?', (int(time.time()),))
        db.execute('INSERT INTO oauth VALUES (?,?,?)', (digest(state), digest(browser), int(time.time()) + 300))
    query = urlencode({'client_id': settings.FEISHU_APP_ID, 'response_type': 'code', 'state': state,
                       'redirect_uri': settings.ROOM_DISPLAY_PUBLIC_ORIGIN + '/api/v6/auth/feishu/callback'})
    response = RedirectResponse('https://accounts.feishu.cn/open-apis/authen/v1/authorize?' + query, status_code=302)
    cookie(response, STATE_COOKIE, browser, 300)
    return response


async def feishu_identity(code):
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
            reply = await client.post('https://open.feishu.cn/open-apis/authen/v2/oauth/token', json={
                'grant_type': 'authorization_code', 'client_id': settings.FEISHU_APP_ID,
                'client_secret': settings.FEISHU_APP_SECRET, 'code': code,
                'redirect_uri': settings.ROOM_DISPLAY_PUBLIC_ORIGIN + '/api/v6/auth/feishu/callback'})
            reply.raise_for_status()
            data = reply.json()
            token = data.get('access_token')
            if data.get('code', 0) != 0 or not isinstance(token, str) or not token:
                raise ValueError('token response')
            reply = await client.get('https://open.feishu.cn/open-apis/authen/v1/user_info',
                                     headers={'Authorization': 'Bearer ' + token})
            reply.raise_for_status()
            data = reply.json()
            value = data.get('data', {})
            if data.get('code') != 0 or not all(isinstance(value.get(k), str) and value[k]
                                               for k in ('open_id', 'tenant_key')):
                raise ValueError('identity response')
            return value
    except (httpx.HTTPError, ValueError, TypeError, AttributeError) as exc:
        # Never expose upstream body, authorization code or token.
        raise AppError(502, '飞书登录暂未完成，请核对应用配置后重试', 502) from exc


@router.get('/feishu/callback')
async def callback(request: Request, state: str = '', code: str = ''):
    if not settings.ROOM_DISPLAY_FEISHU_LOGIN_ENABLED:
        raise AppError(503, '飞书登录尚未配置', 503)
    if not state or not code or len(state) > 128 or len(code) > 2048:
        return RedirectResponse('/control?login_error=feishu', status_code=302)
    with database() as db:
        row = db.execute('SELECT * FROM oauth WHERE state=?', (digest(state),)).fetchone()
        if not row or row['expires'] <= time.time() or not hmac.compare_digest(
                row['verifier'], digest(request.cookies.get(STATE_COOKIE, ''))):
            raise UnauthorizedError('登录请求已过期，请重新发起')
        db.execute('DELETE FROM oauth WHERE state=?', (digest(state),))
    try:
        identity = await feishu_identity(code)
        verified = bootstrap.needs_employee_check()
        if verified:
            await bootstrap.verify_employee(identity['open_id'])
        token = bootstrap.complete_login(identity, employee_verified=verified)
    except AppError:
        return RedirectResponse('/control?login_error=feishu', status_code=302)
    response = RedirectResponse('/control', status_code=302)
    cookie(response, ADMIN_COOKIE, token, 8 * 3600)
    response.delete_cookie(STATE_COOKIE, secure=True, httponly=True, samesite='lax')
    return response


@router.get('/users')
def users(request: Request):
    actor(request, write=True)
    with database() as db:
        return ok([dict(row) for row in db.execute('SELECT * FROM users ORDER BY created_at DESC LIMIT 1000')])


@router.put('/users/{subject}')
def role(subject: str, body: Role, request: Request):
    user = actor(request, write=True)
    if subject == user['subject'] and body.role != 'admin':
        raise AppError(409, '不能取消自己的管理员权限', 409)
    with database() as db:
        old = db.execute('SELECT * FROM users WHERE subject=?', (subject,)).fetchone()
        if not old:
            raise AppError(404, '用户不存在', 404)
        db.execute('UPDATE users SET role=? WHERE subject=?', (body.role, subject))
        if old['role'] != body.role:
            db.execute('DELETE FROM sessions WHERE subject=?', (subject,))
        audit(db, user['subject'], 'role', subject, {'role': body.role})
    return ok({'role': body.role})
