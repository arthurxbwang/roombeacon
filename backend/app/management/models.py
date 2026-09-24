"""Bounded V6 wire protocol. Node fields reserve future centrally approved routing."""
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    field_validator,
    model_validator,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Interface(StrictModel):
    name: str = Field(max_length=32)
    mac: str = Field(default='', max_length=32)
    addresses: list[str] = Field(default_factory=list, max_length=8)


class Screen(StrictModel):
    pixel_width: int = Field(default=0, ge=0, le=8192)
    pixel_height: int = Field(default=0, ge=0, le=8192)
    viewport_width: float = Field(default=0, ge=0, le=8192, allow_inf_nan=False)
    viewport_height: float = Field(default=0, ge=0, le=8192, allow_inf_nan=False)
    density: float = Field(default=0, ge=0, le=16, allow_inf_nan=False)
    dpr: float = Field(default=0, ge=0, le=16, allow_inf_nan=False)


class Metadata(StrictModel):
    model: str = Field(default='', max_length=100)
    serial: str = Field(default='', max_length=100)
    android: str = Field(default='', max_length=40)
    apk: str = Field(default='', max_length=40)
    network: Literal['wifi', 'ethernet', 'other', 'offline'] = 'offline'
    interfaces: list[Interface] = Field(default_factory=list, max_length=12)
    serial_source: str = Field(default='', max_length=60)
    light_supported: bool = False
    firmware: str = Field(default="", max_length=160)
    config_schema: Literal[1, 2, 3] = 1
    screen: Screen = Field(default_factory=Screen)


class Sync(StrictModel):
    protocol: Literal[1] = 1
    metadata: Metadata
    reported_revision: int = Field(default=0, ge=0, le=2147483647)
    error: str = Field(default='', max_length=160)


class DeviceConfig(StrictModel):
    version: Literal['v4', 'v5', 'v6'] = 'v6'
    theme_mode: Literal['auto', 'light'] = 'auto'
    language: Literal['zh-CN', 'en'] = 'zh-CN'
    device_profile: Literal['auto', 'generic', 'bx68', 'rk3568_r'] = 'auto'
    portrait: bool = False
    room_light: bool = True
    node_id: Literal['central'] = 'central'
    reload: int = Field(default=0, ge=0, le=2147483647)

    @model_validator(mode="after")
    def safe_light(self):
        if self.device_profile == "generic" and self.room_light:
            raise ValueError("通用屏幕不支持灯控，请关闭同步侧边灯")
        return self


class TemplateSelection(StrictModel):
    template_id: str = Field(default='', max_length=32)
    template_revision: int = Field(default=0, ge=0)


class Configure(TemplateSelection):
    confirm_model_mismatch: StrictBool = False
    expected_revision: int = Field(ge=1)
    room_id: str = Field(default='', pattern=r'^(omm_[A-Za-z0-9]{1,96})?$', max_length=100)
    status: Literal['active', 'pending', 'revoked']
    config: DeviceConfig


class Revision(StrictModel):
    expected_revision: int = Field(ge=1)


class Rollback(Revision):
    confirm_model_mismatch: StrictBool = False
    revision: int = Field(ge=1)


class Role(StrictModel):
    role: Literal['admin', 'viewer', 'disabled']


class Template(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    config: DeviceConfig

    @field_validator('name')
    @classmethod
    def nonblank_name(cls, value):
        if not value.strip():
            raise ValueError('模板名称不能为空')
        return value.strip()


class EditTemplate(Template):
    expected_revision: int = Field(ge=1)


class Batch(TemplateSelection):
    confirm_model_mismatch: StrictBool = False
    devices: dict[str, int] = Field(min_length=1, max_length=100)
    config: DeviceConfig
