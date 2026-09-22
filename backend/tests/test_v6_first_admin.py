"""One-time administrator election, including concurrent first callbacks."""
import hashlib
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.exceptions import AppError
from app.management import auth, bootstrap
from app.management.store import database
from app.room_display_main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_V6_DB', str(tmp_path / 'v6.db'))
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_FEISHU_LOGIN_ENABLED', True)
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_FEISHU_BOOTSTRAP_ADMIN_ONCE', False)
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_FEISHU_TENANT_KEY', '')
    monkeypatch.setattr(settings, 'FEISHU_APP_ID', 'test-app')
    return TestClient(app, base_url='https://roombeacon.thundersoft.com')


def identity(name='first', tenant='company'):
    return {'tenant_key': tenant, 'open_id': 'ou_' + name, 'name': name}


def callback(client):
    start = client.get('/api/v6/auth/feishu/start', follow_redirects=False)
    state = parse_qs(urlparse(start.headers['location']).query)['state'][0]
    return client.get('/api/v6/auth/feishu/callback', params={'state': state, 'code': 'test'},
                      follow_redirects=False)


def test_first_employee_only_and_no_reopening(client, monkeypatch):
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_FEISHU_BOOTSTRAP_ADMIN_ONCE', True)
    monkeypatch.setattr(auth, 'feishu_identity', AsyncMock(return_value=identity()))
    verify = AsyncMock()
    monkeypatch.setattr(bootstrap, 'verify_employee', verify)
    assert callback(client).status_code == 302
    assert client.get('/api/v6/auth/me').json()['data']['role'] == 'admin'
    verify.assert_awaited_once_with('ou_first')
    with database() as db:
        marker = db.execute("SELECT value FROM meta WHERE key='feishu_first_admin'").fetchone()[0]
        assert db.execute("SELECT COUNT(*) FROM audit WHERE action='first-admin'").fetchone()[0] == 1
        db.execute("UPDATE users SET role='disabled'")
    # Reopening the database and having zero administrators must not rearm election.
    monkeypatch.setattr(auth, 'feishu_identity', AsyncMock(return_value=identity('second')))
    assert callback(client).status_code == 302
    assert client.get('/api/v6/auth/me').status_code == 403
    with database() as db:
        assert db.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0] == 0
        assert db.execute("SELECT value FROM meta WHERE key='feishu_first_admin'").fetchone()[0] == marker


def test_parallel_first_logins_have_one_winner(client, monkeypatch):
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_FEISHU_BOOTSTRAP_ADMIN_ONCE', True)
    def finish(n):
        return bootstrap.complete_login(identity(str(n)), employee_verified=True)
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert len(list(pool.map(finish, range(8)))) == 8
    with database() as db:
        assert db.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM users WHERE role='pending'").fetchone()[0] == 7
        assert db.execute("SELECT COUNT(*) FROM audit WHERE action='first-admin'").fetchone()[0] == 1


def test_bootstrap_disabled_and_existing_admin_not_replaced(client, monkeypatch):
    bootstrap.complete_login(identity())
    with database() as db:
        assert db.execute('SELECT role FROM users').fetchone()[0] == 'pending'
        db.execute("UPDATE users SET role='admin'")
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_FEISHU_BOOTSTRAP_ADMIN_ONCE', True)
    bootstrap.complete_login(identity('second'), employee_verified=True)
    with database() as db:
        assert db.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0] == 1
        assert db.execute("SELECT value FROM meta WHERE key='feishu_first_admin'").fetchone()[0] == 'existing-admin'


def test_failed_employee_check_does_not_consume_election(client, monkeypatch):
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_FEISHU_BOOTSTRAP_ADMIN_ONCE', True)
    monkeypatch.setattr(auth, 'feishu_identity', AsyncMock(return_value=identity()))
    monkeypatch.setattr(bootstrap, 'verify_employee', AsyncMock(side_effect=AppError(403, 'not employee', 403)))
    result = callback(client)
    assert result.status_code == 302 and 'login_error' in result.headers['location']
    with database() as db:
        assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0
        assert not db.execute("SELECT 1 FROM meta WHERE key='feishu_first_admin'").fetchone()
    with pytest.raises(AppError):
        bootstrap.complete_login(identity(), employee_verified=False)


def test_tenant_pinned_and_rechecked_inside_transaction(client, monkeypatch):
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_FEISHU_BOOTSTRAP_ADMIN_ONCE', True)
    bootstrap.complete_login(identity(), employee_verified=True)
    with pytest.raises(AppError):
        bootstrap.complete_login(identity('outsider', 'other'), employee_verified=True)
    with database() as db:
        assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 1
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_FEISHU_TENANT_KEY', 'configured-company')
    with pytest.raises(AppError):
        bootstrap.complete_login(identity('third'))


def test_disabled_employee_cannot_be_bootstrap_winner(client, monkeypatch):
    bootstrap.complete_login(identity())
    with database() as db:
        db.execute("UPDATE users SET role='disabled'")
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_FEISHU_BOOTSTRAP_ADMIN_ONCE', True)
    with pytest.raises(AppError):
        bootstrap.complete_login(identity(), employee_verified=True)
    with database() as db:
        assert not db.execute("SELECT 1 FROM meta WHERE key='feishu_first_admin'").fetchone()


@pytest.mark.asyncio
@pytest.mark.parametrize('result', ['ok', 'wrong-user', 'resigned', 'frozen', 'no-scope', 'invalid'])
async def test_employee_membership_uses_application_tenant_token(monkeypatch, result):
    def response(body):
        return httpx.Response(200, json=body, request=httpx.Request('GET', 'https://open.feishu.cn'))
    post = AsyncMock(return_value=response({'code': 0, 'tenant_access_token': 'private-tenant-token'}))
    user = {'open_id': 'ou_employee', 'status': {'is_resigned': False, 'is_frozen': False}}
    if result == 'wrong-user':
        user['open_id'] = 'ou_other'
    if result in ('resigned', 'frozen'):
        user['status']['is_' + result] = True
    body = {'code': 0, 'data': {'user': user}}
    if result == 'no-scope':
        body = {'code': 99991672}
    if result == 'invalid':
        body = []
    get = AsyncMock(return_value=response(body))
    monkeypatch.setattr(httpx.AsyncClient, 'post', post)
    monkeypatch.setattr(httpx.AsyncClient, 'get', get)
    if result == 'ok':
        await bootstrap.verify_employee('ou_employee')
        assert get.call_args.kwargs['headers']['Authorization'] == 'Bearer private-tenant-token'
        assert get.call_args.kwargs['params'] == {'user_id_type': 'open_id'}
    else:
        with pytest.raises(AppError) as exc:
            await bootstrap.verify_employee('ou_employee')
        assert 'private-' not in str(exc.value)


def test_subject_is_verified_identity_hash(client, monkeypatch):
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_FEISHU_BOOTSTRAP_ADMIN_ONCE', True)
    bootstrap.complete_login(identity(), employee_verified=True)
    expected = hashlib.sha256(b'company:ou_first').hexdigest()
    with database() as db:
        assert db.execute("SELECT value FROM meta WHERE key='feishu_first_admin'").fetchone()[0] == expected
