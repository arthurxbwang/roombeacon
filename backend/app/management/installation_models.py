"""Strict first-install contracts; never carry a shell command or device credential."""
from ipaddress import IPv4Address, IPv4Network
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Manifest(Contract):
    package: Literal['com.roombeacon.shell']
    version_code: int = Field(ge=1, le=2100000000)
    version_name: str = Field(min_length=1, max_length=100)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    certificate_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    size: int = Field(ge=1, le=64 * 1024 * 1024)
    models: list[str] = Field(min_length=1, max_length=20)

    @field_validator('models')
    @classmethod
    def models_valid(cls, values):
        if any(not v.strip() or len(v) > 100 for v in values):
            raise ValueError('请指定适用的准确型号')
        return sorted({v.strip() for v in values})


class Executor(Contract):
    name: str = Field(min_length=1, max_length=80)


class Target(Contract):
    ip: IPv4Address
    port: int = Field(default=5555, ge=1, le=65535)
    serial: str = Field(pattern=r'^[A-Za-z0-9._-]{1,100}$')

    @field_validator('ip')
    @classmethod
    def lan_only(cls, value):
        if not any(value in IPv4Network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')):
            raise ValueError('首装只接受明确登记的内网 IPv4 地址')
        return value


class Batch(Contract):
    request_id: str = Field(pattern=r'^[a-f0-9-]{32,36}$')
    executor_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    release_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    targets: list[Target] = Field(min_length=1, max_length=100)


class Revision(Contract):
    revision: int = Field(ge=1)


class Retry(Revision):
    previous_executor_stopped: Literal[True]


class Association(Revision):
    code: str = Field(pattern=r'^[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{6}$')
    physical_identity_confirmed: Literal[True]


class Acceptance(Revision):
    device_revision: int = Field(ge=1)
    screen_and_fresh_data: Literal[True]
    lighting: Literal[True]
    cold_boot: Literal[True]
    adb_closed: Literal[True]
    poe_recovery_adb_stays_closed: Literal[True]
    location: str = Field(min_length=1, max_length=160)
    switch_port: str = Field(min_length=1, max_length=160)


class Lease(Contract):
    lease: str = Field(pattern=r'^[A-Za-z0-9_-]{43}$')


class Report(Lease):
    result: Literal['installed', 'already_installed', 'failed']
    error: Literal['', 'apk_invalid', 'connection_failed', 'identity_mismatch', 'model_mismatch',
                   'existing_apk', 'install_failed', 'launch_failed', 'verification_failed', 'local_failure'] = ''
