"""Behavior of central refresh, cache-only reads and outage continuity."""
import asyncio
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.connectors.feishu.rooms import FeishuRoomsClient
from app.core.exceptions import ExternalAPIError, NotFoundError
from app.services import room_display_collector as collector


async def collect(world):
    world.values[collector.LOCK] = 'test-owner'
    client = FeishuRoomsClient()
    try:
        await collector.collect_once(world.cache, client, 'test-owner')
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_all_rooms_are_warmed_without_visitors_and_reads_never_call_feishu(world):
    world.rooms += [{'room_id': 'omm_two', 'name': '二号'}]
    world.busy['omm_two'] = []
    await collect(world)
    assert len([r for r in world.requests if '/freebusy/' in r.url.path]) == 1
    world.requests.clear()
    results = await asyncio.gather(*[collector.cached_schedule('omm_one') for _ in range(50)])
    assert all(r.events[0].summary == '产品设计评审' for r in results)
    assert (await collector.cached_schedule('omm_two')).events == []
    assert len(await collector.cached_directory()) == 2
    assert world.requests == []
    assert json.loads(world.values[collector.STATUS])['refreshed_rooms'] == 2


@pytest.mark.asyncio
async def test_expired_history_survives_upstream_failure(world):
    await collect(world)
    key = 'rooms:snapshot:omm_one'
    previous = json.loads(world.values[key])
    previous['valid_until'] = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    world.values[key] = json.dumps(previous)
    world.busy_error = True
    await collect(world)
    world.requests.clear()
    result = await collector.cached_schedule('omm_one')
    assert result.events[0].summary == '产品设计评审'
    assert result.valid_until < datetime.now(UTC)
    assert result.synced_at.isoformat() == previous['synced_at'].replace('Z', '+00:00')
    assert world.requests == []
    assert json.loads(world.values[collector.STATUS])['state'] == 'partial'


@pytest.mark.asyncio
async def test_partial_room_failure_keeps_its_snapshot_and_refreshes_other_rooms(world):
    world.rooms += [{'room_id': 'omm_two', 'name': '二号'}]
    world.busy['omm_two'] = []
    await collect(world)
    previous = world.values['rooms:snapshot:omm_one']
    world.error_rooms = ['omm_one']
    world.busy['omm_two'] = world.events
    await collect(world)
    assert world.values['rooms:snapshot:omm_one'] == previous
    assert (await collector.cached_schedule('omm_two')).events
    assert json.loads(world.values[collector.STATUS])['state'] == 'partial'


@pytest.mark.asyncio
async def test_cold_cache_fails_fast_without_upstream_request(world):
    with pytest.raises(ExternalAPIError):
        await collector.cached_schedule('omm_one')
    with pytest.raises(ExternalAPIError):
        await collector.cached_directory()
    assert world.requests == []


@pytest.mark.asyncio
async def test_deleted_room_cannot_read_old_schedule(world):
    await collect(world)
    world.values[collector.DIRECTORY] = '[]'
    with pytest.raises(NotFoundError):
        await collector.cached_schedule('omm_one')


@pytest.mark.asyncio
async def test_reads_do_not_wait_for_inflight_slow_refresh(world, monkeypatch):
    await collect(world)
    started = asyncio.Event()

    async def slow(*args, **kwargs):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(FeishuRoomsClient, 'freebusy', slow)
    worker = asyncio.create_task(collect(world))
    await started.wait()
    try:
        result = await asyncio.wait_for(collector.cached_schedule('omm_one'), timeout=.5)
        assert result.events
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)


@pytest.mark.asyncio
async def test_only_one_collector_runs_with_shared_lease(world, monkeypatch):
    started = asyncio.Event()
    calls = []

    async def blocked(*args):
        calls.append(args[-1])
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(collector, 'collect_once', blocked)
    first = asyncio.create_task(collector.collector_loop())
    second = asyncio.create_task(collector.collector_loop())
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        await asyncio.sleep(.02)
        assert len(calls) == 1
    finally:
        first.cancel()
        second.cancel()
        await asyncio.gather(first, second, return_exceptions=True)


@pytest.mark.asyncio
async def test_lifespan_stops_background_task(monkeypatch):
    from app.room_display_main import app
    started, stopped = asyncio.Event(), asyncio.Event()

    async def loop():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    monkeypatch.setattr('app.room_display_main.collector_loop', loop)
    async with app.router.lifespan_context(app):
        await started.wait()
    assert stopped.is_set()


@pytest.mark.asyncio
async def test_catalog_outage_preserves_directory(world, monkeypatch):
    await collect(world)
    world.values['rooms:collector:directory-time'] = '0'
    monkeypatch.setattr(FeishuRoomsClient, 'list_rooms', AsyncMock(side_effect=TimeoutError))
    await collect(world)
    assert (await collector.cached_directory())[0]['room_id'] == 'omm_one'
    assert (await collector.cached_schedule('omm_one')).events


@pytest.mark.asyncio
async def test_one_malformed_room_does_not_discard_other_room_updates(world):
    world.rooms += [{'room_id': 'omm_two', 'name': '二号'}]
    world.busy['omm_two'] = []
    await collect(world)
    previous = world.values['rooms:snapshot:omm_one']
    world.busy['omm_one'] = [{**world.events[0], 'start_time': 'invalid'}]
    world.busy['omm_two'] = world.events
    await collect(world)
    assert world.values['rooms:snapshot:omm_one'] == previous
    assert (await collector.cached_schedule('omm_two')).events
    assert json.loads(world.values[collector.STATUS])['refreshed_rooms'] == 1
