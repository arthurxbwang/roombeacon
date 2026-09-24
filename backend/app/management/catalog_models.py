"""Separate installation and presentation contracts; no credentials or runtime grants."""
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .models import StrictModel


class Pins(StrictModel):
    red: Literal[147, 148, 154] = 148
    green: Literal[147, 148, 154] = 154
    blue: Literal[147, 148, 154] = 147

    @model_validator(mode='after')
    def distinct(self):
        if len({self.red, self.green, self.blue}) != 3:
            raise ValueError('RGB 通道必须使用不同 GPIO')
        return self


class HardwareSpec(StrictModel):
    manufacturer: str = Field(default='', max_length=80)
    model: str = Field(default='', max_length=100)
    firmware: str = Field(default='', max_length=160)
    device_profile: Literal['auto', 'generic', 'bx68', 'rk3568_r'] = 'generic'
    portrait: bool = False
    width: int = Field(default=0, ge=0, le=8192)
    height: int = Field(default=0, ge=0, le=8192)
    room_light: bool = False
    pins: Pins = Field(default_factory=Pins)
    active_level: Literal[0, 1] = 0
    notes: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def dimensions(self):
        if bool(self.width) != bool(self.height):
            raise ValueError('分辨率宽高需同时填写')
        return self


class Rules(StrictModel):
    owner: Literal['official', 'v5'] = 'official'
    mode: Literal['off', 'observe', 'auto'] = 'off'
    early_minutes: int = Field(default=5, ge=1, le=30)
    grace_minutes: int = Field(default=10, ge=1, le=30)
    release_delay_seconds: int = Field(default=60, ge=30, le=300)

    @model_validator(mode='after')
    def official_off(self):
        if self.owner == 'official' and self.mode != 'off':
            raise ValueError('官方签到方案必须关闭 RoomBeacon 释放')
        return self


class SoftwareSpec(StrictModel):
    layout: Literal['standard', 'compact'] = 'standard'
    orientation: Literal['any', 'landscape', 'portrait'] = 'any'
    min_width: int = Field(default=0, ge=0, le=8192)
    min_height: int = Field(default=0, ge=0, le=8192)
    theme_mode: Literal['auto', 'light', 'dark'] = 'auto'
    language: Literal['zh-CN', 'en'] = 'zh-CN'
    background_day: str = Field(default='', pattern=r'^(|[a-f0-9]{64})$')
    background_night: str = Field(default='', pattern=r'^(|[a-f0-9]{64})$')
    background_fit: Literal['cover', 'contain'] = 'cover'
    rules: Rules = Field(default_factory=Rules)


class CatalogDraft(StrictModel):
    kind: Literal['hardware', 'software']
    name: str = Field(min_length=1, max_length=80)
    spec: dict = Field(default_factory=dict)
    expected_revision: int = Field(default=0, ge=0)

    @field_validator('name')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('名称不能为空')
        return value.strip()

    @model_validator(mode='after')
    def valid_spec(self):
        schema = HardwareSpec if self.kind == 'hardware' else SoftwareSpec
        self.spec = schema.model_validate(self.spec).model_dump()
        return self


class HardwareTest(StrictModel):
    version: int = Field(ge=1)
    device_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    result: Literal['passed', 'failed']
    notes: str = Field(min_length=5, max_length=2000)
    colors: bool
    off: bool
    orientation: bool


class DeployRequest(StrictModel):
    device_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    expected_revision: int = Field(ge=1)
    room_id: str = Field(pattern=r'^omm_[A-Za-z0-9]{1,96}$')
    hardware_id: str = Field(min_length=1, max_length=64)
    hardware_version: int = Field(ge=1)
    software_id: str = Field(min_length=1, max_length=64)
    software_version: int = Field(ge=1)
    expected_room_revision: int = Field(ge=0)
    replace_room_software: bool = False
    confirm_model_mismatch: bool = False
    control_device: bool = True


class ImageUpload(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    data: str = Field(max_length=4_000_000)


class Qualification(StrictModel):
    expected_revision: str = Field(max_length=64)
    native_policy_cleared: bool
    release_verified: bool


class DeviceStatus(StrictModel):
    expected_revision: int = Field(ge=1)
    status: Literal['pending', 'revoked']


class DeploymentBatch(StrictModel):
    devices: dict[str, int] = Field(min_length=1, max_length=100)
    room_revisions: dict[str, int] = Field(max_length=100)
    hardware_id: str = Field(min_length=1, max_length=64)
    hardware_version: int = Field(ge=1)
    software_id: str = Field(min_length=1, max_length=64)
    software_version: int = Field(ge=1)
    replace_room_software: bool = False
    confirm_model_mismatch: bool = False
