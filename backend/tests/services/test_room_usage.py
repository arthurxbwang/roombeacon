"""V5 boundary tests use a disposable Redis process, never the configured service."""
import asyncio
import os
import shutil
import subprocess
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
import redis.asyncio as redis

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.room_devices import issue_device
from app.core.room_usage_auth import KEY, issue_usage, revoke_usage
from app.room_display_main import app
from app.schemas.meeting_room import Room, RoomEvent, RoomSchedule
from app.schemas.room_usage import TerminalCommand, UsagePolicy, VerifiedOccurrence
from app.services import room_usage as service
from app.services import room_usage_worker as worker
from app.services.room_usage_store import PREFIX, UsageStore


def health(actor, policy, snapshot, now):
    return {'protocol': 2, 'actor': actor, 'time': now.timestamp(), 'session_id': 'a' * 32,
            'occurrence_id': worker.Occurrence.model_validate(snapshot.events[0].model_dump()).identity('omm_one'),
            'policy_revision': policy['revision'], 'operation_state': 'ready'}


@pytest.fixture(scope='module')
def redis_socket():
    binary = os.getenv('ROOMBEACON_TEST_REDIS_SERVER') or shutil.which('redis-server')
    if not binary:
        pytest.skip('V5 原子状态测试需要本地 redis-server；不连接已有 Redis')
    with tempfile.TemporaryDirectory(prefix='rb-v5-') as directory:
        socket = str(Path(directory) / 'r.sock')
        process = subprocess.Popen([binary, '--port', '0', '--unixsocket', socket,
                                    '--save', '', '--appendonly', 'no', '--dir', directory],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(100):
                if Path(socket).exists():
                    break
                if process.poll() is not None:
                    pytest.fail('isolated Redis failed to start')
                time.sleep(.02)
            else:
                pytest.fail('isolated Redis startup timeout')
            yield socket
        finally:
            process.terminate()
            process.wait(timeout=5)


@pytest_asyncio.fixture
async def setup_usage(redis_socket, monkeypatch):
    monkeypatch.setattr(settings, 'REDIS_URL', 'unix://' + redis_socket)
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_ENABLED', True)
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_WRITES_ENABLED', False)
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_RELEASE_ROOM_IDS', {'omm_one'})
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_CONTROL_TOKEN', 'admin-' + 'a' * 40)
    cache = redis.Redis(unix_socket_path=redis_socket, decode_responses=True)
    await cache.flushdb()  # Disposable process owned by this fixture, never a runtime Redis.
    now = datetime.now(UTC)
    event = RoomEvent(uid='fixture', start_time=now - timedelta(minutes=2), end_time=now + timedelta(minutes=30))
    snapshot = RoomSchedule(room=Room(room_id='omm_one', name='fixture'), events=[event],
                            synced_at=now, valid_until=now + timedelta(minutes=10))
    monkeypatch.setattr(service, 'cached_schedule', AsyncMock(return_value=snapshot))
    monkeypatch.setattr('app.room_usage_routes.cached_schedule', AsyncMock(return_value=snapshot))
    store = UsageStore(cache)
    policy = await service.save_policy(store, 'omm_one', UsagePolicy(owner='v5', mode='observe'))
    token = await issue_usage('omm_one')
    actor = await cache.get(KEY + 'omm_one')
    epoch = 'epoch1'
    await cache.set(worker.LEASE, epoch, ex=60)
    await store.put('epoch-start:' + epoch, (now - timedelta(minutes=10)).timestamp())
    before = now - timedelta(minutes=3)
    snapshot.synced_at = before
    await store.put('heartbeat:omm_one', health(actor, policy, snapshot, before))
    client = AsyncMock()
    await worker.tick_room(store, client, 'omm_one', epoch, before)
    await store.put('heartbeat:omm_one', health(actor, policy, snapshot, now))
    state = await service.view(store, 'omm_one', now)
    key = 'record:' + state['record']['id']
    record = await store.get(key)
    await store.put(key, {**record, 'last_seen': now.timestamp()})
    client.freebusy.return_value = {'free_busy': {'omm_one': [event.model_dump(mode='json')]}, 'error_room_ids': []}
    try:
        yield store, client, token, actor, policy, now, snapshot, epoch
    finally:
        await cache.aclose()


async def request_for(store, now):
    state = await service.view(store, 'omm_one', now)
    return TerminalCommand(occurrence_id=state['record']['id'], policy_revision=state['policy']['revision'], session_id='a' * 32)


@pytest.mark.asyncio
async def test_confirm_idempotent_and_survives_reload(setup_usage):
    store, client, _, actor, _, now, _, _ = setup_usage
    request = await request_for(store, now)
    first = await service.command(store, 'omm_one', actor, request, 'confirm', now)
    second = await service.command(store, 'omm_one', actor, request, 'confirm', now)
    assert first['record']['state'] == second['record']['state'] == 'confirmed'
    assert (await service.view(UsageStore(store.cache), 'omm_one', now))['record']['state'] == 'confirmed'
    assert 'actor' not in first['record']
    client.release.assert_not_called()


@pytest.mark.asyncio
async def test_auth_separation_revocation_and_disabled_legacy(setup_usage, monkeypatch):
    store, _, token, _, _, _, snapshot, _ = setup_usage
    read = await issue_device('omm_one')
    monkeypatch.setattr('app.room_display_main.schedule_for', AsyncMock(return_value=snapshot))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as http:
        headers = {'Authorization': 'Bearer ' + token}
        request = (await request_for(store, datetime.now(UTC))).model_dump()
        for wrong in ['', read, settings.ROOM_DISPLAY_CONTROL_TOKEN]:
            response = await http.post('/api/meeting-rooms/usage/confirm', json=request,
                                       headers={'Authorization': 'Bearer ' + wrong})
            assert response.status_code == 401
        assert (await http.get('/api/meeting-rooms/display', headers=headers)).status_code == 401
        assert (await http.get('/api/room-control/usage/omm_one', headers=headers)).status_code == 401
        assert (await http.get('/api/meeting-rooms/usage', headers=headers)).status_code == 200
        await revoke_usage('omm_one')
        assert (await http.get('/api/meeting-rooms/usage', headers=headers)).status_code == 401
        monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_ENABLED', False)
        read_headers = {'Authorization': 'Bearer ' + read}
        assert (await http.get('/api/meeting-rooms/display', headers=read_headers)).status_code == 200
        assert (await http.post('/api/meeting-rooms/display', headers=read_headers)).status_code == 405


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['stale', 'disabled', 'rescheduled', 'cross_room', 'expired', 'policy'])
async def test_invalid_confirmation(setup_usage, change):
    store, _, _, actor, _, now, snapshot, _ = setup_usage
    request = await request_for(store, now)
    if change == 'stale': snapshot.valid_until = now
    if change == 'disabled': snapshot.room.enabled = False
    if change == 'rescheduled': snapshot.events[0].end_time += timedelta(minutes=10)
    if change == 'cross_room': request.occurrence_id = '0' * 64
    if change == 'expired': now += timedelta(minutes=9)
    if change == 'policy': await service.save_policy(store, 'omm_one', UsagePolicy(owner='v5', mode='observe'))
    with pytest.raises(AppError):
        await service.command(store, 'omm_one', actor, request, 'confirm', now)


@pytest.mark.asyncio
async def test_confirm_and_release_claim_have_single_winner(setup_usage):
    store, _, _, actor, policy, now, _, _ = setup_usage
    request = await request_for(store, now)
    key = 'record:' + request.occurrence_id
    old = await store.get(key)
    results = await asyncio.gather(
        service.command(store, 'omm_one', actor, request, 'confirm', now),
        store.cas(key, old, {**old, 'state': 'releasing'}, 'omm_one', policy=policy), return_exceptions=True)
    record = await store.get(key)
    assert record['state'] in {'confirmed', 'releasing'}
    assert (record['state'] == 'releasing') == (results[1] is True)


async def make_due(setup_usage, monkeypatch, mode='auto'):
    store, client, _, _, policy, now, snapshot, epoch = setup_usage
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_WRITES_ENABLED', True)
    policy.update(mode=mode, grace_minutes=1, native_policy_cleared=True, release_verified=True)
    await store.put('policy:omm_one', policy)
    await store.put('paused', False)
    request = await request_for(store, now)
    key = 'record:' + request.occurrence_id
    old = await store.get(key)
    old.update(verified=True, deadline=(now - timedelta(seconds=1)).isoformat())
    if mode == 'auto':
        old.update(state='checking', challenge_id='b' * 32, challenge_started=now.timestamp() - 1,
                   challenge_expires=now.timestamp() + 15, ack_at=now.timestamp(), release_kind='no_show')
    await store.put(key, old)
    return store, client, key, old, policy, now, snapshot, epoch


@pytest.mark.asyncio
async def test_observation_never_writes_even_with_write_switch(setup_usage, monkeypatch):
    store, client, key, _, _, now, _, epoch = await make_due(setup_usage, monkeypatch, 'observe')
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    assert (await store.get(key))['state'] == 'observed'
    client.release.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('condition', ['paused', 'not_verified', 'no_write', 'offline', 'revoked', 'restart', 'gap', 'policy'])
async def test_release_safety_gates(setup_usage, monkeypatch, condition):
    store, client, key, old, _, now, _, epoch = await make_due(setup_usage, monkeypatch)
    if condition == 'paused': await store.put('paused', True)
    if condition == 'not_verified': old['verified'] = False; await store.put(key, old)
    if condition == 'no_write': monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_WRITES_ENABLED', False)
    if condition == 'offline': await store.cache.delete(PREFIX + 'heartbeat:omm_one')
    if condition == 'revoked': await revoke_usage('omm_one')
    if condition == 'restart': epoch = 'new-process'
    if condition == 'gap': old['last_seen'] -= 50; await store.put(key, old)
    if condition == 'policy': await service.save_policy(store, 'omm_one', UsagePolicy(owner='v5', mode='observe'))
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    assert (await store.get(key))['state'] == 'blocked'
    client.release.assert_not_called()


@pytest.mark.asyncio
async def test_release_success_is_verified_and_single_attempt(setup_usage, monkeypatch):
    store, client, key, _, _, now, snapshot, epoch = await make_due(setup_usage, monkeypatch)
    client.freebusy.side_effect = [client.freebusy.return_value, {'free_busy': {'omm_one': []}}]
    await store.cache.set('rooms:snapshot:omm_one', snapshot.model_dump_json(), ex=60)
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    assert (await store.get(key))['state'] == 'released'
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    client.release.assert_awaited_once()
    assert client.release.call_args.args[2] == 'NOT_CHECK_IN'
    saved = RoomSchedule.model_validate_json(await store.cache.get('rooms:snapshot:omm_one'))
    assert saved.valid_until <= datetime.now(UTC)


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['timeout', 'rejected', 'still_busy', 'changed', 'missing', 'lease_lost'])
async def test_ambiguous_release_is_not_retried(setup_usage, monkeypatch, failure):
    from app.connectors.feishu.room_release import ReleaseRejected
    store, client, key, _, _, now, _, epoch = await make_due(setup_usage, monkeypatch)
    if failure == 'timeout': client.release.side_effect = httpx.ReadTimeout('fixture')
    if failure == 'rejected': client.release.side_effect = ReleaseRejected(105003)
    if failure == 'changed': client.freebusy.return_value = {'free_busy': {'omm_one': []}}
    if failure == 'missing': client.freebusy.return_value = {'free_busy': {}}
    if failure == 'lease_lost': await store.cache.delete(worker.LEASE)
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    expected = 'failed' if failure == 'rejected' else 'blocked' if failure in {'changed', 'missing', 'lease_lost'} else 'uncertain'
    assert (await store.get(key))['state'] == expected
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    assert client.release.await_count <= 1


@pytest.mark.asyncio
async def test_missing_records_do_not_become_unconfirmed(setup_usage):
    store, client, _, _, _, now, _, epoch = setup_usage
    request = await request_for(store, now)
    await store.cache.delete(PREFIX + 'record:' + request.occurrence_id)
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    assert (await service.view(store, 'omm_one', now))['record']['state'] == 'blocked'
    client.release.assert_not_called()


@pytest.mark.asyncio
async def test_lost_confirmation_before_start_is_not_reenrolled(setup_usage):
    store, client, _, _, policy, now, snapshot, epoch = setup_usage
    request = await request_for(store, now)
    before = snapshot.events[0].start_time - timedelta(seconds=20)
    await store.cache.delete(PREFIX + 'record:' + request.occurrence_id)
    actor = await store.cache.get(KEY + 'omm_one')
    await store.put('heartbeat:omm_one', health(actor, policy, snapshot, before))
    await worker.tick_room(store, client, 'omm_one', epoch, before)
    assert (await store.get('record:' + request.occurrence_id))['state'] == 'blocked'


@pytest.mark.asyncio
async def test_restart_during_window_does_not_enroll_missing_records(setup_usage):
    store, client, _, _, policy, _now, snapshot, _ = setup_usage
    before = snapshot.events[0].start_time - timedelta(seconds=20)
    occurrence = worker.Occurrence.model_validate(snapshot.events[0].model_dump())
    key = 'record:' + occurrence.identity('omm_one')
    await store.cache.delete(PREFIX + key, PREFIX + 'seen:' + occurrence.identity('omm_one'))
    await store.put('epoch-start:new', before.timestamp())
    actor = await store.cache.get(KEY + 'omm_one')
    await store.put('heartbeat:omm_one', health(actor, policy, snapshot, before))
    await worker.tick_room(store, client, 'omm_one', 'new', before)
    assert (await store.get(key))['state'] == 'blocked'


@pytest.mark.asyncio
async def test_early_end_requires_occurrence_verification_and_stays_queued(setup_usage, monkeypatch):
    store, client, _, actor, policy, now, _, epoch = setup_usage
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_WRITES_ENABLED', True)
    policy.update(mode='auto', native_policy_cleared=True, release_verified=True)
    await store.put('policy:omm_one', policy)
    await store.put('paused', False)
    request = await request_for(store, now)
    with pytest.raises(AppError):
        await service.command(store, 'omm_one', actor, request, 'end', now)
    await service.verify_occurrence(store, 'omm_one', VerifiedOccurrence(**request.model_dump(), non_recurring_verified=True))
    await service.command(store, 'omm_one', actor, request, 'confirm', now)
    result = await service.command(store, 'omm_one', actor, request, 'end', now)
    assert result['record']['state'] == 'end_requested'
    client.release.assert_not_called()
    client.freebusy.side_effect = [client.freebusy.return_value, {'free_busy': {'omm_one': []}}]
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    record = await store.get('record:' + request.occurrence_id)
    assert record['state'] == 'checking'
    await store.put('record:' + request.occurrence_id, {**record, 'ack_at': now.timestamp()})
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    assert client.release.call_args.args[2] == 'ENDED_BEFORE_DUE'


@pytest.mark.asyncio
async def test_admin_policy_pause_and_audit(setup_usage):
    store, _, token, _, _, now, _, _ = setup_usage
    headers = {'Authorization': 'Bearer ' + settings.ROOM_DISPLAY_CONTROL_TOKEN}
    paths = ['/api/room-control/usage/omm_one/policy', '/api/room-control/usage-pause']
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as http:
        for path in paths:
            data = {'paused': True} if path.endswith('pause') else {'mode': 'observe'}
            assert (await http.put(path, json=data)).status_code == 401
            assert (await http.put(path, json=data, headers={'Authorization': 'Bearer ' + token})).status_code == 401
        response = await http.put(paths[0], headers=headers, json={'mode': 'auto'})
        assert response.status_code == 409
        response = await http.put(paths[1], headers=headers, json={'paused': False})
        assert response.status_code == 200
        assert await store.get('paused') is False
        response = await http.get('/api/room-control/usage/omm_one', headers=headers)
        assert response.status_code == 200
        assert response.json()['data']['global_audit'][0]['paused'] is False
        request = await request_for(store, now)
        response = await http.post('/api/room-control/usage/omm_one/verify', headers=headers,
                                   json={**request.model_dump(), 'non_recurring_verified': False})
        assert response.status_code == 422
        assert (await service.view(store, 'omm_one', now))['record']['verified'] is False


@pytest.mark.asyncio
async def test_cancelled_write_becomes_uncertain_without_retry(setup_usage, monkeypatch):
    store, client, key, _, _, now, _, epoch = await make_due(setup_usage, monkeypatch)
    client.release.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await worker.tick_room(store, client, 'omm_one', epoch, now)
    assert (await store.get(key))['state'] == 'releasing'
    await worker.tick_room(store, client, 'omm_one', epoch, now + timedelta(seconds=31))
    assert (await store.get(key))['state'] == 'uncertain'
    client.release.assert_awaited_once()


@pytest.mark.asyncio
async def test_read_queries_cannot_mask_failed_confirmation(setup_usage):
    store, _, token, _, _, _, _, _ = setup_usage
    await store.cache.delete(PREFIX + 'heartbeat:omm_one')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as http:
        response = await http.get('/api/meeting-rooms/usage', headers={'Authorization': 'Bearer ' + token})
    assert response.status_code == 200
    assert await store.get('heartbeat:omm_one') is None
