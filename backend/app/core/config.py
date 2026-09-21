"""RoomBeacon settings; deliberately independent of Argus platform settings."""
import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.getenv("ROOMBEACON_ENV_FILE", os.getenv("ARGUS_ENV_FILE", ".env")),
        env_file_encoding="utf-8", extra="ignore",
    )
    APP_ENV: str = "dev"
    REDIS_URL: str = "redis://127.0.0.1:6379/0"
    FEISHU_APP_ID: str = ""
    FEISHU_APP_SECRET: str = ""
    ROOM_DISPLAY_CHECKIN_URLS: dict[str, str] = Field(default_factory=dict)
    ROOM_DISPLAY_SYNC_SECONDS: int = Field(default=300, ge=120, le=3600)
    ROOM_DISPLAY_CONTROL_TOKEN: str = ""
    ROOM_DISPLAY_CONTROL_TOKEN_SECONDARY: str = ""
    ROOM_DISPLAY_USAGE_ENABLED: bool = False
    ROOM_DISPLAY_USAGE_WRITES_ENABLED: bool = False
    ROOM_DISPLAY_USAGE_RELEASE_ROOM_IDS: set[str] = Field(default_factory=set)
    # Exact room -> readable calendar mapping. Empty keeps the manual pilot behavior.
    ROOM_DISPLAY_USAGE_AUTO_VERIFY_CALENDARS: dict[str, str] = Field(default_factory=dict)


settings = Settings()
