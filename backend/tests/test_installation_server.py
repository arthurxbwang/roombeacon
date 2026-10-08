"""IP-first delivery: permission, probe snapshots and execution failure boundaries."""
from unittest.mock import Mock

import pytest

from app.management import installation_runtime as runtime
from app.management.store import database
from tests.test_installation import BASE, MANIFEST, overview, post
from tests.test_v6_management import admin, session
from tests.test_v6_management import client as management_client

client = management_client
DEVICE = {'serial': 'SERIAL-1', 'model': 'BX68', 'android': '11', 'existing': False}


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv('ROOM_DISPLAY_INSTALL_NETWORKS', '10.0.1.0/24')
    monkeypatch.setenv('ROOM_DISPLAY_INSTALL_ADB', '/test/adb')
    monkeypatch.setattr(runtime, 'tool_available', lambda _: True)
    monkeypatch.setattr(runtime, 'default_apk', lambda: ('/test/app.apk', MANIFEST))
    detect = Mock(return_value=DEVICE)
    monkeypatch.setattr(runtime, 'detect', detect)
    install = Mock(return_value='installed')
    monkeypatch.setattr(runtime.installer, 'install', install)
    return detect, install


def probe(client):
    response = post(client, '/probe', {'ip': '10.0.1.2'})
    assert response.status_code == 200, response.text
    return response.json()['data']


def initialize(client, value):
    return post(client, '/initialize', {'probe_id': value['id'], 'confirmed': True})


def test_probe_is_read_only_and_initialize_is_idempotent(client, configured):
    detect, install = configured
    value = probe(client)
    assert value['serial'] == 'SERIAL-1' and value['can_initialize']
    detect.assert_called_once_with('10.0.1.2', 5555)
    install.assert_not_called()
    assert overview(client)['jobs'] == []
    assert initialize(client, value).status_code == 200
    assert initialize(client, value).status_code == 200
    assert install.call_count == 1
    assert len(overview(client)['jobs']) == 1
    job = overview(client)['jobs'][0]
    assert job['state'] == 'installed' and job['executor_id'] == 'server'
    assert install.call_args.args[0]['serial'] == DEVICE['serial']


def test_probe_permissions_csrf_network_and_port_boundaries(client, configured):
    detect, install = configured
    assert client.post(BASE + '/probe', json={'ip': '10.0.1.2'}).status_code == 401
    for ip in ['127.0.0.1', '169.254.169.254', '8.8.8.8', '::1', 'example.com', '10.0.1.2;id', '10.0.2.1']:
        assert post(client, '/probe', {'ip': ip}).status_code == 422
    assert post(client, '/probe', {'ip': '10.0.1.2', 'port': 22}).status_code == 422
    me = session(client, 'viewer').json()['data']
    assert client.get(BASE + '/server').status_code == 200
    for path, body in [('/probe', {'ip': '10.0.1.2'}), ('/initialize', {'probe_id': 'a' * 32, 'confirmed': True})]:
        assert post(client, path, body, {'X-RB-CSRF': me['csrf']}).status_code == 403
    with database() as db:
        db.execute("UPDATE users SET role='admin'")
    assert post(client, '/probe', {'ip': '10.0.1.2'}, {}).status_code == 403
    detect.assert_not_called()
    install.assert_not_called()


def test_no_apk_still_probes_but_cannot_initialize(client, configured, monkeypatch):
    monkeypatch.setattr(runtime, 'default_apk', lambda: (_ for _ in ()).throw(runtime.conflict('尚未配置正式安装包')))
    value = probe(client)
    assert not value['can_initialize'] and '正式安装包' in value['blocker']
    assert initialize(client, value).status_code == 409
    configured[1].assert_not_called()


@pytest.mark.parametrize('change', ['expired', 'artifact', 'network', 'busy'])
def test_stale_probe_and_concurrent_target_cannot_initialize(client, configured, monkeypatch, change):
    value = probe(client)
    if change == 'expired':
        with database() as db:
            db.execute('UPDATE install_probes SET expires=0')
    elif change == 'artifact':
        monkeypatch.setattr(runtime, 'default_apk', lambda: ('/new.apk', MANIFEST | {'sha256': 'c' * 64}))
    elif change == 'network':
        monkeypatch.setenv('ROOM_DISPLAY_INSTALL_NETWORKS', '')
    else:
        with database() as db:
            db.execute("INSERT INTO install_jobs(id,batch_id,executor_id,release_id,ip,port,serial,state,created_at) "
                       "VALUES ('busy','b','e','r','10.0.1.2',5555,'SERIAL-1','uncertain',0)")
    assert initialize(client, value).status_code in (409, 422)
    configured[1].assert_not_called()


def test_existing_app_and_wrong_model_block_first_install(client, configured):
    for device in [DEVICE | {'existing': True}, DEVICE | {'model': 'OTHER'}]:
        configured[0].return_value = device
        value = probe(client)
        assert not value['can_initialize']
        assert initialize(client, value).status_code == 409
    configured[1].assert_not_called()


def test_worker_failure_and_loss_of_lease_remain_visible(client, configured):
    configured[1].side_effect = runtime.installer.InstallError('identity_mismatch')
    assert initialize(client, probe(client)).status_code == 200
    assert overview(client)['jobs'][0]['error'] == 'identity_mismatch'
    def expired(*args):
        with database() as db:
            db.execute('UPDATE install_jobs SET lease_until=0')
        args[-1]()
    configured[1].side_effect = expired
    assert initialize(client, probe(client)).status_code == 200
    assert overview(client)['jobs'][0]['state'] == 'uncertain'


def test_probe_transport_pinned_and_no_device_mutations(monkeypatch):
    calls = []
    def run(args, timeout=30):
        calls.append(args)
        if args[1:3] == ['connect', '10.0.1.2:5555']:
            return 'connected'
        if args[1:] == ['devices', '-l']:
            return '10.0.1.2:5555 device transport_id:7'
        assert args[1:3] == ['-t', '7']
        return {'ro.serialno': 'SERIAL-1', 'ro.product.model': 'BX68',
                'ro.build.version.release': '11', 'com.roombeacon.shell': ''}[args[-1]]
    monkeypatch.setenv('ROOM_DISPLAY_INSTALL_ADB', '/test/adb')
    monkeypatch.setattr(runtime.installer, 'run', run)
    assert runtime.detect('10.0.1.2', 5555) == DEVICE
    assert len(calls) == 6
    assert all('install' not in args and 'am' not in args for args in calls)


@pytest.mark.parametrize('listing', ['10.0.1.2:5555 unauthorized transport_id:7', '10.0.1.2:5555 offline transport_id:7', ''])
def test_unusable_adb_never_probes_another_transport(monkeypatch, listing):
    monkeypatch.setattr(runtime.installer, 'run', lambda args, timeout: listing)
    with pytest.raises(runtime.AppError):
        runtime.detect('10.0.1.2', 5555)


def test_missing_config_fails_closed(client, monkeypatch):
    monkeypatch.delenv('ROOM_DISPLAY_INSTALL_NETWORKS', raising=False)
    value = client.get(BASE + '/server', headers=admin()).json()['data']
    assert not value['probe_ready']
    assert post(client, '/probe', {'ip': '10.0.1.2'}).status_code == 409


def test_probe_owned_by_requester(client, configured):
    value = probe(client)
    me = session(client, 'admin').json()['data']
    assert post(client, '/initialize', {'probe_id': value['id'], 'confirmed': True},
                {'X-RB-CSRF': me['csrf']}).status_code == 409
    configured[1].assert_not_called()


def test_default_apk_requires_pinned_certificate_and_stable_snapshot(tmp_path, monkeypatch):
    apk = tmp_path / 'release.apk'
    apk.write_bytes(b'test-only-apk')
    for key, value in {'APK': str(apk), 'CERT_SHA256': 'b' * 64, 'MODELS': 'BX68'}.items():
        monkeypatch.setenv('ROOM_DISPLAY_INSTALL_' + key, value)
    monkeypatch.setattr(runtime, 'tool_available', lambda _: True)
    snapshots = []
    def inspect(path, *_):
        assert path != apk and path.read_bytes() == b'test-only-apk'
        snapshots.append(path)
        return MANIFEST
    monkeypatch.setattr(runtime.installer, 'inspect_apk', inspect)
    assert runtime.default_apk() == (str(apk), MANIFEST)
    assert not snapshots[0].exists()
    monkeypatch.setenv('ROOM_DISPLAY_INSTALL_CERT_SHA256', 'c' * 64)
    with pytest.raises(runtime.AppError):
        runtime.default_apk()
    monkeypatch.setattr(runtime.installer, 'inspect_apk', lambda *_: (_ for _ in ()).throw(runtime.installer.InstallError('apk_invalid')))
    with pytest.raises(runtime.AppError):
        runtime.default_apk()


def test_parallel_confirmations_create_only_one_job(client, configured):
    from concurrent.futures import ThreadPoolExecutor
    value = probe(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: initialize(client, value), range(2)))
    assert all(r.status_code == 200 for r in results)
    assert results[0].json()['data'] == results[1].json()['data']
    assert configured[1].call_count == 1


def test_no_tools_and_invalid_network_configuration_never_connect(client, configured, monkeypatch):
    for networks in ['0.0.0.0/0', '127.0.0.0/8', 'bad', '10.0.1.1/24']:
        monkeypatch.setenv('ROOM_DISPLAY_INSTALL_NETWORKS', networks)
        assert post(client, '/probe', {'ip': '10.0.1.2'}).status_code == 409
    monkeypatch.setenv('ROOM_DISPLAY_INSTALL_NETWORKS', '10.0.1.0/24')
    monkeypatch.setattr(runtime, 'tool_available', lambda _: False)
    assert post(client, '/probe', {'ip': '10.0.1.2'}).status_code == 409
    configured[0].assert_not_called()


def test_unexpected_worker_failure_does_not_publish_success(client, configured):
    configured[1].side_effect = OSError('private diagnostic must not appear in response or audit')
    assert initialize(client, probe(client)).status_code == 200
    job = overview(client)['jobs'][0]
    assert job['state'] == 'uncertain'
    assert 'private diagnostic' not in client.get(BASE, headers=admin()).text
    assert 'private diagnostic' not in client.get('/api/v6/admin/audit', headers=admin()).text
