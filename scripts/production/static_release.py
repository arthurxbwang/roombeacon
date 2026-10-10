"""准备公开静态产物，并在发布前后核对页面与入口资源。"""
import argparse
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


def prepare_static(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Static root must be a real directory')
    items = [root, *root.rglob('*')]
    if any(p.is_symlink() or not (p.is_dir() or p.is_file()) for p in items):
        raise ValueError('Static output contains a link or special file')
    # 不依赖调用者的 umask；只改变公开 dist，不触碰配置、源码和备份。
    for path in items:
        path.chmod(0o755 if path.is_dir() else 0o644)


class Entry(HTMLParser):
    def __init__(self):
        super().__init__()
        self.releases = []
        self.assets = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta' and attrs.get('name') == 'roombeacon-release':
            self.releases.append(attrs.get('content'))
        if tag == 'script' and attrs.get('type') == 'module' and attrs.get('src'):
            self.assets.append((attrs['src'], 'javascript'))
        if tag == 'link' and attrs.get('href'):
            if attrs.get('rel') == 'stylesheet':
                self.assets.append((attrs['href'], 'text/css'))
            elif attrs.get('rel') == 'modulepreload':
                self.assets.append((attrs['href'], 'javascript'))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def verify_static(origin, sha, open_url=None):
    origin = origin.rstrip('/')
    parsed = urlsplit(origin)
    if (parsed.scheme not in {'http', 'https'} or not parsed.netloc or parsed.path
            or parsed.query or parsed.fragment or parsed.username or parsed.password
            or not re.fullmatch('[0-9a-f]{40}', sha)):
        raise ValueError('Expected an origin and full release SHA')
    open_url = open_url or build_opener(NoRedirect()).open
    assets = set()
    for path in ('/', '/?version=v6&managed=1&theme=auto&lang=zh-CN', '/control', '/control/legacy'):
        url = origin + path
        request = Request(url, headers={'Cache-Control': 'no-cache'})
        with open_url(request, timeout=10) as response:
            if response.status != 200 or 'text/html' not in response.headers.get('Content-Type', ''):
                raise ValueError('Public page is unavailable or has the wrong content type')
            body = response.read(1024 * 1024 + 1)
        if len(body) > 1024 * 1024:
            raise ValueError('Unexpected public page size')
        entry = Entry()
        entry.feed(body.decode('utf-8'))
        if entry.releases != [sha] or not any(kind == 'javascript' for _, kind in entry.assets):
            raise ValueError('Public page release or entry module differs')
        for path, kind in entry.assets:
            asset = urljoin(url, path)
            parts = urlsplit(asset)
            if (parts.scheme, parts.netloc) != (parsed.scheme, parsed.netloc):
                raise ValueError('Unexpected external entry resource')
            assets.add((asset, kind))
    for url, kind in sorted(assets):
        with open_url(Request(url, method='HEAD'), timeout=10) as response:
            if response.status != 200 or kind not in response.headers.get('Content-Type', ''):
                raise ValueError('Public entry resource is unavailable or has the wrong content type')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'verify'])
    parser.add_argument('target')
    parser.add_argument('sha', nargs='?')
    args = parser.parse_args()
    if args.action == 'prepare':
        prepare_static(args.target)
        return
    # Nginx reload 为异步；仅重试只读探针，失败交给部署脚本回退。
    for attempt in range(20):
        try:
            verify_static(args.target, args.sha or '')
            return
        except (OSError, URLError, ValueError):
            if attempt == 19:
                raise SystemExit('Static release verification failed; no response body logged') from None
            time.sleep(1)


if __name__ == '__main__':
    main()
