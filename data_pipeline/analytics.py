"""
Pure analytics functions over already-cleaned DataFrames.
"""

import pandas as pd
import streamlit as st


@st.cache_data
def compute_acwr(df_past: pd.DataFrame, acute_window: int = 7, chronic_window: int = 28) -> pd.DataFrame:
    """Acute:Chronic Workload Ratio - a metric of training
    load trend, used as an injury-risk / readiness signal

    Daily load is the sum of Effort Scale across all sessions on that day.
    Days with no session count as 0 load. `acute` is the rolling mean load
    over the last `acute_window` days (short-term fatigue); `chronic` is
    the rolling mean over the last `chronic_window` days (longer-term
    baseline). ACWR = acute / chronic - commonly cited "sweet spot" in the
    sports-science literature this metric comes from is roughly 0.8-1.3,
    with values above ~1.5 associated with elevated injury risk.

    Returns a DataFrame indexed by date with columns:
    daily_load, acute_load, chronic_load, acwr.
    """
    if df_past.empty:
        return pd.DataFrame(columns=['daily_load', 'acute_load', 'chronic_load', 'acwr'])

    sessions_with_effort = df_past.dropna(subset=['effort'])
    if sessions_with_effort.empty:
        return pd.DataFrame(columns=['daily_load', 'acute_load', 'chronic_load', 'acwr'])

    daily_load = sessions_with_effort.groupby(
        sessions_with_effort['date'].dt.normalize()
    )['effort'].sum()

    full_range = pd.date_range(daily_load.index.min(), daily_load.index.max(), freq='D')
    daily_load = daily_load.reindex(full_range, fill_value=0)
    daily_load.index.name = 'date'

    acute_load = daily_load.rolling(window=acute_window, min_periods=1).mean()
    chronic_load = daily_load.rolling(window=chronic_window, min_periods=1).mean()
    acwr = (acute_load / chronic_load).where(chronic_load > 0)

    return pd.DataFrame({
        'daily_load': daily_load,
        'acute_load': acute_load,
        'chronic_load': chronic_load,
        'acwr': acwr,
    })


def compute_kpis(df_past: pd.DataFrame) -> dict:
    """Snapshot KPIs for the top-of-page summary strip.

    Returns a dict with:
        streak: consecutive days up to the most recently logged day that
            have a non-Rest session (0 if none)
        sessions_this_week: non-Rest sessions logged since the most
            recent Monday
        acwr_current / acwr_delta: latest ACWR value and its change from
            the previous day with a computable ACWR (None if not enough
            training history yet)
        days_since_last: days since the most recently logged session of
            any category (None if nothing has been logged)
    """
    empty_result = {
        'streak': 0, 'sessions_this_week': 0,
        'acwr_current': None, 'acwr_delta': None, 'days_since_last': None,
    }

    dated = df_past.dropna(subset=['date']) if not df_past.empty else df_past
    if dated.empty:
        return empty_result

    today = pd.to_datetime('today').normalize()
    last_date = dated['date'].max().normalize()

    week_start = today - pd.Timedelta(days=today.weekday())
    sessions_this_week = dated[
        (dated['date'] >= week_start) & (dated['category'] != 'Rest')
    ].shape[0]

    non_rest_days = set(dated[dated['category'] != 'Rest']['date'].dt.normalize())
    streak = 0
    cursor = last_date
    while cursor in non_rest_days:
        streak += 1
        cursor -= pd.Timedelta(days=1)

    acwr_df = compute_acwr(df_past)
    acwr_series = acwr_df['acwr'].dropna() if not acwr_df.empty else pd.Series(dtype=float)
    acwr_current = float(acwr_series.iloc[-1]) if not acwr_series.empty else None
    acwr_delta = (
        float(acwr_series.iloc[-1] - acwr_series.iloc[-2])
        if len(acwr_series) >= 2 else None
    )

    return {
        'streak': streak,
        'sessions_this_week': int(sessions_this_week),
        'acwr_current': acwr_current,
        'acwr_delta': acwr_delta,
        'days_since_last': int((today - last_date).days),
    }


def compute_grade_pyramid(df: pd.DataFrame, grade_col: str, grade_mapping: dict) -> pd.Series:
    """Session counts per grade, ordered easiest -> hardest per
    grade_mapping's key order, with untouched grades dropped.
    value_counts() alone sorts by frequency, not grade order - the
    reindex here is what actually produces the pyramid shape."""
    if df.empty:
        return pd.Series(dtype=int)
    return df[grade_col].value_counts().reindex(grade_mapping.keys()).dropna().astype(int)
