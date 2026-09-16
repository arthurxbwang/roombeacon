"""City astronomy and metadata failure boundaries."""
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from app.services.room_daylight import plan_for_location, room_daylight


def test_city_timezone_and_seasons():
    winter = plan_for_location('中国 / 北京 / 总部', datetime(2026, 12, 21, tzinfo=UTC))
    summer = plan_for_location('中国 / 北京 / 总部', datetime(2026, 6, 21, tzinfo=UTC))
    assert winter.timezone == 'Asia/Shanghai'
    assert summer.windows[1].end - summer.windows[1].start > winter.windows[1].end - winter.windows[1].start
    assert summer.windows[1].start.hour in (4, 5)
    assert summer.windows[1].end.hour in (19, 20)
    toronto = plan_for_location('加拿大 / 多伦多', datetime(2026, 9, 15, 1, tzinfo=UTC))
    assert toronto.timezone == 'America/Toronto'
    assert toronto.windows[1].start.day == 14
    india = plan_for_location('印度 / Hyderabad', datetime(2026, 9, 15, tzinfo=UTC))
    assert india.windows[1].start.utcoffset().total_seconds() == 19800


@pytest.mark.parametrize('location', ['波兰 / 波兰分部 / Poland Office', '美国CES / CES2025', '未知'])
def test_unknown_location_is_not_beijing(location):
    plan = plan_for_location(location, datetime.now(UTC))
    assert plan.city is None
    assert plan.windows == []


@pytest.mark.asyncio
async def test_directory_failure_degrades_theme_only(monkeypatch, caplog):
    monkeypatch.setattr('app.services.room_daylight.directory', AsyncMock(side_effect=TimeoutError))
    plan = await room_daylight('omm_one', datetime.now(UTC))
    assert plan.city is None
    assert 'Room daylight directory unavailable' in caplog.text
