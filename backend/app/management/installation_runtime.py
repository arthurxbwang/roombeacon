"""Server-side first install. Operator-owned tools/artifact; no browser shell input."""
import importlib.util
import ipaddress
import os
import re
import shutil
import tempfile
from pathlib import Path

from ..core.exceptions import AppError
from .installation_models import Manifest
from .installation_store import conflict

_spec = importlib.util.spec_from_file_location(
    'roombeacon_install_worker', Path(__file__).resolve().parents[3] / 'scripts/roombeacon_installer.py')
installer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(installer)


def setting(name, default=''):
    return os.environ.get('ROOM_DISPLAY_INSTALL_' + name, default).strip()


def tool_available(tool):
    return bool(shutil.which(tool))


def tools():
    return (setting('ADB', 'adb'), setting('AAPT', 'aapt'), setting('APKSIGNER', 'apksigner'))


def status():
    networks = setting('NETWORKS')
    blocker = ''
    try:
        if not networks:
            raise ValueError()
        for value in networks.split(','):
            network = ipaddress.IPv4Network(value.strip())
            if not any(network.subnet_of(ipaddress.IPv4Network(n))
                       for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')):
                raise ValueError()
        if not 1 <= int(setting('PORT', '5555')) <= 65535:
            raise ValueError()
    except ValueError:
        blocker = '请先由运维配置设备网段与 ADB 端口'
    if not blocker and not tool_available(tools()[0]):
        blocker = '后台尚未配置 ADB 工具，请由运维完成一次性设置'
    return {'probe_ready': not blocker, 'blocker': blocker, 'networks': networks,
            'port': int(setting('PORT', '5555')) if not blocker else 5555,
            'apk_configured': bool(setting('APK') and setting('CERT_SHA256') and setting('MODELS'))}


def allowed(ip, port):
    state = status()
    if not state['probe_ready']:
        raise conflict(state['blocker'])
    address = ipaddress.IPv4Address(ip)
    if port != state['port'] or not any(address in ipaddress.IPv4Network(n.strip())
                                        for n in state['networks'].split(',')):
        raise AppError(422, 'IP 或端口不在已配置的设备网络范围内', 422)


def default_apk():
    apk, cert, models = setting('APK'), setting('CERT_SHA256'), setting('MODELS')
    if not apk or not cert or not models:
        raise conflict('尚未配置默认正式 APK，请由运维在高级设置说明中完成一次性配置')
    if not all(tool_available(t) for t in tools()[1:]):
        raise conflict('后台尚未配置 APK 校验工具')
    try:
        # Inspect a stable copy. Installation checks a fresh snapshot against this exact manifest.
        source = Path(apk)
        if not source.is_file() or not 0 < source.stat().st_size <= installer.MAX_APK:
            raise ValueError()
        with tempfile.TemporaryDirectory(prefix='roombeacon-inspect-') as directory:
            snapshot = Path(directory) / 'default.apk'
            shutil.copyfile(source, snapshot)
            manifest = Manifest.model_validate(installer.inspect_apk(
                snapshot, tools()[1], tools()[2], [m.strip() for m in models.split(',')])).model_dump()
        if manifest['certificate_sha256'] != cert.lower():
            raise ValueError()
        return apk, manifest
    except (OSError, ValueError, installer.InstallError) as exc:
        raise conflict('默认 APK 的正式签名、摘要或型号配置校验未通过，请联系运维') from exc


def detect(ip, port):
    adb = tools()[0]
    endpoint = f'{ip}:{port}'
    try:
        installer.run([adb, 'connect', endpoint], 8)
        listing = installer.run([adb, 'devices', '-l'], 3)
        transport = ''
        for line in listing.splitlines():
            parts = line.split()
            if len(parts) < 2 or parts[0] != endpoint:
                continue
            if parts[1] == 'unauthorized':
                raise conflict('设备尚未授权 ADB，请在设备上允许调试后重新检测')
            match = re.search(r'\btransport_id:(\d+)\b', line)
            if parts[1] == 'device' and match:
                transport = match[1]
        if not transport:
            raise conflict('无法连接设备 ADB，请检查 IP、设备联网和网络 ADB 开关')
        def command(*args):
            return installer.run([adb, '-t', transport, 'shell', *args], 5)
        serial = command('getprop', 'ro.serialno')
        model = command('getprop', 'ro.product.model')
        android = command('getprop', 'ro.build.version.release')
        packages = command('pm', 'list', 'packages', installer.PACKAGE).splitlines()
        if not re.fullmatch(r'[A-Za-z0-9._-]{1,100}', serial) or not model or len(model) > 100:
            raise conflict('无法读取有效设备序列号或型号，请检查厂家 ADB 权限')
        return {'serial': serial, 'model': model, 'android': android[:100],
                'existing': any(p in packages for p in ('package:' + installer.PACKAGE,
                                                       'package:' + installer.PACKAGE + '.debug'))}
    except installer.InstallError as exc:
        raise conflict('设备连接超时或读取失败，请检查联网与 ADB 授权后重新检测') from exc
