"""A fetched multi-day schedule stays fresh across midnight, but never past TTL."""
from datetime import datetime, timedelta

import pytest

from app.connectors.feishu.rooms import FeishuRoomsClient
from app.core.exceptions import AppError, ExternalAPIError
from app.schemas.meeting_room import Room, RoomSchedule
from app.services.meeting_rooms import refresh_batch
from app.services.room_usage import fresh_target


@pytest.mark.asyncio
@pytest.mark.parametrize('fresh_seconds', [300, 360])
async def test_midnight_keeps_fetched_booking_until_normal_expiry(world, fresh_seconds):
    before = datetime.fromisoformat('2026-09-20T23:58:00+08:00')
    world.events[0].update(start_time='2026-09-21T00:00:00+08:00', end_time='2026-09-21T00:30:00+08:00')
    client = FeishuRoomsClient()
    try:
        await refresh_batch(world.cache, client, [Room(room_id='omm_one', name='fixture')], before,
                            fresh_seconds=fresh_seconds)
    finally:
        await client.close()
    snapshot = RoomSchedule.model_validate_json(world.values['rooms:snapshot:omm_one'])
    assert snapshot.valid_until == before + timedelta(seconds=fresh_seconds)
    world.requests.clear()
    target = await fresh_target('omm_one', before + timedelta(minutes=3))
    assert target.uid == 'event1'
    with pytest.raises(AppError):
        await fresh_target('omm_one', snapshot.valid_until)
    assert world.requests == []


@pytest.mark.asyncio
async def test_midnight_upstream_failure_does_not_extend_cached_validity(world):
    before = datetime.fromisoformat('2026-09-20T23:58:00+08:00')
    client = FeishuRoomsClient()
    room = Room(room_id='omm_one', name='fixture')
    try:
        await refresh_batch(world.cache, client, [room], before, fresh_seconds=360)
        saved = world.values['rooms:snapshot:omm_one']
        world.busy_error = True
        with pytest.raises(ExternalAPIError):
            await refresh_batch(world.cache, client, [room], before + timedelta(minutes=3), fresh_seconds=360)
        assert world.values['rooms:snapshot:omm_one'] == saved
        assert RoomSchedule.model_validate_json(saved).valid_until == before + timedelta(minutes=6)
    finally:
        await client.close()
