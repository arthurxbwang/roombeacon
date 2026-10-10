"""Mock the actual command boundary, including reconnect and hostile APK scenarios."""
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

spec = importlib.util.spec_from_file_location('installer', Path(__file__).parents[2] / 'scripts/roombeacon_installer.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
PACKAGE = installer.PACKAGE


@pytest.fixture
def equipment(tmp_path, monkeypatch):
    apk = tmp_path / 'formal.apk'
    apk.write_bytes(b'fake-apk-for-isolated-test')
    state = {'serial': 'SAMPLE', 'model': 'BX68', 'installed': False, 'debug': False, 'certificate': 'b' * 64,
             'installed_bytes': apk.read_bytes(), 'launch': 'Status: ok', 'debuggable': False, 'calls': []}

    def command(args, timeout=30):
        args = [str(a) for a in args]
        state['calls'].append(args)
        if args[0] == 'aapt':
            return f"package: name='{PACKAGE}' versionCode='10' versionName='0.7.0'\n" + ('application-debuggable' if state['debuggable'] else '')
        if args[0] == 'apksigner':
            return 'Signer #1 certificate SHA-256 digest: ' + state['certificate']
        if args == ['adb', 'connect', '10.0.1.2:5555']:
            return 'connected'
        if args == ['adb', 'devices', '-l']:
            return 'List of devices attached\n10.0.1.2:5555 device product:test transport_id:42'
        assert args[:3] == ['adb', '-t', '42'], args
        rest = args[3:]
        if rest == ['shell', 'getprop', 'ro.serialno']:
            return state['serial']
        if rest == ['shell', 'getprop', 'ro.product.model']:
            return state['model']
        if rest == ['shell', 'pm', 'list', 'packages', PACKAGE]:
            return ('package:' + PACKAGE if state['installed'] else '') + ('\npackage:' + PACKAGE + '.debug' if state['debug'] else '')
        if rest == ['shell', 'pm', 'path', PACKAGE]:
            return 'package:/data/app/~~abc==/com.roombeacon.shell-xyz==/base.apk'
        if rest[0] == 'pull':
            Path(rest[2]).write_bytes(state['installed_bytes'])
            return '1 file pulled'
        if rest[0] == 'install':
            assert len(rest) == 2  # No replacement/downgrade/permission-grant flags.
            state['installed'] = True
            return 'Performing Streamed Install\nSuccess'
        if rest == ['shell', 'am', 'start', '-W', '-n', PACKAGE + '/' + PACKAGE + '.MainActivity']:
            return state['launch']
        raise AssertionError(args)

    monkeypatch.setattr(installer, 'run', command)
    manifest = installer.inspect_apk(apk, 'aapt', 'apksigner', ['BX68'])
    job = {'id': '1' * 32, 'ip': '10.0.1.2', 'port': 5555, 'serial': 'SAMPLE', 'lease': 'a' * 43, 'manifest': manifest}
    return state, apk, job


def perform(equipment, authorize=lambda: None):
    _, apk, job = equipment
    return installer.install(job, apk, 'adb', 'aapt', 'apksigner', authorize)


def test_fresh_install_verifies_snapshot_transport_and_readback(equipment):
    state, apk, job = equipment
    assert perform(equipment) == 'installed'
    assert job['manifest']['sha256'] == hashlib.sha256(apk.read_bytes()).hexdigest()
    assert len([c for c in state['calls'] if c[3:4] == ['install']]) == 1
    state['calls'].clear()
    assert perform(equipment) == 'already_installed'
    assert not any(c[3:4] == ['install'] for c in state['calls'])


@pytest.mark.parametrize(('field', 'value', 'error'), [
    ('serial', 'WRONG', 'identity_mismatch'), ('model', 'OTHER', 'model_mismatch'),
    ('certificate', 'c' * 64, 'apk_invalid'), ('debuggable', True, 'apk_invalid'), ('debug', True, 'existing_apk')])
def test_preflight_refusals_never_install(equipment, field, value, error):
    state, _, _ = equipment
    state[field] = value
    with pytest.raises(installer.InstallError, match=error):
        perform(equipment)
    assert not any(c[3:4] == ['install'] for c in state['calls'])


def test_existing_other_apk_preserved_and_post_install_mismatch_fails(equipment):
    state, _, _ = equipment
    state['installed'], state['installed_bytes'] = True, b'other-apk'
    with pytest.raises(installer.InstallError, match='existing_apk'):
        perform(equipment)
    assert not any(c[3:4] == ['install'] for c in state['calls'])
    state['installed'] = False
    with pytest.raises(installer.InstallError, match='verification_failed'):
        perform(equipment)


def test_revocation_after_preflight_stops_before_install(equipment):
    state, _, _ = equipment
    count = 0

    def authorize():
        nonlocal count
        count += 1
        if count == 2:
            raise installer.InstallError('server_failure')

    with pytest.raises(installer.InstallError, match='server_failure'):
        perform(equipment, authorize)
    assert not any(c[3:4] == ['install'] for c in state['calls'])


def test_identity_rechecked_before_mutation(equipment):
    state, _, _ = equipment
    count = 0

    def authorize():
        nonlocal count
        count += 1
        if count == 2:
            state['serial'] = 'ADDRESS-REUSED'

    with pytest.raises(installer.InstallError, match='identity_mismatch'):
        perform(equipment, authorize)
    assert not any(c[3:4] == ['install'] for c in state['calls'])


def test_launch_failure_is_not_success(equipment):
    equipment[0]['launch'] = 'Error: activity not found'
    with pytest.raises(installer.InstallError, match='launch_failed'):
        perform(equipment)


def test_https_redirect_boundaries():
    token = 'rbi:' + 'a' * 32 + ':' + 'b' * 43
    for url in ['http://example.test', 'https://user:secret@example.test', 'https://example.test/private', 'https://example.test?token=1']:
        with pytest.raises(installer.InstallError):
            installer.Server(url, token)
    with pytest.raises(installer.InstallError):
        installer.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://elsewhere.test')


def test_process_reports_only_fixed_evidence(equipment, capsys):
    state, apk, job = equipment
    state['serial'] = 'WRONG'
    requests = []

    class Server:
        def post(self, path, body):
            requests.append((path, body))

    args = SimpleNamespace(apk=apk, adb='adb', aapt='aapt', apksigner='apksigner')
    installer.process(Server(), job, args)
    report = requests[-1][1]
    assert report == {'lease': job['lease'], 'result': 'failed', 'error': 'identity_mismatch'}
    assert job['lease'] not in capsys.readouterr().out
    assert 'WRONG' not in json.dumps(requests)


@pytest.mark.parametrize('ip', ['10.0.51.170', '10.99.3.4', '172.20.5.6', '192.168.8.9'])
def test_assistant_accepts_other_sites_without_local_allowlist(equipment, ip):
    installer.validate_job(equipment[2] | {'ip': ip})


@pytest.mark.parametrize('ip', ['127.0.0.1', '169.254.169.254', '8.8.8.8', '::1', 'example.com', '10.0.1.2;id'])
def test_assistant_rejects_non_lan_and_malformed_targets(equipment, ip):
    with pytest.raises(installer.InstallError, match='invalid_configuration'):
        installer.validate_job(equipment[2] | {'ip': ip})


@pytest.mark.parametrize('legacy_network', [None, '10.0.51.221/32', 'bad'])
def test_assistant_cli_needs_no_network_flag_and_ignores_legacy_flag(equipment, monkeypatch, legacy_network):
    _, apk, job = equipment
    argv = ['installer', 'run', '--apk', str(apk)]
    if legacy_network is not None:
        argv += ['--allow-network', legacy_network]
    monkeypatch.setattr('sys.argv', argv)
    monkeypatch.setenv('ROOMBEACON_INSTALLER_TOKEN', 'test-only-token')
    server = SimpleNamespace(post=Mock(side_effect=[job | {'ip': '172.20.5.6'}, None]))
    monkeypatch.setattr(installer, 'Server', lambda *_: server)
    process = Mock()
    monkeypatch.setattr(installer, 'process', process)
    assert installer.main() == 0
    assert process.call_args.args[1]['ip'] == '172.20.5.6'


def test_command_failures_sanitized_and_token_not_inherited(monkeypatch):
    monkeypatch.setenv('ROOMBEACON_INSTALLER_TOKEN', 'private-test-token')

    def execute(args, **kwargs):
        assert 'ROOMBEACON_INSTALLER_TOKEN' not in kwargs['env']
        return SimpleNamespace(returncode=1, stdout=b'private-response', stderr=b'private-response')

    monkeypatch.setattr(installer.subprocess, 'run', execute)
    with pytest.raises(installer.InstallError) as error:
        installer.run(['adb', 'devices'])
    assert str(error.value) == 'local_failure'
