"""V5 policy and command contracts, separate from the legacy display API."""
import hashlib
import json
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

ROOM_PATTERN = r'^omm_[A-Za-z0-9]{1,96}$'


class UsagePolicy(BaseModel):
    owner: Literal['official', 'v5'] = 'official'
    mode: Literal['off', 'observe', 'auto'] = 'off'
    early_minutes: int = Field(default=5, ge=1, le=30)
    grace_minutes: int = Field(default=10, ge=1, le=30)
    release_delay_seconds: int = Field(default=60, ge=30, le=300)
    native_policy_cleared: bool = False
    release_verified: bool = False
    revision: str = ''


class Occurrence(BaseModel):
    uid: str = Field(min_length=1, max_length=256)
    original_time: int = Field(ge=0)
    start_time: datetime
    end_time: datetime

    def identity(self, room_id: str) -> str:
        parts = [room_id, self.uid, self.original_time,
                 self.start_time.timestamp(), self.end_time.timestamp()]
        return hashlib.sha256(json.dumps(parts).encode()).hexdigest()


class UsageCommand(BaseModel):
    occurrence_id: str = Field(pattern=r'^[a-f0-9]{64}$')
    policy_revision: str


class TerminalCommand(UsageCommand):
    session_id: str = Field(pattern=r'^[a-f0-9]{32}$')


class UsageHeartbeat(BaseModel):
    protocol: Literal[2]
    session_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    occurrence_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    policy_revision: str
    operation_state: Literal['ready', 'submitting', 'uncertain']
    challenge_id: str | None = Field(default=None, pattern=r'^[a-f0-9]{32}$')
    monitored_occurrence_ids: list[Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]] = Field(default_factory=list, max_length=64)


class VerifiedOccurrence(UsageCommand):
    non_recurring_verified: Literal[True]


class PauseCommand(BaseModel):
    paused: bool
