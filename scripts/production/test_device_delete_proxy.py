"""用独立回环 Nginx 和假上游核对设备 DELETE，仅在有 nginx 的机器执行。"""
import http.client
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Upstream(BaseHTTPRequestHandler):
    def handle_request(self):
        authorized = self.headers.get('Authorization') == 'Bearer fixture-only'
        status = (204 if authorized else 401) if self.command == 'DELETE' else 200
        self.send_response(status)
        self.send_header('Content-Length', '0')
        self.end_headers()

    do_GET = do_PUT = do_POST = do_DELETE = handle_request

    def log_message(self, *args):
        pass


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def response(port, method, path, authorized=False):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
    try:
        conn.request(method, path, headers={'Authorization': 'Bearer fixture-only'} if authorized else {})
        result = conn.getresponse()
        result.read()
        return result.status
    finally:
        conn.close()


def main(template):
    binary = shutil.which('nginx')
    if not binary:
        raise SystemExit('需要 nginx；不能以跳过代替代理验收')
    upstream = ThreadingHTTPServer(('127.0.0.1', 0), Upstream)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix='roombeacon-delete-proxy-') as directory:
            root = Path(directory)
            port = free_port()
            server = Path(template).read_text().replace('listen 8080 default_server;',
                f'listen 127.0.0.1:{port} default_server;').replace(
                    'http://127.0.0.1:8088', f'http://127.0.0.1:{upstream.server_port}').replace(
                        '/data/roombeacon/current/frontend/dist', str(root))
            config = root / 'nginx.conf'
            config.write_text(f'worker_processes 1;\npid {root}/nginx.pid;\n'
                              f'error_log {root}/error.log;\nevents {{}}\nhttp {{ {server} }}\n')
            subprocess.run([binary, '-t', '-c', str(config), '-p', directory], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            process = subprocess.Popen([binary, '-c', str(config), '-p', directory, '-g', 'daemon off;'],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            try:
                for _ in range(50):
                    try:
                        if response(port, 'GET', '/api/v6/auth/options') == 200:
                            break
                    except OSError:
                        if process.poll() is not None:
                            raise AssertionError('隔离 Nginx 启动失败')
                    time.sleep(0.1)
                else:
                    raise AssertionError('隔离 Nginx 启动超时')
                device = '/api/v6/admin/devices/' + 'a' * 32
                cases = [('DELETE', device, False, 401), ('DELETE', device, True, 204),
                         ('PUT', device, True, 200), ('GET', device, True, 200),
                         ('DELETE', '/api/v6/admin/catalog', True, 403),
                         ('DELETE', device + '/reload', True, 403),
                         ('DELETE', '/api/v6/admin/devices/bad-id', True, 403),
                         ('PATCH', device, True, 403)]
                for method, path, authorized, expected in cases:
                    actual = response(port, method, path, authorized)
                    assert actual == expected, f'{method} {path}: expected {expected}, got {actual}'
                print(json.dumps({'isolated_nginx_proxy_cases': len(cases), 'production_requests': 0}))
            finally:
                process.terminate()
                process.wait(timeout=5)
    finally:
        upstream.shutdown()
        upstream.server_close()
        thread.join(timeout=5)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).with_name('roombeacon.nginx.conf'))
