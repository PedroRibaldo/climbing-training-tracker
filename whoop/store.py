"""
Supabase persistence for WHOOP daily metrics and the app-wide settings
flag that gates whether WHOOP data is fetched/displayed at all.
"""

from datetime import date as dt_date
from typing import Optional

import streamlit as st
from pydantic import ValidationError

from data_pipeline import _get_supabase_client
from .models import WhoopConfig, WhoopMetricsRecord, WhoopClimbingWorkoutRecord


def get_daily_metrics(start_date: Optional[dt_date] = None, end_date: Optional[dt_date] = None) -> list[dict]:
    """WHOOP metrics rows, optionally bounded to [start_date, end_date],
    sorted by date. Invalid rows are skipped with a warning rather than
    blanking the whole result."""
    client = _get_supabase_client()
    query = client.table(WhoopConfig.METRICS_TABLE).select('*')
    if start_date is not None:
        query = query.gte('date', start_date.isoformat())
    if end_date is not None:
        query = query.lte('date', end_date.isoformat())
    response = query.order('date').execute()

    valid = []
    for row in response.data:
        try:
            valid.append(WhoopMetricsRecord.model_validate(row).model_dump())
        except ValidationError as exc:
            st.warning(f"A WHOOP metrics row for {row.get('date', '?')} had invalid data and was skipped: {exc}")
    return valid


def get_climbing_workouts(start_date: Optional[dt_date] = None, end_date: Optional[dt_date] = None) -> list[dict]:
    """WHOOP climbing-workout rows (one per date, already combined by
    scripts/whoop_sync.py), optionally bounded to [start_date, end_date],
    sorted by date. Invalid rows are skipped with a warning rather than
    blanking the whole result."""
    client = _get_supabase_client()
    query = client.table(WhoopConfig.WORKOUTS_TABLE).select('*')
    if start_date is not None:
        query = query.gte('date', start_date.isoformat())
    if end_date is not None:
        query = query.lte('date', end_date.isoformat())
    response = query.order('date').execute()

    valid = []
    for row in response.data:
        try:
            valid.append(WhoopClimbingWorkoutRecord.model_validate(row).model_dump())
        except ValidationError as exc:
            st.warning(f"A WHOOP climbing workout row for {row.get('date', '?')} had invalid data and was skipped: {exc}")
    return valid


def get_latest_metrics() -> Optional[dict]:
    """Most recent WHOOP metrics row, or None if none exist yet."""
    client = _get_supabase_client()
    response = (
        client.table(WhoopConfig.METRICS_TABLE)
        .select('*')
        .order('date', desc=True)
        .limit(1)
        .execute()
    )
    if not response.data:
        return None
    try:
        return WhoopMetricsRecord.model_validate(response.data[0]).model_dump()
    except ValidationError as exc:
        st.warning(f"The latest WHOOP metrics row had invalid data and was ignored: {exc}")
        return None


def is_enabled() -> bool:
    """Whether the WHOOP toggle is on. Fails closed (False) if the
    settings row is somehow missing."""
    client = _get_supabase_client()
    response = client.table(WhoopConfig.SETTINGS_TABLE).select('whoop_enabled').limit(1).execute()
    if not response.data:
        return False
    return bool(response.data[0]['whoop_enabled'])


def set_enabled(value: bool) -> bool:
    """Flip the WHOOP toggle."""
    client = _get_supabase_client()
    try:
        client.table(WhoopConfig.SETTINGS_TABLE).update({'whoop_enabled': value}).eq('id', True).execute()
    except Exception as exc:
        st.error(f"Couldn't update the WHOOP toggle: {exc}")
        return False
    return True
