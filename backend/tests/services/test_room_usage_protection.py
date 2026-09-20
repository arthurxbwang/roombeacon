"""Protected V5 lifecycle, protocol boundaries and room ownership."""
from datetime import datetime, timedelta

import httpx
import pytest

from app.core.config import settings
from app.core.exceptions import AppError
from app.room_display_main import app, decorate
from app.schemas.room_usage import UsageHeartbeat, UsagePolicy
from app.services import room_usage as service
from app.services import room_usage_worker as worker
from app.services.room_usage_health import heartbeat
from tests.services import test_room_usage as support
from tests.services.test_room_usage import health, make_due, request_for

redis_socket = support.redis_socket
setup_usage = support.setup_usage


def report(policy, record, status='ready', **extra):
    return UsageHeartbeat(protocol=2, session_id='a' * 32, occurrence_id=record['id'],
                          policy_revision=policy['revision'], operation_state=status, **extra)


@pytest.mark.asyncio
async def test_waiting_allows_confirmation_without_release(setup_usage, monkeypatch):
    store, client, key, old, _policy, now, _, epoch = await make_due(setup_usage, monkeypatch)
    await store.put(key, {**old, 'state': 'pending'})
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    record = await store.get(key)
    assert record['state'] == 'waiting'
    assert datetime.fromisoformat(record['release_at']) == now + timedelta(seconds=60)
    request = await request_for(store, now)
    state = await service.command(store, 'omm_one', setup_usage[3], request, 'confirm', now)
    assert state['record']['state'] == 'confirmed'
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    client.release.assert_not_called()


@pytest.mark.asyncio
async def test_complete_challenge_before_release(setup_usage, monkeypatch):
    store, client, key, old, policy, now, _, epoch = await make_due(setup_usage, monkeypatch)
    old.update(state='waiting', release_at=(now - timedelta(seconds=1)).isoformat())
    await store.put(key, old)
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    record = await store.get(key)
    assert record['state'] == 'checking' and record['ack_at'] is None
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    client.release.assert_not_called()
    await heartbeat(store, 'omm_one', setup_usage[3], report(policy, record, challenge_id=record['challenge_id']), now)
    client.freebusy.side_effect = [client.freebusy.return_value, {'free_busy': {'omm_one': []}}]
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    assert (await store.get(key))['state'] == 'released'
    client.release.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['no_reply', 'uncertain', 'submitting', 'old_protocol', 'new_session', 'stale_ack'])
async def test_page_fault_protects_occurrence_permanently(setup_usage, monkeypatch, fault):
    store, client, key, old, policy, now, snapshot, epoch = await make_due(setup_usage, monkeypatch)
    if fault == 'no_reply':
        old.update(ack_at=None, challenge_expires=now.timestamp())
    if fault == 'stale_ack':
        old.update(challenge_expires=now.timestamp() - 1)
    await store.put(key, old)
    if fault in {'uncertain', 'submitting'}:
        await heartbeat(store, 'omm_one', setup_usage[3], report(policy, old, fault), now)
    if fault in {'old_protocol', 'new_session'}:
        hb = health(setup_usage[3], policy, snapshot, now)
        hb.update({'protocol': 1} if fault == 'old_protocol' else {'session_id': 'c' * 32})
        await store.put('heartbeat:omm_one', hb)
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    assert (await store.get(key))['state'] == 'blocked'
    await store.put('heartbeat:omm_one', health(setup_usage[3], policy, snapshot, now))
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    client.release.assert_not_called()


@pytest.mark.asyncio
async def test_api_delay_invalidates_ack_before_write(setup_usage, monkeypatch):
    store, client, key, _old, _, now, _, epoch = await make_due(setup_usage, monkeypatch)
    class Clock:
        @staticmethod
        def now(tz):
            return now + timedelta(seconds=20)
    async def slow_query(*args):
        monkeypatch.setattr(worker, 'datetime', Clock)
        return client.freebusy.return_value
    client.freebusy.side_effect = slow_query
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    assert (await store.get(key))['state'] == 'blocked'
    client.release.assert_not_called()


@pytest.mark.asyncio
async def test_cache_delay_after_upstream_check_does_not_use_expired_ack(setup_usage, monkeypatch):
    store, client, key, _old, _, now, _, epoch = await make_due(setup_usage, monkeypatch)
    original = worker.fresh_target
    reads = 0
    class Clock:
        @staticmethod
        def now(tz):
            return now + timedelta(seconds=20)
    async def delayed_cache(*args):
        nonlocal reads
        result = await original(*args)
        reads += 1
        if reads == 2:
            monkeypatch.setattr(worker, 'datetime', Clock)
        return result
    monkeypatch.setattr(worker, 'fresh_target', delayed_cache)
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    client.release.assert_not_called()
    assert (await store.get(key))['state'] == 'blocked'


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['room', 'policy', 'challenge', 'session', 'epoch'])
async def test_invalid_heartbeat_cannot_authorize_release(setup_usage, monkeypatch, fault):
    store, client, key, record, policy, now, _, _epoch = await make_due(setup_usage, monkeypatch)
    request = report(policy, record, challenge_id=record['challenge_id'])
    if fault == 'room': request.occurrence_id = '0' * 64
    if fault == 'policy': request.policy_revision = 'old'
    if fault == 'challenge': request.challenge_id = 'f' * 32
    if fault == 'session': request.session_id = 'f' * 32
    if fault == 'epoch': await store.cache.delete(worker.LEASE)
    record['ack_at'] = None
    await store.put(key, record)
    with pytest.raises(AppError):
        await heartbeat(store, 'omm_one', setup_usage[3], request, now)
    assert (await store.get(key))['ack_at'] is None
    client.release.assert_not_called()


@pytest.mark.asyncio
async def test_official_owner_and_legacy_policy_cannot_release(setup_usage, monkeypatch):
    store, client, _key, _, policy, now, snapshot, epoch = await make_due(setup_usage, monkeypatch)
    with pytest.raises(AppError):
        await service.save_policy(store, 'omm_one', UsagePolicy(owner='official', mode='observe'))
    policy.pop('owner')
    await store.put('policy:omm_one', policy)
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    assert (await service.view(store, 'omm_one', now))['policy']['owner'] == 'official'
    assert not await service.write_allowed(store, policy, 'omm_one')
    client.release.assert_not_called()
    await service.save_policy(store, 'omm_one', UsagePolicy(owner='v5', mode='observe'))
    monkeypatch.setattr('app.room_display_main.checkin_qr', lambda _: 'fixture-qr')
    display = await decorate(snapshot)
    assert display.checkin_qr is None and display.usage_owner == 'v5'
    await service.save_policy(store, 'omm_one', UsagePolicy())
    assert (await decorate(snapshot)).checkin_qr == 'fixture-qr'


@pytest.mark.asyncio
async def test_heartbeat_endpoint_auth_validation_and_read_isolation(setup_usage):
    store, _, token, _, policy, now, _, _ = setup_usage
    state = await service.view(store, 'omm_one', now)
    payload = report(policy, state['record']).model_dump()
    path = '/api/meeting-rooms/usage/heartbeat'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as http:
        for value in ['', settings.ROOM_DISPLAY_CONTROL_TOKEN]:
            assert (await http.post(path, json=payload, headers={'Authorization': 'Bearer ' + value})).status_code == 401
        headers = {'Authorization': 'Bearer ' + token}
        assert (await http.post(path, json={**payload, 'protocol': 1}, headers=headers)).status_code == 422
        assert (await http.post(path, json=payload, headers=headers)).status_code == 200
        before = await store.get('heartbeat:omm_one')
        await http.get('/api/meeting-rooms/usage', headers=headers)
        assert await store.get('heartbeat:omm_one') == before


@pytest.mark.asyncio
@pytest.mark.parametrize('allowed', [set(), {'omm_other'}, {'omm_onex'}, {'*'}])
async def test_server_allowlist_blocks_even_fully_authorized_auto_policy(setup_usage, monkeypatch, allowed):
    store, client, key, _, _, now, _, epoch = await make_due(setup_usage, monkeypatch)
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_RELEASE_ROOM_IDS', allowed)
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    assert (await store.get(key))['state'] == 'blocked'
    client.release.assert_not_called()
    assert not (await service.view(store, 'omm_one', now))['can_end']


@pytest.mark.asyncio
async def test_allowlist_revocation_during_preflight_blocks_write(setup_usage, monkeypatch):
    store, client, key, _, _, now, _, epoch = await make_due(setup_usage, monkeypatch)
    async def revoke(*args):
        monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_RELEASE_ROOM_IDS', set())
        return client.freebusy.return_value
    client.freebusy.side_effect = revoke
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    assert (await store.get(key))['state'] == 'blocked'
    client.release.assert_not_called()


@pytest.mark.asyncio
async def test_control_reports_write_availability_per_room(setup_usage, monkeypatch):
    await make_due(setup_usage, monkeypatch)
    headers = {'Authorization': 'Bearer ' + settings.ROOM_DISPLAY_CONTROL_TOKEN}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as http:
        for room, expected in [('omm_one', True), ('omm_other', False)]:
            response = await http.get('/api/room-control/usage/' + room, headers=headers)
            assert response.status_code == 200
            assert response.json()['data']['writes_enabled'] is expected


@pytest.mark.asyncio
async def test_allowlist_also_blocks_manual_early_end(setup_usage, monkeypatch):
    store, client, key, old, _, now, _, _ = await make_due(setup_usage, monkeypatch)
    await store.put(key, {**old, 'state': 'confirmed'})
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_USAGE_RELEASE_ROOM_IDS', {'omm_other'})
    request = await request_for(store, now)
    assert not (await service.view(store, 'omm_one', now))['can_end']
    with pytest.raises(AppError):
        await service.command(store, 'omm_one', setup_usage[3], request, 'end', now)
    assert (await store.get(key))['state'] == 'confirmed'
    client.release.assert_not_called()
