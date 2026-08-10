"""
Pydantic validation models for the 'gyms' and 'gym_memberships' tables.
"""

from datetime import datetime
from typing import Literal, Optional

import pandas as pd
from pydantic import BaseModel, field_validator

ALL_ROLES = ['climber', 'worker', 'setter', 'trainer', 'competitor', 'admin']
Role = Literal['climber', 'worker', 'setter', 'trainer', 'competitor', 'admin']


def _parse_joined_at(v):
    if v is None:
        return None
    parsed = pd.to_datetime(v, errors='coerce')
    return None if pd.isna(parsed) else parsed.to_pydatetime()


class GymRecord(BaseModel):
    """A single validated row from 'gyms'."""

    id: int
    name: str
    location: Optional[str] = None


class GymMembershipRecord(BaseModel):
    """The caller's own membership row, joined with the gym's name -
    what get_user_memberships() returns."""

    id: int
    gym_id: int
    gym_name: str
    role: Role
    joined_at: Optional[datetime] = None

    @field_validator('joined_at', mode='before')
    @classmethod
    def parse_joined_at(cls, v):
        return _parse_joined_at(v)


class GymMemberRecord(BaseModel):
    """A member row on a gym's roster, joined with their display name -
    what list_gym_members() returns, for the admin-only 'Manage members'
    screen."""

    id: int
    gym_id: int
    user_id: str
    display_name: Optional[str] = None
    role: Role
    joined_at: Optional[datetime] = None

    @field_validator('joined_at', mode='before')
    @classmethod
    def parse_joined_at(cls, v):
        return _parse_joined_at(v)


def is_elevated(role: str) -> bool:
    """True for any role other than the default 'climber'. Pure and
    I/O-free so the future bouldering-problems feature can reuse it for
    creator/elevated-role permission checks without importing Supabase
    machinery."""
    return role != 'climber'
