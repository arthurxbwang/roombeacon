"""Zero extra check-in time keeps the existing release checks."""
from datetime import datetime, timedelta

import pytest
from pydantic import ValidationError

from app.core.exceptions import AppError
from app.management.catalog_models import Rules
from app.schemas.room_usage import UsagePolicy
from app.services import room_usage as service
from app.services import room_usage_worker as worker
from app.services.room_usage_health import heartbeat
from tests.services import test_room_usage as support
from tests.services.test_room_usage_protection import report

redis_socket = support.redis_socket
setup_usage = support.setup_usage


@pytest.mark.parametrize('model', [Rules, UsagePolicy])
def test_zero_buffer_is_valid_but_negative_is_rejected(model):
    assert model(release_delay_seconds=0).release_delay_seconds == 0
    with pytest.raises(ValidationError):
        model(release_delay_seconds=-1)


@pytest.mark.asyncio
async def test_deadline_closes_confirmation_without_skipping_checks(setup_usage, monkeypatch):
    store, client, key, old, policy, now, _, epoch = await support.make_due(setup_usage, monkeypatch)
    policy['release_delay_seconds'] = 0
    await store.put('policy:omm_one', policy)
    old.update(state='pending', deadline=now.isoformat())
    await store.put(key, old)
    request = await support.request_for(store, now - timedelta(microseconds=1))
    assert (await service.view(store, 'omm_one', now - timedelta(microseconds=1)))['can_confirm']
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    waiting = await store.get(key)
    assert waiting['state'] == 'waiting'
    assert datetime.fromisoformat(waiting['release_at']) == now
    assert not (await service.view(store, 'omm_one', now))['can_confirm']
    with pytest.raises(AppError):
        await service.command(store, 'omm_one', setup_usage[3], request, 'confirm', now)
    client.release.assert_not_called()
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    checking = await store.get(key)
    assert checking['state'] == 'checking' and checking['ack_at'] is None
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    client.release.assert_not_called()
    await heartbeat(store, 'omm_one', setup_usage[3], report(policy, checking,
                    challenge_id=checking['challenge_id']), now)
    client.freebusy.side_effect = [client.freebusy.return_value, {'free_busy': {'omm_one': []}}]
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    assert (await store.get(key))['state'] == 'released'
    client.release.assert_awaited_once()


@pytest.mark.asyncio
async def test_zero_buffer_offline_page_never_releases(setup_usage, monkeypatch):
    store, client, key, old, policy, now, _, epoch = await support.make_due(setup_usage, monkeypatch)
    policy['release_delay_seconds'] = 0
    await store.put('policy:omm_one', policy)
    old.update(state='waiting', release_at=now.isoformat())
    await store.put(key, old)
    await store.cache.delete('rooms:usage:v1:heartbeat:omm_one')
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    assert (await store.get(key))['state'] == 'blocked'
    client.release.assert_not_called()


@pytest.mark.asyncio
async def test_late_worker_does_not_extend_zero_buffer_deadline(setup_usage, monkeypatch):
    store, client, key, old, policy, now, _, epoch = await support.make_due(setup_usage, monkeypatch)
    policy['release_delay_seconds'] = 0
    await store.put('policy:omm_one', policy)
    old.update(state='pending', deadline=(now - timedelta(seconds=5)).isoformat())
    await store.put(key, old)
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    waiting = await store.get(key)
    assert waiting['release_at'] == old['deadline']
    assert not (await service.view(store, 'omm_one', now))['can_confirm']
    client.release.assert_not_called()
