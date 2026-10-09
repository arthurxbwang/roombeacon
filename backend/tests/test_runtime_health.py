"""Native runtime evidence stays independent from management and business heartbeats."""
import json
import time

import pytest

from app.management.installation_store import ready
from app.management.store import database
from tests.test_installation import installed, overview, post
from tests.test_v6_management import admin, configure, enroll, web_cookie
from tests.test_v6_management import client as management_client

client = management_client
RUNTIME = {'protocol': 1, 'page_state': 'ready', 'page_error': '', 'page_age_seconds': 2,
           'page_release': 'git-1234abcd', 'terminal_state': 'free', 'webview': '106.0.5249.126',
           'light_state': 'ok'}


def runtime_sync(client, token, runtime=RUNTIME, **changes):
    return web_cookie(client, token, metadata={'runtime': runtime}, **changes)


def view(client, identity):
    response = client.get('/api/v6/admin/devices', headers=admin())
    assert response.status_code == 200
    return next(row for row in response.json()['data'] if row['id'] == identity)


def row(identity):
    with database() as db:
        return dict(db.execute('SELECT * FROM devices WHERE id=?', (identity,)).fetchone())


def test_legacy_metadata_stays_compatible_without_inventing_page_evidence(client):
    token, item = enroll(client)
    assert configure(client, item['id']).status_code == 200
    web_cookie(client, token, reported_revision=2)
    value = view(client, item['id'])
    assert value['online'] and value['reported_revision'] == 2
    assert value['page_health'] == {'state': 'unknown', 'error': '', 'age_seconds': None,
                                   'page_release': '', 'terminal_state': 'unknown',
                                   'webview': '', 'light_state': 'unknown'}
    assert ready(row(item['id']))  # Historical APK delivery rules remain compatible.


def test_page_failure_recovery_preserves_applied_revision_and_device_isolation(client):
    token, item = enroll(client)
    other_token, other = enroll(client)
    assert configure(client, item['id']).status_code == 200
    runtime_sync(client, token, reported_revision=2)
    runtime_sync(client, other_token, RUNTIME | {'page_release': 'other', 'terminal_state': 'busy'})
    assert view(client, item['id'])['page_health']['state'] == 'ready'
    assert ready(row(item['id']))
    runtime_sync(client, token, RUNTIME | {'page_state': 'failed', 'page_error': 'renderer',
                                         'terminal_state': 'unknown'}, reported_revision=2)
    failed = view(client, item['id'])
    assert failed['online'] and failed['reported_revision'] == failed['revision'] == 2
    assert failed['page_health']['state'] == 'failed' and failed['page_health']['error'] == 'renderer'
    assert not ready(row(item['id']))
    assert view(client, other['id'])['page_health']['page_release'] == 'other'
    runtime_sync(client, token, reported_revision=2)
    recovered = view(client, item['id'])
    assert recovered['page_health']['state'] == 'ready' and recovered['page_health']['error'] == ''
    assert ready(row(item['id']))


@pytest.mark.parametrize(('age', 'elapsed', 'expected', 'online'), [
    (2, 10, 'ready', True), (44, 1, 'stale', True), (45, 0, 'stale', True),
    (0, 60, 'offline', False), (0, -10, 'offline', False), (None, 0, 'unknown', True),
])
def test_js_probe_age_includes_server_elapsed_and_future_heartbeat_is_not_fresh(
        client, age, elapsed, expected, online):
    token, item = enroll(client)
    assert configure(client, item['id']).status_code == 200
    runtime_sync(client, token, RUNTIME | {'page_age_seconds': age}, reported_revision=2)
    with database() as db:
        db.execute('UPDATE devices SET last_seen=? WHERE id=?', (int(time.time()) - elapsed, item['id']))
    value = view(client, item['id'])
    assert value['page_health']['state'] == expected
    assert value['online'] is online
    actual_age = value['page_health']['age_seconds']
    if age is None or elapsed < 0:
        assert actual_age is None
    else:
        assert age + elapsed <= actual_age <= age + elapsed + 1
    assert ready(row(item['id'])) is (expected == 'ready')


@pytest.mark.parametrize('state', ['waiting', 'loading', 'failed', 'paused'])
def test_explicit_nonready_native_states_do_not_become_ready_from_sync(client, state):
    token, item = enroll(client)
    assert configure(client, item['id']).status_code == 200
    runtime_sync(client, token, RUNTIME | {'page_state': state, 'page_age_seconds': None,
                                         'page_error': 'timeout' if state == 'failed' else ''}, reported_revision=2)
    assert view(client, item['id'])['page_health']['state'] == state
    assert not ready(row(item['id']))


def test_unknown_terminal_data_cannot_pass_delivery_and_sync_does_not_refresh_probe(client):
    token, item = enroll(client)
    assert configure(client, item['id']).status_code == 200
    stale = RUNTIME | {'page_age_seconds': 86400}
    runtime_sync(client, token, stale, reported_revision=2)
    runtime_sync(client, token, stale, reported_revision=2)
    assert view(client, item['id'])['online']
    assert view(client, item['id'])['page_health']['state'] == 'stale'
    assert not ready(row(item['id']))
    runtime_sync(client, token, RUNTIME | {'terminal_state': 'unknown'}, reported_revision=2)
    assert not ready(row(item['id']))


def test_new_health_evidence_requires_device_auth_and_cannot_mutate_another_device(client):
    token, item = enroll(client)
    payload = {'metadata': {'runtime': RUNTIME}}
    assert client.post('/api/v6/device/sync', json=payload).status_code == 401
    assert client.post('/api/v6/device/sync', json=payload, headers=admin()).status_code == 401
    bad = token.rsplit(':', 1)[0] + ':' + 'b' * 43
    assert client.post('/api/v6/device/sync', json=payload,
                       headers={'Authorization': 'Bearer ' + bad}).status_code == 401
    assert view(client, item['id'])['page_health']['state'] == 'unknown'


@pytest.mark.parametrize(('field', 'bad'), [
    ('protocol', 2), ('page_state', 'healthy'), ('page_error', 'private-secret'),
    ('terminal_state', 'signed_in'), ('light_state', 'green'),
    ('page_age_seconds', -1), ('page_age_seconds', 86401), ('page_age_seconds', 1.5),
    ('page_age_seconds', True), ('page_age_seconds', '1'),
    ('page_release', 'x' * 101), ('page_release', 'https://secret.test'),
    ('page_release', 'abc def'), ('page_release', 'abc\n'),
    ('webview', 'x' * 101), ('webview', 'Chromium/106 secret'), ('unknown', 'value'),
])
def test_runtime_wire_protocol_rejects_unbounded_or_uncontrolled_values(client, field, bad):
    token, item = enroll(client)
    result = client.post('/api/v6/device/sync', headers={'Authorization': 'Bearer ' + token},
                         json={'metadata': {'runtime': RUNTIME | {field: bad}}})
    assert result.status_code == 422
    assert json.loads(row(item['id'])['metadata']).get('runtime') is None


@pytest.mark.parametrize('age', [0, 86400, None])
def test_probe_age_boundaries_are_accepted(client, age):
    token, item = enroll(client)
    runtime_sync(client, token, RUNTIME | {'page_age_seconds': age})
    assert view(client, item['id'])['metadata']['runtime']['page_age_seconds'] == age


def test_new_apk_delivery_acceptance_requires_live_page_evidence(client):
    _, job = installed(client)
    token, device = enroll(client)
    metadata = {'model': 'BX68', 'apk': '0.7.0', 'runtime': RUNTIME | {'page_state': 'loading'}}
    web_cookie(client, token, metadata=metadata)
    assert configure(client, device['id'], config={'room_light': False}).status_code == 200
    web_cookie(client, token, metadata=metadata, reported_revision=2)
    path = '/jobs/' + job['id']
    association = {'revision': overview(client)['jobs'][0]['revision'], 'code': device['code'],
                   'physical_identity_confirmed': True}
    with database() as db:
        db.execute('UPDATE devices SET last_seen=? WHERE id=?', (int(time.time()) + 60, device['id']))
    assert post(client, path + '/associate', association).status_code == 409
    web_cookie(client, token, metadata=metadata, reported_revision=2)
    assert post(client, path + '/associate', association).status_code == 200
    acceptance = {'revision': overview(client)['jobs'][0]['revision'], 'device_revision': 2,
                  'screen_and_fresh_data': True, 'lighting': True, 'cold_boot': True, 'adb_closed': True,
                  'poe_recovery_adb_stays_closed': True, 'location': '测试位置', 'switch_port': '测试端口'}
    assert post(client, path + '/accept', acceptance).status_code == 409
    assert not overview(client)['jobs'][0]['device_ready']
    web_cookie(client, token, metadata=metadata | {'runtime': RUNTIME}, reported_revision=2)
    assert overview(client)['jobs'][0]['device_ready']
    assert post(client, path + '/accept', acceptance).status_code == 200
    web_cookie(client, token, metadata=metadata | {'runtime': RUNTIME | {'page_age_seconds': 45}},
               reported_revision=2)
    assert not overview(client)['jobs'][0]['device_ready']
    assert post(client, path + '/accept', acceptance | {'revision': acceptance['revision'] + 1}).status_code == 409
