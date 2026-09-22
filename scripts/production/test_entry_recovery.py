"""在独立回环端口验证生产单元的重启策略，不终止生产进程。

在目标服务器以root执行。临时实例采用实际生产单元的Restart/RestartSec，
Caddy同步采用其--resume状态；测试结束清理临时单元与数据。
"""
import json
import os
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def run(*args, check=True):
    return subprocess.run(args, check=check, capture_output=True, text=True).stdout.strip()


def properties(service):
    raw = run('systemctl', 'show', service, '-p', 'Restart', '-p', 'RestartUSec',
              '-p', 'ExecStart', '-p', 'StartLimitIntervalUSec', '-p', 'StartLimitBurst')
    return dict(line.split('=', 1) for line in raw.splitlines())


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def read_body(url):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=.5) as response:
        return response.read().decode()


def wait_for_body(url, expected, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if read_body(url) == expected:
                return True
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(.2)
    return False


def test_service(service):
    policy = properties(service)
    unit = f'roombeacon-recovery-test-{service}-{os.getpid()}'
    with tempfile.TemporaryDirectory(prefix='roombeacon-recovery-', dir='/run') as temp:
        folder = Path(temp)
        port = free_port()
        url = f'http://127.0.0.1:{port}/'
        start = ['systemd-run', '--quiet', '--unit=' + unit,
                 '--property=Restart=' + policy['Restart'],
                 '--property=RestartSec=' + policy['RestartUSec'],
                 '--property=StartLimitIntervalSec=' + policy['StartLimitIntervalUSec'],
                 '--property=StartLimitBurst=' + policy['StartLimitBurst']]
        expected = 'recovery-ok'
        if service == 'caddy':
            admin_port = free_port()
            config = {'admin': {'listen': f'127.0.0.1:{admin_port}'},
                      'apps': {'http': {'servers': {'probe': {
                          'listen': [f'127.0.0.1:{port}'],
                          'routes': [{'handle': [{'handler': 'static_response',
                                                  'body': 'initial'}]}],
                      }}}}}
            source = folder / 'config.json'
            source.write_text(json.dumps(config))
            start += ['--setenv=XDG_CONFIG_HOME=' + str(folder / 'config'),
                      '--setenv=XDG_DATA_HOME=' + str(folder / 'data'),
                      '--property=Type=notify', '/usr/bin/caddy', 'run', '--config', str(source)]
            if '--resume' in policy['ExecStart']:
                start.append('--resume')
        else:
            source = folder / 'nginx.conf'
            pidfile = folder / 'nginx.pid'
            source.write_text(f'pid {pidfile};\nerror_log {folder}/error.log;\n'
                              'events {}\nhttp { access_log off; server {\n'
                              f'listen 127.0.0.1:{port};\n'
                              'location / { return 200 "recovery-ok"; } } }\n')
            start += ['--property=Type=forking', '--property=KillMode=mixed',
                      '--property=PIDFile=' + str(pidfile), '/usr/sbin/nginx',
                      '-c', str(source), '-p', str(folder)]
        try:
            run(*start)
            assert wait_for_body(url, 'initial' if service == 'caddy' else expected, 10), 'startup failed'
            if service == 'caddy':
                config['apps']['http']['servers']['probe']['routes'][0]['handle'][0]['body'] = expected
                request = urllib.request.Request(f'http://127.0.0.1:{admin_port}/load',
                                                 data=json.dumps(config).encode(),
                                                 headers={'Content-Type': 'application/json'}, method='POST')
                with urllib.request.urlopen(request, timeout=3) as response:
                    assert response.status == 200
                assert wait_for_body(url, expected, 3), 'dynamic configuration failed'
            old_pid = run('systemctl', 'show', unit, '-p', 'MainPID', '--value')
            run('systemctl', 'kill', '--kill-who=main', '--signal=SIGKILL', unit)
            recovered = wait_for_body(url, expected, 12)
            new_pid = run('systemctl', 'show', unit, '-p', 'MainPID', '--value')
            restarts = int(run('systemctl', 'show', unit, '-p', 'NRestarts', '--value'))
            passed = recovered and old_pid != new_pid and new_pid != '0' and restarts >= 1
            print(json.dumps({'service': service, 'passed': passed, 'restart_policy': policy['Restart'],
                              'restart_delay': policy['RestartUSec'], 'restarts': restarts,
                              'dynamic_config_restored': recovered if service == 'caddy' else None}), flush=True)
            return passed
        finally:
            run('systemctl', 'stop', unit, check=False)
            run('systemctl', 'reset-failed', unit, check=False)


if __name__ == '__main__':
    results = [test_service(name) for name in ('caddy', 'nginx')]
    raise SystemExit(0 if all(results) else 1)
