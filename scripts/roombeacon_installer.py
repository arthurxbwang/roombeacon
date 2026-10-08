#!/usr/bin/env python3
"""现场首装助手：Python 3.10+ / Android platform-tools 与 build-tools。"""
import argparse
import getpass
import hashlib
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PACKAGE = 'com.roombeacon.shell'
MAX_APK = 64 * 1024 * 1024


class InstallError(Exception):
    """Only fixed error codes may cross the process/network boundary."""


def run(arguments, timeout=30):
    try:
        environment = {k: v for k, v in os.environ.items() if k != 'ROOMBEACON_INSTALLER_TOKEN'}
        result = subprocess.run([str(a) for a in arguments], capture_output=True, timeout=timeout,
                                check=False, env=environment)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise InstallError('local_failure') from exc
    if result.returncode:
        raise InstallError('local_failure')
    return result.stdout.decode('utf-8', errors='replace').strip()


def inspect_apk(path, aapt, apksigner, models):
    path = Path(path).resolve()
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_APK:
        raise InstallError('apk_invalid')
    try:
        badging = run([aapt, 'dump', 'badging', path])
        match = re.search(r"^package: name='([^']+)' versionCode='(\d+)' versionName='([^']+)'", badging, re.MULTILINE)
        signing = run([apksigner, 'verify', '--verbose', '--print-certs', path])
        certs = re.findall(r'^Signer #\d+ certificate SHA-256 digest: ([a-fA-F0-9]{64})$', signing, re.MULTILINE)
        if (not match or match[1] != PACKAGE or 'application-debuggable' in badging or
                len(certs) != 1 or not 0 < int(match[2]) <= 2100000000 or not models):
            raise InstallError('apk_invalid')
        return {'package': match[1], 'version_code': int(match[2]), 'version_name': match[3],
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'certificate_sha256': certs[0].lower(), 'size': path.stat().st_size,
                'models': sorted(set(models))}
    except InstallError as exc:
        raise InstallError('apk_invalid') from exc


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise InstallError('server_failure')


class Server:
    def __init__(self, origin, token):
        parsed = urllib.parse.urlsplit(origin)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or
                parsed.query or parsed.fragment or parsed.path not in ('', '/') or
                not re.fullmatch(r'rbi:[a-f0-9]{32}:[A-Za-z0-9_-]{43}', token)):
            raise InstallError('invalid_configuration')
        self.origin, self.token = origin.rstrip('/'), token
        self.opener = urllib.request.build_opener(NoRedirect())

    def post(self, path, body=None):
        request = urllib.request.Request(self.origin + '/api/v6/installer/' + path,
            data=json.dumps(body or {}).encode(), method='POST',
            headers={'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=15) as response:
                raw = response.read(65537)
                if len(raw) > 65536:
                    raise InstallError('server_failure')
                value = json.loads(raw)
                if not isinstance(value, dict) or value.get('code') != 0:
                    raise InstallError('server_failure')
                return value.get('data')
        except (OSError, ValueError, urllib.error.URLError) as exc:
            raise InstallError('server_failure') from exc


def validate_job(job, networks):
    try:
        address = ipaddress.IPv4Address(job['ip'])
        if not any(address in network for network in networks):
            raise ValueError('outside locally approved network')
        if (not re.fullmatch(r'[a-f0-9]{32}', job['id']) or
                not re.fullmatch(r'[A-Za-z0-9_-]{43}', job['lease']) or
                not re.fullmatch(r'[A-Za-z0-9._-]{1,100}', job['serial']) or
                type(job['port']) is not int or not 1 <= job['port'] <= 65535 or
                job['manifest']['package'] != PACKAGE):
            raise ValueError('invalid job')
    except (KeyError, TypeError, ValueError) as exc:
        raise InstallError('invalid_configuration') from exc


class Device:
    def __init__(self, adb, job):
        self.adb, self.job, self.transport = adb, job, ''

    def connect(self):
        endpoint = f"{self.job['ip']}:{self.job['port']}"
        try:
            run([self.adb, 'connect', endpoint], 20)
            listing = run([self.adb, 'devices', '-l'])
            for line in listing.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[0] == endpoint and parts[1] == 'device':
                    transport = re.search(r'\btransport_id:(\d+)\b', line)
                    if transport:
                        self.transport = transport[1]
            if not self.transport:
                raise InstallError('connection_failed')
            self.identity()
        except InstallError as exc:
            if str(exc) == 'identity_mismatch':
                raise
            raise InstallError('connection_failed') from exc

    def command(self, *args, timeout=30):
        # Pin this connection. Never fall back to the IP after reconnect or address reuse.
        if not self.transport:
            raise InstallError('connection_failed')
        return run([self.adb, '-t', self.transport, *args], timeout)

    def identity(self):
        if self.command('shell', 'getprop', 'ro.serialno') != self.job['serial']:
            raise InstallError('identity_mismatch')

    def existing(self, directory):
        packages = self.command('shell', 'pm', 'list', 'packages', PACKAGE).splitlines()
        if 'package:' + PACKAGE + '.debug' in packages:
            raise InstallError('existing_apk')
        if 'package:' + PACKAGE not in packages:
            return None
        paths = self.command('shell', 'pm', 'path', PACKAGE).splitlines()
        if len(paths) != 1 or not re.fullmatch(r'package:/data/app/[A-Za-z0-9_./=+~-]+\.apk', paths[0]):
            raise InstallError('existing_apk')
        saved = Path(directory) / 'installed.apk'
        self.command('pull', paths[0][8:], saved, timeout=60)
        return saved


def install(job, apk, adb, aapt, apksigner, authorize):
    """Only fresh installs or identical APK recovery; no upgrade, uninstall or data reset."""
    device = Device(adb, job)
    with tempfile.TemporaryDirectory(prefix='roombeacon-install-') as directory:
        snapshot = Path(directory) / 'approved.apk'
        if not Path(apk).is_file() or Path(apk).stat().st_size > MAX_APK:
            raise InstallError('apk_invalid')
        shutil.copyfile(apk, snapshot)
        actual = inspect_apk(snapshot, aapt, apksigner, job['manifest']['models'])
        if actual != job['manifest']:
            raise InstallError('apk_invalid')
        authorize()
        device.connect()
        if device.command('shell', 'getprop', 'ro.product.model') not in actual['models']:
            raise InstallError('model_mismatch')
        previous = device.existing(directory)
        if previous:
            if inspect_apk(previous, aapt, apksigner, actual['models']) != actual:
                raise InstallError('existing_apk')
            result = 'already_installed'
        else:
            authorize()
            device.identity()
            try:
                # Deliberately no -r, -d, -g: another installation must not be overwritten.
                output = device.command('install', snapshot, timeout=120)
                if output.splitlines()[-1:] != ['Success']:
                    raise InstallError('install_failed')
            except InstallError as exc:
                raise InstallError('install_failed') from exc
            result = 'installed'
        authorize()
        device.identity()
        installed = device.existing(directory)
        if not installed or inspect_apk(installed, aapt, apksigner, actual['models']) != actual:
            raise InstallError('verification_failed')
        try:
            launched = device.command('shell', 'am', 'start', '-W', '-n', PACKAGE + '/' + PACKAGE + '.MainActivity')
            if 'Status: ok' not in launched or 'Error' in launched:
                raise InstallError('launch_failed')
        except InstallError as exc:
            raise InstallError('launch_failed') from exc
        return result


def process(server, job, args, networks):
    validate_job(job, networks)
    started = time.monotonic()
    path = 'jobs/' + job['id']

    def authorize():
        # Leave enough time for bounded ADB operations; server time is authoritative.
        if time.monotonic() - started > 360:
            raise InstallError('server_failure')
        server.post(path + '/check', {'lease': job['lease']})

    try:
        result = install(job, args.apk, args.adb, args.aapt, args.apksigner, authorize)
        report = {'lease': job['lease'], 'result': result, 'error': ''}
    except InstallError as exc:
        if str(exc) == 'server_failure':
            raise  # Stop on revocation/lost network; backend will mark an expired lease uncertain.
        report = {'lease': job['lease'], 'result': 'failed', 'error': str(exc)}
    server.post(path + '/report', report)
    print(f"{job['ip']} {job['serial']}: {report['result']} {report['error']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['inspect-apk', 'run'])
    parser.add_argument('--apk', required=True, type=Path)
    parser.add_argument('--adb', default='adb')
    parser.add_argument('--aapt', default='aapt')
    parser.add_argument('--apksigner', default='apksigner')
    parser.add_argument('--model', action='append', default=[])
    parser.add_argument('--server', default='https://roombeacon.thundersoft.com')
    parser.add_argument('--allow-network', action='append', default=[])
    args = parser.parse_args()
    try:
        if args.action == 'inspect-apk':
            print(json.dumps(inspect_apk(args.apk, args.aapt, args.apksigner, args.model), ensure_ascii=False, indent=2))
            return 0
        if not args.allow_network:
            raise InstallError('invalid_configuration')
        networks = [ipaddress.IPv4Network(n) for n in args.allow_network]
        # No credential in argv, URL, config file, subprocess or progress output.
        token = os.environ.get('ROOMBEACON_INSTALLER_TOKEN') or getpass.getpass('安装助手凭证（隐藏输入）：')
        server = Server(args.server, token)
        while job := server.post('claim'):
            process(server, job, args, networks)
        print('本轮无可领取任务。待核实任务请到后台处理；新增任务后重新运行。')
        return 0
    except (InstallError, OSError, ValueError) as exc:
        code = str(exc) if isinstance(exc, InstallError) else 'local_failure'
        print('助手停止：' + code + '。检查后台与现场；不要直接重复安装。', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('助手已停止。已领取任务的实际结果须在后台核实。', file=sys.stderr)
        return 130


if __name__ == '__main__':
    sys.exit(main())
