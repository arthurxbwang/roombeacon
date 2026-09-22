"""Successful releases must publish real readback without breaking the next window."""
from datetime import UTC, datetime, timedelta

import pytest

from app.schemas.meeting_room import RoomSchedule
from app.services import room_display_collector as collector
from app.services import room_usage as service
from app.services import room_usage_worker as worker
from app.services.room_usage_health import heartbeat
from tests.services import test_room_usage as support
from tests.services.test_room_usage_adjacent import adjacent, report

redis_socket = support.redis_socket
setup_usage = support.setup_usage


@pytest.mark.asyncio
async def test_release_readback_keeps_next_booking_fresh_and_monitored(setup_usage, monkeypatch):
    store, client, _, actor, policy, now, snapshot, epoch = setup_usage
    first, second = await adjacent(setup_usage, 'pending')
    await heartbeat(store, 'omm_one', actor, report(policy, first, second), now)
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    await support.make_due(setup_usage, monkeypatch)
    await store.cache.set('rooms:snapshot:omm_one', snapshot.model_dump_json(), ex=300)
    monkeypatch.setattr(service, 'cached_schedule', collector.cached_schedule)
    client.freebusy.side_effect = [
        {'free_busy': {'omm_one': [e.model_dump(mode='json') for e in snapshot.events]}},
        {'free_busy': {'omm_one': [snapshot.events[1].model_dump(mode='json')]}},
    ]
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    saved = RoomSchedule.model_validate_json(await store.cache.get('rooms:snapshot:omm_one'))
    assert saved.valid_until > datetime.now(UTC), 'Successful release must not stale the entire room until the next five-minute collection'
    assert [e.uid for e in saved.events] == ['next-booking']
    state = await service.view(store, 'omm_one', now + timedelta(seconds=5))
    assert state['target_id'] == second
    await heartbeat(store, 'omm_one', actor, report(policy, second, second), now + timedelta(seconds=5))
    await worker.tick_room(store, client, 'omm_one', epoch, now + timedelta(seconds=5))
    assert (await store.get('record:' + first))['state'] == 'released'
    assert (await store.get('record:' + second))['state'] == 'pending'
    client.release.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['timeout', 'missing', 'room_error', 'malformed', 'still_busy'])
async def test_failed_readback_never_invents_free_time_or_retries(setup_usage, monkeypatch, failure):
    import httpx

    store, client, key, _, _, now, snapshot, epoch = await support.make_due(setup_usage, monkeypatch)
    await store.cache.set('rooms:snapshot:omm_one', snapshot.model_dump_json(), ex=300)
    await store.cache.set('rooms:snapshot:omm_other', 'unrelated-room-sentinel', ex=300)
    original = client.freebusy.return_value
    invalid = {
        'timeout': httpx.ReadTimeout('fixture'),
        'missing': {'free_busy': {}},
        'room_error': {'free_busy': {'omm_one': []}, 'error_room_ids': ['omm_one']},
        'malformed': {'free_busy': {'omm_one': [{'uid': 'bad', 'start_time': 'invalid'}]}},
        'still_busy': original,
    }[failure]
    client.freebusy.side_effect = [original, invalid]
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    assert (await store.get(key))['state'] == 'uncertain'
    saved = RoomSchedule.model_validate_json(await store.cache.get('rooms:snapshot:omm_one'))
    assert saved.valid_until <= datetime.now(UTC)
    assert saved.events[0].uid == snapshot.events[0].uid
    assert await store.cache.get('rooms:snapshot:omm_other') == 'unrelated-room-sentinel'
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    client.release.assert_awaited_once()


@pytest.mark.asyncio
async def test_readback_keeps_new_upstream_bookings_and_full_query_window(setup_usage, monkeypatch):
    from app.services.meeting_rooms import ZONE

    store, client, key, _, _, now, snapshot, epoch = await support.make_due(setup_usage, monkeypatch)
    await store.cache.set('rooms:snapshot:omm_one', snapshot.model_dump_json(), ex=300)
    other = snapshot.events[0].model_copy(update={
        'uid': 'created-during-release', 'start_time': now + timedelta(hours=1), 'end_time': now + timedelta(hours=2)})
    client.freebusy.side_effect = [client.freebusy.return_value, {'free_busy': {'omm_one': [other.model_dump(mode='json')]}}]
    await worker.tick_room(store, client, 'omm_one', epoch, now)
    assert (await store.get(key))['state'] == 'released'
    saved = RoomSchedule.model_validate_json(await store.cache.get('rooms:snapshot:omm_one'))
    assert [e.uid for e in saved.events] == ['created-during-release']
    day = saved.synced_at.astimezone(ZONE).replace(hour=0, minute=0, second=0, microsecond=0)
    assert client.freebusy.await_args.args == (['omm_one'], day - timedelta(days=1), day + timedelta(days=2))
    assert 0 < (saved.valid_until - saved.synced_at).total_seconds() <= 360
    assert not saved.titles_available


@pytest.mark.asyncio
async def test_slow_collector_cannot_restore_released_booking(setup_usage, monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock

    from app.services.meeting_rooms import refresh_batch
    from app.services.room_schedule_cache import save_snapshot

    store, _, _, _, _, now, snapshot, _ = setup_usage
    began, finish = asyncio.Event(), asyncio.Event()
    client = AsyncMock()
    async def old_response(*args):
        began.set()
        await finish.wait()
        return {'free_busy': {'omm_one': [e.model_dump(mode='json') for e in snapshot.events]}}
    client.freebusy.side_effect = old_response
    task = asyncio.create_task(refresh_batch(store.cache, client, [snapshot.room], now - timedelta(seconds=30)))
    await began.wait()
    newer = snapshot.model_copy(update={'events': [], 'synced_at': now})
    await save_snapshot(store.cache, newer, 300)
    finish.set()
    await task
    saved = RoomSchedule.model_validate_json(await store.cache.get('rooms:snapshot:omm_one'))
    assert saved.events == [] and saved.synced_at == now


@pytest.mark.asyncio
async def test_snapshot_compare_swap_preserves_concurrent_newer_refresh(setup_usage, monkeypatch):
    from app.services.room_schedule_cache import save_snapshot

    store, _, _, _, _, now, snapshot, _ = setup_usage
    key = 'rooms:snapshot:omm_one'
    await store.cache.set(key, snapshot.model_dump_json())
    newer = snapshot.model_copy(update={'events': [], 'synced_at': now + timedelta(seconds=1)})
    real_eval = store.cache.eval
    async def raced(*args):
        await store.cache.set(key, newer.model_dump_json())
        return await real_eval(*args)
    monkeypatch.setattr(store.cache, 'eval', raced)
    assert not await save_snapshot(store.cache, snapshot, 300)
    assert await store.cache.get(key) == newer.model_dump_json()


@pytest.mark.asyncio
async def test_valid_collection_repairs_corrupt_snapshot_with_bounded_ttl(setup_usage):
    from app.services.room_schedule_cache import save_snapshot

    store, _, _, _, _, _, snapshot, _ = setup_usage
    key = 'rooms:snapshot:omm_one'
    await store.cache.set(key, '{invalid')
    assert await save_snapshot(store.cache, snapshot, 300)
    assert RoomSchedule.model_validate_json(await store.cache.get(key)) == snapshot
    assert 0 < await store.cache.ttl(key) <= 300


@pytest.mark.asyncio
async def test_snapshot_publication_race_fails_explicitly(setup_usage, monkeypatch):
    from unittest.mock import AsyncMock

    from app.services.room_schedule_cache import save_snapshot

    store, _, _, _, _, _, snapshot, _ = setup_usage
    monkeypatch.setattr(store.cache, 'eval', AsyncMock(return_value=0))
    with pytest.raises(RuntimeError, match='Concurrent snapshot'):
        await save_snapshot(store.cache, snapshot, 300)
    assert store.cache.eval.await_count == 3
    assert await store.cache.get('rooms:snapshot:omm_one') is None
