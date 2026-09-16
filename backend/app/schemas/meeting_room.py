from datetime import datetime

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


class RoomSchedule(BaseModel):
    room: Room
    events: list[RoomEvent]
    synced_at: datetime
    valid_until: datetime
    titles_available: bool = True
    server_time: datetime | None = None
    daylight: DaylightPlan | None = None
    checkin_qr: str | None = None


class DeviceRequest(BaseModel):
    room_id: str = Field(pattern=r"^omm_[a-zA-Z0-9]+$", max_length=100)
