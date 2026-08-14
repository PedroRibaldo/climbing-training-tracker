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
    SETTINGS_TABLE = 'app_settings'


class WhoopMetricsRecord(BaseModel):
    """A single validated row from 'whoop_daily_metrics'."""

    date: dt_date
    recovery_score: Optional[int] = Field(default=None, ge=0, le=100)
    hrv_ms: Optional[float] = Field(default=None, ge=0)
    strain: Optional[float] = Field(default=None, ge=0, le=21)
    resting_hr: Optional[int] = Field(default=None, ge=0)
