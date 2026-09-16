import subprocess
import sys

import pytest
import pytest_asyncio
from httpx import ASGITransport

from app.core.room_devices import issue_device
from app.room_display_main import app
from tests.fixtures.meeting_rooms import HttpClient


@pytest_asyncio.fixture(autouse=True)
async def prepared_snapshots(world):
    from app.connectors.feishu.rooms import FeishuRoomsClient
    from app.services.room_display_collector import LOCK, collect_once
    world.values[LOCK] = 'test-owner'
    client = FeishuRoomsClient()
    try:
        await collect_once(world.cache, client, 'test-owner')
    finally:
        await client.close()
    world.requests.clear()


@pytest.mark.asyncio
async def test_isolated_app_only_serves_bound_room(world):
    token = await issue_device("omm_one")
    async with HttpClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/meeting-rooms/display")).status_code == 401
        headers = {"Authorization": "Bearer " + token}
        response = await client.get("/api/meeting-rooms/display", headers=headers)
        assert response.status_code == 200
        assert response.json()["data"]["room"]["room_id"] == "omm_one"
        for path in ["/api/meeting-rooms", "/api/auth/login", "/api/admin/users", "/docs"]:
            assert (await client.get(path, headers=headers)).status_code == 404
        assert (await client.post("/api/meeting-rooms/display", headers=headers)).status_code == 405
        assert world.requests == []


def test_standalone_config_needs_no_database():
    from app.core.config import Settings
    settings = Settings(_env_file=None)
    assert "DATABASE_URL" not in Settings.model_fields
    assert "SECRET_KEY" not in Settings.model_fields
    assert settings.ROOM_DISPLAY_SYNC_SECONDS >= 120
    subprocess.run([sys.executable, "-c",
                    ("import app.room_display_main; import sys; "
                    "assert 'app.tasks' not in sys.modules; "
                    "assert 'app.db' not in sys.modules")], check=True, timeout=20)


@pytest.mark.asyncio
async def test_control_auth_is_separate_and_preview_does_not_issue_devices(world, monkeypatch):
    from unittest.mock import AsyncMock

    from app import room_display_main
    from app.core.config import settings
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_CONTROL_TOKEN', 'control-' + 'x' * 40)
    monkeypatch.setattr(room_display_main, 'directory', AsyncMock(return_value=[{'room_id': 'omm_one'}]))
    token = await issue_device('omm_one')
    async with HttpClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        assert (await client.get('/api/room-control/rooms')).status_code == 401
        assert (await client.get('/api/room-control/rooms', headers={'Authorization': 'Bearer ' + token})).status_code == 401
        headers = {'Authorization': 'Bearer ' + settings.ROOM_DISPLAY_CONTROL_TOKEN}
        assert (await client.get('/api/room-control/rooms', headers=headers)).status_code == 200
        r = await client.get('/api/room-control/preview?room_id=omm_one', headers=headers)
        assert r.status_code == 200
        assert r.json()['data']['room']['room_id'] == 'omm_one'
        assert (await client.get('/api/room-control/preview?room_id=invalid', headers=headers)).status_code == 422
        assert (await client.post('/api/room-control/rooms', headers=headers)).status_code == 405
        assert (await client.get('/api/meeting-rooms/display', headers=headers)).status_code == 401
        assert (await client.get('/api/meeting-rooms/display', headers={'Authorization': 'Bearer ' + token})).status_code == 200


@pytest.mark.asyncio
async def test_control_secondary_is_independent_and_revocable(world, monkeypatch):
    from unittest.mock import AsyncMock

    from app import room_display_main
    from app.core.config import settings

    primary, secondary = 'primary-' + 'a' * 40, 'secondary-' + 'b' * 40
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_CONTROL_TOKEN', primary)
    monkeypatch.setattr(settings, 'ROOM_DISPLAY_CONTROL_TOKEN_SECONDARY', secondary)
    monkeypatch.setattr(room_display_main, 'directory', AsyncMock(return_value=[]))
    async with HttpClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        async def status(token):
            return (await client.get('/api/room-control/rooms', headers={'Authorization': 'Bearer ' + token})).status_code

        assert await status(primary) == 200
        assert await status(secondary) == 200
        assert await status('incorrect') == 401
        assert await status('') == 401
        assert (await client.get('/api/room-control/preview?room_id=omm_one',
                                headers={'Authorization': 'Bearer ' + secondary})).status_code == 200
        assert (await client.get('/api/meeting-rooms/display',
                                headers={'Authorization': 'Bearer ' + secondary})).status_code == 401
        monkeypatch.setattr(settings, 'ROOM_DISPLAY_CONTROL_TOKEN_SECONDARY', '')
        assert await status(secondary) == 401
        assert await status(primary) == 200
        monkeypatch.setattr(settings, 'ROOM_DISPLAY_CONTROL_TOKEN_SECONDARY', 'short')
        assert await status('short') == 200
        assert await status('shorT') == 401
        monkeypatch.setattr(settings, 'ROOM_DISPLAY_CONTROL_TOKEN_SECONDARY', ' ')
        assert await status(' ') == 401
        monkeypatch.setattr(settings, 'ROOM_DISPLAY_CONTROL_TOKEN_SECONDARY', '')
        monkeypatch.setattr(settings, 'ROOM_DISPLAY_CONTROL_TOKEN', '')
        assert await status('') == 401
