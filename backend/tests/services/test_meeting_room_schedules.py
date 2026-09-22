import json
from datetime import UTC, datetime, timedelta

import pytest

from app.connectors.feishu.rooms import FeishuRoomsClient
from app.core.exceptions import ExternalAPIError, NotFoundError
from app.services.meeting_room_events import invalidate_room
from app.services.meeting_rooms import list_rooms, parse_events, schedule_for


@pytest.mark.asyncio
async def test_schedule_queries_repeated_room_ids_and_reuses_batch(world):
    world.rooms.append({'room_id': 'omm_two', 'name': '泰山'})
    world.busy['omm_two'] = []
    first = await schedule_for('omm_one')
    second = await schedule_for('omm_two')
    queries = [r for r in world.requests if '/freebusy/' in r.url.path]
    assert len(queries) == 1
    assert queries[0].url.params.get_list('room_ids') == ['omm_one', 'omm_two']
    assert first.events[0].summary == '产品设计评审'
    assert second.events == []


@pytest.mark.asyncio
async def test_hidden_organizer_does_not_request_or_display_title(world):
    world.events[0]['organizer_info'] = None
    schedule = await schedule_for('omm_one')
    assert schedule.events[0].organizer is None
    assert schedule.events[0].summary is None
    assert not any('/summary/' in r.url.path for r in world.requests)


@pytest.mark.asyncio
async def test_title_permission_failure_preserves_busy_times(world):
    world.title_error = True
    schedule = await schedule_for('omm_one')
    assert schedule.events and schedule.events[0].summary is None
    assert schedule.titles_available is False


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['missing', 'partial', 'quota'])
async def test_upstream_failure_never_becomes_empty_free_room(world, failure):
    if failure == 'missing':
        world.busy = {}
    elif failure == 'partial':
        world.error_rooms = ['omm_one']
    else:
        world.busy_error = True
    with pytest.raises(ExternalAPIError):
        await schedule_for('omm_one')
    assert 'rooms:snapshot:omm_one' not in world.values


@pytest.mark.asyncio
async def test_unknown_room_is_not_queried(world):
    with pytest.raises(NotFoundError):
        await schedule_for('omm_unknown')
    assert not any('/freebusy/' in r.url.path for r in world.requests)


@pytest.mark.asyncio
async def test_catalog_empty_and_pagination_loop(world):
    world.rooms = []
    assert await list_rooms() == []
    world.values.clear()
    world.page_loop = True
    with pytest.raises(ExternalAPIError):
        await list_rooms()


@pytest.mark.asyncio
async def test_event_invalidates_fresh_snapshot_and_cooldown_returns_unknown(world):
    first = await schedule_for('omm_one')
    await invalidate_room('omm_one')
    second = await schedule_for('omm_one')
    assert second.valid_until < first.valid_until
    assert second.valid_until <= datetime.now(UTC)
    assert second.events == first.events


@pytest.mark.asyncio
async def test_event_refresh_removes_cancelled_meeting(world):
    await schedule_for('omm_one')
    await invalidate_room('omm_one')
    for key in list(world.values):
        if key.startswith('rooms:refresh:'):
            del world.values[key]
    world.busy['omm_one'] = []
    assert (await schedule_for('omm_one')).events == []


@pytest.mark.asyncio
async def test_stale_snapshot_during_parallel_refresh_stays_stale(world):
    first = await schedule_for('omm_one')
    first.valid_until = datetime.now(UTC) - timedelta(seconds=1)
    world.values['rooms:snapshot:omm_one'] = first.model_dump_json()
    assert (await schedule_for('omm_one')).valid_until <= datetime.now(UTC)


@pytest.mark.asyncio
async def test_snapshot_has_bounded_freshness(world):
    result = await schedule_for('omm_one')
    assert result.valid_until - result.synced_at <= timedelta(minutes=5)
    assert json.loads(world.values['rooms:snapshot:omm_one'])['room']['name'] == '望岳'


def test_recurring_instances_with_zero_original_time_are_not_collapsed(world):
    second = {**world.events[0], 'start_time': '2026-09-15T18:00:00+08:00', 'end_time': '2026-09-15T19:00:00+08:00'}
    assert len(parse_events([world.events[0], world.events[0], second])) == 2


@pytest.mark.parametrize('start,end', [('bad', 'bad'), ('2026-09-15T14:00:00', '2026-09-15T15:00:00'), ('2026-09-15T15:00:00Z', '2026-09-15T14:00:00Z')])
def test_invalid_times_are_rejected(world, start, end):
    with pytest.raises(ValueError):
        parse_events([{**world.events[0], 'start_time': start, 'end_time': end}])


@pytest.mark.asyncio
async def test_connector_rejects_oversized_batch_without_network(world):
    with pytest.raises(ValueError):
        await FeishuRoomsClient().freebusy(['omm_one'] * 21, datetime.now(UTC), datetime.now(UTC))
    assert not world.requests


@pytest.mark.asyncio
async def test_complete_feishu_envelope_omits_rooms_without_bookings(world):
    world.complete_busy_envelope = True
    world.busy = {}
    result = await schedule_for('omm_one')
    assert result.events == []
    assert result.valid_until > result.synced_at


@pytest.mark.asyncio
async def test_complete_envelope_still_rejects_failed_rooms(world):
    world.complete_busy_envelope = True
    world.busy = {}
    world.error_rooms = ['omm_one']
    with pytest.raises(ExternalAPIError):
        await schedule_for('omm_one')
