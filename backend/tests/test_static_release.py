"""发布必须同时保证 Nginx 可读、页面版本正确及入口资源可用。"""
import importlib.util
import io
from pathlib import Path
from urllib.error import HTTPError

import pytest

spec = importlib.util.spec_from_file_location(
    'static_release', Path(__file__).parents[2] / 'scripts/production/static_release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)
SHA = 'a' * 40
HTML = (f'<meta name="roombeacon-release" content="{SHA}">'
        '<script type="module" src="/assets/main.js"></script>'
        '<link rel="stylesheet" href="/assets/main.css">').encode()


def test_private_build_becomes_public_without_exposing_sibling_secrets(tmp_path):
    dist = tmp_path / 'frontend/dist'
    assets = dist / 'assets'
    assets.mkdir(parents=True)
    html, js, secret = dist / 'room-display.html', assets / 'main.js', tmp_path / 'v6.env'
    for path in (html, js, secret):
        path.write_text('fixture')
        path.chmod(0o600)
    for path in (dist, assets):
        path.chmod(0o700)
    assert not html.stat().st_mode & 0o004
    release.prepare_static(dist)
    assert all(path.stat().st_mode & 0o777 == 0o755 for path in (dist, assets))
    assert all(path.stat().st_mode & 0o777 == 0o644 for path in (html, js))
    assert secret.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('root_link', [False, True])
def test_symlink_is_rejected_before_any_permissions_change(tmp_path, root_link):
    secret = tmp_path / 'v6.env'
    secret.write_text('fixture')
    secret.chmod(0o600)
    dist = tmp_path / 'dist'
    if root_link:
        dist.symlink_to(tmp_path, target_is_directory=True)
    else:
        dist.mkdir(mode=0o700)
        (dist / 'secret').symlink_to(secret)
    with pytest.raises(ValueError):
        release.prepare_static(dist)
    assert secret.stat().st_mode & 0o777 == 0o600
    if not root_link:
        assert dist.stat().st_mode & 0o777 == 0o700


class Response(io.BytesIO):
    status = 200

    def __init__(self, body, content_type):
        super().__init__(body)
        self.headers = {'Content-Type': content_type}


def opener(failure=None):
    calls = []

    def open_url(request, timeout):
        calls.append((request.full_url, request.get_method()))
        path = request.full_url.removeprefix('https://example.test')
        if failure == path:
            raise HTTPError(request.full_url, 404, 'Not Found', {}, None)
        if path.startswith('/assets/'):
            kind = 'text/css' if path.endswith('.css') else 'application/javascript'
            return Response(b'', 'text/html' if failure == 'asset_type' else kind)
        html = HTML
        if failure == 'old_release':
            html = html.replace(SHA.encode(), b'b' * 40)
        elif failure == 'no_script':
            html = f'<meta name="roombeacon-release" content="{SHA}">'.encode()
        elif failure == 'external_asset':
            html = html.replace(b'/assets/main.js', b'https://other.test/main.js')
        return Response(html, 'application/json' if failure == 'page_type' else 'text/html')

    return open_url, calls


def test_probe_checks_managed_entry_controls_and_module_assets():
    open_url, calls = opener()
    release.verify_static('https://example.test', SHA, open_url)
    paths = {url.removeprefix('https://example.test') for url, _ in calls}
    assert {'/', '/control', '/control/legacy', '/assets/main.js', '/assets/main.css'} <= paths
    assert any('managed=1' in path for path in paths)
    assert ('https://example.test/assets/main.js', 'HEAD') in calls


@pytest.mark.parametrize('failure', [
    '/', '/control', '/assets/main.js', '/assets/main.css',
    'old_release', 'no_script', 'external_asset', 'page_type', 'asset_type',
])
def test_api_health_cannot_hide_broken_static_release(failure):
    open_url, calls = opener(failure)
    with pytest.raises((ValueError, HTTPError)):
        release.verify_static('https://example.test', SHA, open_url)
    assert all('other.test' not in url for url, _ in calls)
