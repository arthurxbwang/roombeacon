from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class Room(BaseModel):
    room_id: str
    name: str
    capacity: int = 0
    enabled: bool = True


class RoomEvent(BaseModel):
    uid: str
    original_time: int = 0
    start_time: datetime
    end_time: datetime
    organizer: str | None = None
    summary: str | None = None


class DaylightWindow(BaseModel):
    start: datetime
    end: datetime


class DaylightPlan(BaseModel):
    city: str | None
    timezone: str
    windows: list[DaylightWindow]
    valid_until: datetime


class DisplayPreferences(BaseModel):
    theme_mode: Literal["auto", "light"] = "auto"
    language: Literal["zh-CN", "en"] = "zh-CN"


class RoomSchedule(BaseModel):
    display_preferences: DisplayPreferences | None = None
    room: Room
    events: list[RoomEvent]
    synced_at: datetime
    valid_until: datetime
    titles_available: bool = True
    server_time: datetime | None = None
    daylight: DaylightPlan | None = None
    checkin_qr: str | None = None
    usage_owner: Literal['official', 'v5'] = 'official'


class DeviceRequest(BaseModel):
    room_id: str = Field(pattern=r"^omm_[a-zA-Z0-9]+$", max_length=100)
