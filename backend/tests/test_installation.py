"""Real SQLite/API tests; no production devices, ADB or upstream systems."""
import json
import secrets
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.management.store import database
from tests.test_v6_management import (
    admin,
    configure,
    enroll,
    session,
    web_cookie,
)
from tests.test_v6_management import (
    client as management_client,
)

BASE = '/api/v6/admin/installation'
AGENT = '/api/v6/installer'
MANIFEST = {'package': 'com.roombeacon.shell', 'version_code': 10, 'version_name': '0.7.0',
            'sha256': 'a' * 64, 'certificate_sha256': 'b' * 64, 'size': 1234, 'models': ['BX68']}


client = management_client


def post(client, path, body=None, headers=None):
    return client.post(BASE + path, headers=admin() if headers is None else headers, json=body or {})


def setup_job(client, targets=None):
    who = post(client, '/executors', {'name': '现场电脑'}).json()['data']
    release = post(client, '/releases', MANIFEST).json()['data']
    body = {'request_id': secrets.token_hex(16), 'executor_id': who['id'], 'release_id': release['id'],
            'targets': targets or [{'ip': '10.0.1.2', 'serial': 'SAMPLE-1'}]}
    assert post(client, '/batches', body).status_code == 200
    return who, body


def agent(client, path, who, body=None):
    return client.post(AGENT + path, headers={'Authorization': 'Bearer ' + who['token']}, json=body or {})


def overview(client):
    return client.get(BASE, headers=admin()).json()['data']


def installed(client):
    who, _ = setup_job(client)
    job = agent(client, '/claim', who).json()['data']
    assert agent(client, '/jobs/' + job['id'] + '/report', who,
                 {'lease': job['lease'], 'result': 'installed'}).status_code == 200
    return who, job


def test_batch_atomic_idempotent_and_target_validation(client):
    _, body = setup_job(client)
    assert post(client, '/batches', body).status_code == 200
    assert len(overview(client)['jobs']) == 1
    assert post(client, '/batches', body | {'targets': [{'ip': '10.0.1.3', 'serial': 'OTHER'}]}).status_code == 409
    fresh = body | {'request_id': secrets.token_hex(16)}
    assert post(client, '/batches', fresh).status_code == 409
    for ip in ['127.0.0.1', '8.8.8.8', '169.254.169.254', '::1', '10.0.1.2;id']:
        assert post(client, '/batches', fresh | {'targets': [{'ip': ip, 'serial': 'OTHER'}]}).status_code == 422
    for serial in ['x;id', 'x y', '']:
        assert post(client, '/batches', fresh | {'targets': [{'ip': '10.0.1.9', 'serial': serial}]}).status_code == 422
    assert post(client, '/batches', fresh | {'targets': [body['targets'][0]] * 2}).status_code == 422
    assert post(client, '/releases', MANIFEST | {'package': 'com.roombeacon.shell.debug'}).status_code == 422
    assert len(overview(client)['jobs']) == 1


def test_executor_scope_secrets_report_replay_and_revoke(client):
    who, _ = setup_job(client)
    other = post(client, '/executors', {'name': '其他电脑'}).json()['data']
    assert agent(client, '/claim', other).json()['data'] is None
    job = agent(client, '/claim', who).json()['data']
    path = '/jobs/' + job['id']
    assert agent(client, '/claim', who).json()['data'] is None
    assert agent(client, path + '/check', other, {'lease': job['lease']}).status_code == 401
    assert agent(client, path + '/check', who, {'lease': 'x' * 43}).status_code == 401
    assert client.get(BASE, headers={'Authorization': 'Bearer ' + who['token']}).status_code == 401
    assert agent(client, path + '/report', who, {'lease': job['lease'], 'result': 'failed'}).status_code == 422
    report = {'lease': job['lease'], 'result': 'installed'}
    assert agent(client, path + '/report', who, report).status_code == 200
    assert agent(client, path + '/report', who, report).status_code == 200
    assert agent(client, path + '/report', who, report | {'result': 'already_installed'}).status_code == 409
    public = client.get(BASE, headers=admin()).text + client.get('/api/v6/admin/audit', headers=admin()).text
    assert who['token'] not in public and job['lease'] not in public and 'secret_hash' not in public and 'lease_hash' not in public
    assert post(client, '/executors/' + who['id'] + '/revoke').status_code == 200
    assert agent(client, path + '/report', who, report).status_code == 401


def test_expired_lease_never_reassigns_and_late_result_rejected(client):
    who, _ = setup_job(client, [{'ip': '10.0.1.2', 'serial': 'ONE'}, {'ip': '10.0.1.3', 'serial': 'TWO'}])
    job = agent(client, '/claim', who).json()['data']
    with database() as db:
        db.execute('UPDATE install_jobs SET lease_until=0 WHERE id=?', (job['id'],))
    assert agent(client, '/claim', who).json()['data'] is None
    value = next(v for v in overview(client)['jobs'] if v['id'] == job['id'])
    assert value['state'] == 'uncertain'
    assert agent(client, '/jobs/' + job['id'] + '/report', who,
                 {'lease': job['lease'], 'result': 'installed'}).status_code == 409
    path = '/jobs/' + job['id'] + '/retry'
    assert post(client, path, {'revision': value['revision']}).status_code == 422
    assert post(client, path, {'revision': value['revision'], 'previous_executor_stopped': True}).status_code == 200
    reclaimed = agent(client, '/claim', who).json()['data']
    assert reclaimed['id'] == job['id'] and reclaimed['lease'] != job['lease']
    assert agent(client, '/jobs/' + job['id'] + '/check', who, {'lease': job['lease']}).status_code == 401


def test_revoke_running_requires_expiry_and_manual_resolution(client):
    who, _ = setup_job(client)
    job = agent(client, '/claim', who).json()['data']
    value = overview(client)['jobs'][0]
    assert post(client, '/jobs/' + job['id'] + '/cancel', {'revision': value['revision']}).status_code == 409
    post(client, '/executors/' + who['id'] + '/revoke')
    value = overview(client)['jobs'][0]
    action = {'revision': value['revision'], 'previous_executor_stopped': True}
    assert post(client, '/jobs/' + job['id'] + '/resolve', action).status_code == 409
    with database() as db:
        db.execute('UPDATE install_jobs SET lease_until=0 WHERE id=?', (job['id'],))
    assert post(client, '/jobs/' + job['id'] + '/resolve', action).status_code == 200
    assert overview(client)['jobs'][0]['state'] == 'cancelled'


def test_permissions_csrf_and_expired_executor(client):
    assert client.get(BASE).status_code == 401
    who, _ = setup_job(client)
    with database() as db:
        db.execute('UPDATE install_executors SET expires=0 WHERE id=?', (who['id'],))
    assert agent(client, '/claim', who).status_code == 401
    me = session(client, 'viewer').json()['data']
    assert client.get(BASE).status_code == 200
    assert post(client, '/executors', {'name': '禁止'}, {'X-RB-CSRF': me['csrf']}).status_code == 403
    with database() as db:
        db.execute("UPDATE users SET role='admin'")
    assert post(client, '/executors', {'name': '禁止'}, {}).status_code == 403
    assert post(client, '/executors', {'name': '禁止'}, {'X-RB-CSRF': me['csrf'], 'Origin': 'https://evil.test'}).status_code == 403


def test_association_and_acceptance_are_separate_and_staleness_visible(client):
    _, job = installed(client)
    token, device = enroll(client)
    value = overview(client)['jobs'][0]
    association = {'revision': value['revision'], 'code': device['code'], 'physical_identity_confirmed': True}
    path = '/jobs/' + job['id']
    assert post(client, path + '/associate', association).status_code == 409
    metadata = {'serial': 'WRONG', 'model': 'BX68', 'apk': '0.7.0'}
    web_cookie(client, token, metadata=metadata)
    assert post(client, path + '/associate', association).status_code == 409
    # Android may withhold serial from an ordinary app; explicit physical short-code confirmation is required.
    web_cookie(client, token, metadata=metadata | {'serial': ''})
    assert post(client, path + '/associate', association).status_code == 200
    value = overview(client)['jobs'][0]
    assert value['state'] == 'associated' and not value['acceptance_current']
    acceptance = {'revision': value['revision'], 'device_revision': 2, 'screen_and_fresh_data': True,
                  'lighting': True, 'cold_boot': True, 'adb_closed': True, 'poe_recovery_adb_stays_closed': True,
                  'location': '测试位置', 'switch_port': '测试交换机 / 端口 1'}
    assert post(client, path + '/accept', acceptance).status_code == 409
    assert configure(client, device['id'], config={'room_light': False}).status_code == 200
    assert post(client, path + '/accept', acceptance).status_code == 409
    web_cookie(client, token, reported_revision=2, metadata=metadata | {'serial': ''})
    assert post(client, path + '/accept', acceptance | {'adb_closed': False}).status_code == 422
    assert post(client, path + '/accept', acceptance).status_code == 200
    value = overview(client)['jobs'][0]
    assert value['acceptance_current'] and value['acceptance']['source'] == 'manual'
    with database() as db:
        db.execute('UPDATE devices SET last_seen=?', (int(time.time()) - 120,))
    value = overview(client)['jobs'][0]
    assert not value['device_ready']  # Historical acceptance never implies current health.
    with database() as db:
        db.execute('UPDATE devices SET revision=revision+1')
    assert not overview(client)['jobs'][0]['acceptance_current']
    with database() as db:
        saved = json.loads(db.execute('SELECT acceptance FROM install_jobs').fetchone()[0])
        assert saved['device_revision'] == 2


@pytest.mark.parametrize('state', ['queued', 'failed', 'cancelled', 'uncertain'])
def test_cannot_associate_before_success(client, state):
    setup_job(client)
    _, device = enroll(client)
    value = overview(client)['jobs'][0]
    with database() as db:
        db.execute('UPDATE install_jobs SET state=?', (state,))
    assert post(client, '/jobs/' + value['id'] + '/associate', {'revision': 1, 'code': device['code'],
                'physical_identity_confirmed': True}).status_code == 409


def test_concurrent_claim_and_cancelled_queue(client):
    who, _ = setup_job(client)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: agent(client, '/claim', who).json()['data'], range(2)))
    assert len([r for r in results if r]) == 1
    job = next(r for r in results if r)
    assert overview(client)['jobs'][0]['revision'] == 2
    # A lost response cannot issue a second lease even when another process starts.
    assert agent(client, '/claim', who).json()['data'] is None
    assert agent(client, '/jobs/' + job['id'] + '/check', who, {'lease': job['lease']}).status_code == 200


def test_cancel_prevents_claim_and_failure_does_not_block_next_device(client):
    who, _ = setup_job(client, [{'ip': '10.0.1.2', 'serial': 'ONE'}, {'ip': '10.0.1.3', 'serial': 'TWO'},
                              {'ip': '10.0.1.4', 'serial': 'THREE'}])
    queued = overview(client)['jobs'][0]
    assert post(client, '/jobs/' + queued['id'] + '/cancel', {'revision': 1}).status_code == 200
    job = agent(client, '/claim', who).json()['data']
    assert job['id'] != queued['id']
    assert agent(client, '/jobs/' + job['id'] + '/report', who,
                 {'lease': job['lease'], 'result': 'failed', 'error': 'connection_failed'}).status_code == 200
    assert agent(client, '/claim', who).json()['data']['id'] not in (job['id'], queued['id'])
