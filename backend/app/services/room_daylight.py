"""Offline astronomical daylight, using configured city centres (not weather data)."""
import asyncio
import logging
from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from astral import Observer
from astral.sun import elevation, sunrise, sunset
from httpx import HTTPError
from redis.exceptions import RedisError

from ..core.exceptions import AppError
from ..schemas.meeting_room import DaylightPlan, DaylightWindow
from .room_display_directory import directory

logger = logging.getLogger(__name__)

# Aliases match Feishu location hierarchy only, never meeting titles or room names.
CITIES = [
    ("北京", ("北京", "Beijing"), 39.90, 116.40, "Asia/Shanghai"),
    ("上海", ("上海", "Shanghai"), 31.23, 121.47, "Asia/Shanghai"),
    ("沈阳", ("沈阳",), 41.81, 123.43, "Asia/Shanghai"),
    ("深圳", ("深圳",), 22.54, 114.06, "Asia/Shanghai"),
    ("南京", ("南京",), 32.06, 118.80, "Asia/Shanghai"),
    ("合肥", ("合肥",), 31.82, 117.23, "Asia/Shanghai"),
    ("大连", ("大连",), 38.91, 121.61, "Asia/Shanghai"),
    ("天津", ("天津",), 39.08, 117.20, "Asia/Shanghai"),
    ("广州", ("广州",), 23.13, 113.26, "Asia/Shanghai"),
    ("成都", ("成都",), 30.57, 104.07, "Asia/Shanghai"),
    ("无锡", ("无锡",), 31.49, 120.31, "Asia/Shanghai"),
    ("杭州", ("杭州",), 30.27, 120.15, "Asia/Shanghai"),
    ("武汉", ("武汉",), 30.59, 114.31, "Asia/Shanghai"),
    ("苏州", ("苏州",), 31.30, 120.59, "Asia/Shanghai"),
    ("西安", ("西安",), 34.34, 108.94, "Asia/Shanghai"),
    ("重庆", ("重庆",), 29.56, 106.55, "Asia/Shanghai"),
    ("长春", ("长春",), 43.82, 125.32, "Asia/Shanghai"),
    ("青岛", ("青岛",), 36.07, 120.38, "Asia/Shanghai"),
    ("台北", ("台北", "臺北", "南港", "Taipei"), 25.03, 121.57, "Asia/Taipei"),
    ("东京", ("东京", "Tokyo"), 35.68, 139.69, "Asia/Tokyo"),
    ("名古屋", ("名古屋", "Nagoya"), 35.18, 136.91, "Asia/Tokyo"),
    ("海得拉巴", ("Hyderabad",), 17.39, 78.49, "Asia/Kolkata"),
    ("纽伦堡", ("Nürnberg", "Nuremberg"), 49.45, 11.08, "Europe/Berlin"),
    ("多伦多", ("多伦多", "Toronto"), 43.65, -79.38, "America/Toronto"),
    ("安科纳", ("ANCONA", "安科纳"), 43.62, 13.52, "Europe/Rome"),
    ("巴塞罗那", ("巴塞罗那", "Barcelona"), 41.39, 2.17, "Europe/Madrid"),
]


@lru_cache(maxsize=512)
def city_plan(city: str, latitude: float, longitude: float, timezone: str, day: date) -> DaylightPlan:
    observer = Observer(latitude, longitude)
    zone = ZoneInfo(timezone)
    windows = []
    for offset in [-1, 0, 1, 2]:
        target = day + timedelta(days=offset)
        try:
            start = sunrise(observer, date=target, tzinfo=zone)
            end = sunset(observer, date=target, tzinfo=zone)
        except ValueError:
            # Polar day/night: an absent horizon crossing is an expected solar condition.
            noon = datetime.combine(target, time(12), zone)
            if elevation(observer, noon) <= 0:
                continue
            start = datetime.combine(target, time(), zone)
            end = datetime.combine(target + timedelta(days=1), time(), zone)
        windows.append(DaylightWindow(start=start, end=end))
    return DaylightPlan(city=city, timezone=timezone, windows=windows,
                        valid_until=datetime.combine(day + timedelta(days=3), time(), zone))


def plan_for_location(location: str, now: datetime) -> DaylightPlan:
    folded = location.casefold()
    for city, aliases, latitude, longitude, timezone in CITIES:
        if any(alias.casefold() in folded for alias in aliases):
            return city_plan(city, latitude, longitude, timezone, now.astimezone(ZoneInfo(timezone)).date())
    return DaylightPlan(city=None, timezone="Asia/Shanghai", windows=[], valid_until=now)


async def room_daylight(room_id: str, now: datetime) -> DaylightPlan:
    try:
        rooms = await asyncio.wait_for(directory(), timeout=5)
    except (AppError, HTTPError, RedisError, TimeoutError, ValueError, KeyError):
        logger.warning("Room daylight directory unavailable", exc_info=True)
        return plan_for_location("", now)
    location = next((room["location"] for room in rooms if room["room_id"] == room_id), "")
    return plan_for_location(location, now.astimezone(UTC))
