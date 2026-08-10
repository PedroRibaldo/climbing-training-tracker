"""
Pydantic validation models for the 'profiles' and 'injuries' tables.
"""

from datetime import date as dt_date
from typing import Optional

import pandas as pd
from pydantic import BaseModel, field_validator

from data_pipeline import PipelineConfig, _validate_membership, _require_nonblank_string


class ProfileRecord(BaseModel):
    """A single validated row from 'profiles'."""

    id: str
    role: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None
    current_gym_grade: Optional[str] = None
    current_moonboard_grade: Optional[str] = None

    @field_validator('current_gym_grade', mode='before')
    @classmethod
    def validate_gym_grade(cls, v):
        return _validate_membership(v, PipelineConfig.GYM_MAPPING, 'gym grade')

    @field_validator('current_moonboard_grade', mode='before')
    @classmethod
    def validate_moonboard_grade(cls, v):
        return _validate_membership(v, PipelineConfig.MOONBOARD_MAPPING, 'moonboard grade')


class InjuryRecord(BaseModel):
    """A single validated row from 'injuries'."""

    id: int
    body_part: str
    description: Optional[str] = None
    started_at: dt_date
    resolved_at: Optional[dt_date] = None

    @field_validator('body_part', mode='before')
    @classmethod
    def body_part_required(cls, v):
        return _require_nonblank_string(v, 'Body part')

    @field_validator('started_at', mode='before')
    @classmethod
    def parse_started_at(cls, v):
        parsed = pd.to_datetime(v, errors='coerce')
        if pd.isna(parsed):
            raise ValueError(f'Unparseable date: {v!r}')
        return parsed.date()

    @field_validator('resolved_at', mode='before')
    @classmethod
    def parse_resolved_at(cls, v):
        if v is None:
            return None
        parsed = pd.to_datetime(v, errors='coerce')
        return None if pd.isna(parsed) else parsed.date()
