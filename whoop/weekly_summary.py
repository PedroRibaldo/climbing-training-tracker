"""
Pure computation of this week's average climbing-workout duration/HR from
WHOOP data, used to pre-fill two of the header KPI tiles.
"""

from datetime import date as dt_date
from typing import Optional

import pandas as pd


def compute_weekly_workout_averages(df_whoop_workouts: pd.DataFrame, reference_date: Optional[dt_date] = None) -> dict:
    """Mean duration_min and avg_hr across this calendar week's (Monday-
    start, same definition data_pipeline.compute_kpis uses) rows of
    df_whoop_workouts. Both fields are None if no rows fall in the current
    week. reference_date pins "today" for tests; defaults to the real
    today when not given."""
    if df_whoop_workouts.empty:
        return {'avg_duration_min': None, 'avg_hr': None}

    today = pd.Timestamp(reference_date) if reference_date is not None else pd.Timestamp.today()
    week_start = today.normalize() - pd.Timedelta(days=today.weekday())

    df_week = df_whoop_workouts[df_whoop_workouts['date'] >= week_start]
    if df_week.empty:
        return {'avg_duration_min': None, 'avg_hr': None}

    return {
        'avg_duration_min': float(df_week['duration_min'].mean()),
        'avg_hr': float(df_week['avg_hr'].mean()),
    }
