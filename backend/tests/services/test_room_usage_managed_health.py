"""Managed device heartbeats retain revocation and controller boundaries."""
import json
from unittest.mock import AsyncMock

import pytest

from app.management.configuration_delivery import reconcile_room
from app.management.security import authenticate_web, current_usage_actor
from app.management.store import database
from app.services.room_usage_health import healthy_terminal
from tests import test_v6_management as v6
from tests.services import test_room_usage as support

redis_socket = support.redis_socket
setup_usage = support.setup_usage
client = v6.client


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', [None, 'revoked', 'revision', 'room', 'display_only', 'other_controller', 'error', 'unacknowledged'])
async def test_managed_heartbeat_matches_current_binding(setup_usage, client, monkeypatch, fault):
    store, _, _, _, policy, now, _, _ = setup_usage
    monkeypatch.setattr(v6.devices, 'cached_directory', AsyncMock(return_value=[{'room_id': 'omm_one'}]))
    token, device = v6.enroll(client)
    assert v6.configure(client, device['id'], room_id='omm_one').status_code == 200
    session = v6.web_cookie(client, token, reported_revision=2)['web_session']
    user = authenticate_web(session)
    state = await support.service.view(store, 'omm_one', now)
    record = await store.get('record:' + state['record']['id'])
    hb = await store.get('heartbeat:omm_one')
    await store.put('heartbeat:omm_one', hb | {'actor': user['digest']})
    if fault:
        with database() as db:
            if fault == 'revoked':
                db.execute("UPDATE devices SET status='revoked' WHERE id=?", (device['id'],))
            elif fault == 'revision':
                db.execute('UPDATE devices SET revision=revision+1 WHERE id=?', (device['id'],))
            elif fault == 'room':
                db.execute("UPDATE devices SET room_id='omm_other' WHERE id=?", (device['id'],))
            elif fault == 'display_only':
                db.execute('UPDATE devices SET config=? WHERE id=?',
                           (json.dumps({'usage_control': False}), device['id']))
            elif fault == 'error':
                db.execute("UPDATE devices SET error='light failed' WHERE id=?", (device['id'],))
            elif fault == 'unacknowledged':
                db.execute('UPDATE devices SET reported_revision=0 WHERE id=?', (device['id'],))
            else:
                db.execute('INSERT INTO room_configurations VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                           ('omm_one', 'fixture', 1, 1, 'other', '{}', 'applied', '', 'fixture', '', ''))
    assert current_usage_actor('omm_one', user['digest']) is (fault is None)
    assert await healthy_terminal(store, 'omm_one', now, record, policy) is (fault is None)


@pytest.mark.asyncio
async def test_existing_policy_migration_preserves_bookings(setup_usage, client, monkeypatch):
    store, _, _, _, policy, now, _, _ = setup_usage
    monkeypatch.setattr(v6.devices, 'cached_directory', AsyncMock(return_value=[{'room_id': 'omm_one'}]))
    token, device = v6.enroll(client)
    assert v6.configure(client, device['id'], room_id='omm_one').status_code == 200
    v6.web_cookie(client, token, reported_revision=2)
    desired = {k: policy[k] for k in ('owner', 'mode', 'early_minutes', 'grace_minutes', 'release_delay_seconds')}
    with database() as db:
        db.execute('INSERT INTO room_configurations VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                   ('omm_one', 'fixture', 1, 1, device['id'], json.dumps(desired),
                    'applied', '', 'fixture', '', policy['revision']))
    key = 'rooms:usage:v1:policy:omm_one'
    await store.cache.expire(key, 30)
    state = await support.service.view(store, 'omm_one', now)
    record_key = 'record:' + state['record']['id']
    record = await store.get(record_key)
    await reconcile_room(store, 'omm_one')
    assert await store.cache.ttl(key) == -1
    assert await store.get('policy:omm_one') == policy
    assert await store.get(record_key) == record
