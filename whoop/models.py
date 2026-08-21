"""
Pydantic validation model for WHOOP daily metrics, plus the table-name
constants the rest of the whoop package depends on.
"""

from datetime import date as dt_date
from typing import Optional

from pydantic import BaseModel, Field


class WhoopConfig:
    """Central place for the Supabase table names this package touches."""

    TOKENS_TABLE = 'whoop_tokens'
    METRICS_TABLE = 'whoop_daily_metrics'
    WORKOUTS_TABLE = 'whoop_climbing_workouts'
    SETTINGS_TABLE = 'app_settings'


class WhoopMetricsRecord(BaseModel):
    """A single validated row from 'whoop_daily_metrics'."""

    date: dt_date
    recovery_score: Optional[int] = Field(default=None, ge=0, le=100)
    hrv_ms: Optional[float] = Field(default=None, ge=0)
    strain: Optional[float] = Field(default=None, ge=0, le=21)
    resting_hr: Optional[int] = Field(default=None, ge=0)


class WhoopClimbingWorkoutRecord(BaseModel):
    """A single validated row from 'whoop_climbing_workouts' - one day's
    combined climbing-workout stats. Same-day WHOOP recordings are already
    summed into one row by scripts/whoop_sync.py before this ever gets
    read back, so there's exactly one row per date, not per workout."""

    date: dt_date
    duration_min: Optional[float] = Field(default=None, ge=0)
    calories: Optional[int] = Field(default=None, ge=0)
    avg_hr: Optional[int] = Field(default=None, ge=0)
    max_hr: Optional[int] = Field(default=None, ge=0)
    zone_0_min: Optional[float] = Field(default=None, ge=0)
    zone_1_min: Optional[float] = Field(default=None, ge=0)
    zone_2_min: Optional[float] = Field(default=None, ge=0)
    zone_3_min: Optional[float] = Field(default=None, ge=0)
    zone_4_min: Optional[float] = Field(default=None, ge=0)
    zone_5_min: Optional[float] = Field(default=None, ge=0)
