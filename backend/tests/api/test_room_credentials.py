import pytest

from app.core.exceptions import ExternalAPIError, UnauthorizedError
from app.core.room_devices import authenticate_device, issue_device, revoke_device


@pytest.mark.asyncio
async def test_device_rotation_revocation_and_room_binding(world):
    old = await issue_device("omm_one")
    fresh = await issue_device("omm_one")
    assert (await authenticate_device(fresh, "/api/meeting-rooms/display", "GET"))["room_id"] == "omm_one"
    with pytest.raises(UnauthorizedError):
        await authenticate_device(old, "/api/meeting-rooms/display", "GET")
    await revoke_device("omm_one")
    with pytest.raises(UnauthorizedError):
        await authenticate_device(fresh, "/api/meeting-rooms/display", "GET")
    assert fresh not in str(world.values)


@pytest.mark.asyncio
@pytest.mark.parametrize("path,method", [("/api/admin/users", "GET"), ("/api/meeting-rooms/device", "POST"), ("/api/meeting-rooms/display", "POST")])
async def test_display_credentials_cannot_access_other_routes(world, path, method):
    token = await issue_device("omm_one")
    with pytest.raises(UnauthorizedError):
        await authenticate_device(token, path, method)


@pytest.mark.asyncio
async def test_redis_failure_denies_device_access(world):
    from redis.exceptions import ConnectionError
    world.cache.get.side_effect = ConnectionError("unavailable")
    with pytest.raises(ExternalAPIError):
        await authenticate_device("room:omm_one:" + "a" * 43, "/api/meeting-rooms/display", "GET")
