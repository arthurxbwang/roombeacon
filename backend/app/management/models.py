"""Bounded V6 wire protocol. Node fields reserve future centrally approved routing."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Interface(StrictModel):
    name: str = Field(max_length=32)
    mac: str = Field(default='', max_length=32)
    addresses: list[str] = Field(default_factory=list, max_length=8)


class Metadata(StrictModel):
    model: str = Field(default='', max_length=100)
    serial: str = Field(default='', max_length=100)
    android: str = Field(default='', max_length=40)
    apk: str = Field(default='', max_length=40)
    network: Literal['wifi', 'ethernet', 'other', 'offline'] = 'offline'
    interfaces: list[Interface] = Field(default_factory=list, max_length=12)
    serial_source: str = Field(default='', max_length=60)
    light_supported: bool = False


class Sync(StrictModel):
    protocol: Literal[1] = 1
    metadata: Metadata
    reported_revision: int = Field(default=0, ge=0, le=2147483647)
    error: str = Field(default='', max_length=160)


class DeviceConfig(StrictModel):
    version: Literal['v4', 'v5', 'v6'] = 'v6'
    portrait: bool = False
    room_light: bool = True
    node_id: Literal['central'] = 'central'
    reload: int = Field(default=0, ge=0, le=2147483647)


class Configure(StrictModel):
    expected_revision: int = Field(ge=1)
    room_id: str = Field(default='', pattern=r'^(omm_[A-Za-z0-9]{1,96})?$', max_length=100)
    status: Literal['active', 'pending', 'revoked']
    config: DeviceConfig


class Revision(StrictModel):
    expected_revision: int = Field(ge=1)


class Rollback(Revision):
    revision: int = Field(ge=1)


class Role(StrictModel):
    role: Literal['admin', 'viewer', 'disabled']


class Template(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    config: DeviceConfig


class Batch(StrictModel):
    devices: dict[str, int] = Field(min_length=1, max_length=100)
    config: DeviceConfig
