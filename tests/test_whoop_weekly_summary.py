"""
Tests for compute_weekly_workout_averages() in whoop/weekly_summary.py.

Run with: pytest
"""
from datetime import date

import pandas as pd

from whoop import compute_weekly_workout_averages


def make_workouts_df(rows):
    df = pd.DataFrame(rows)
    if not df.empty:
        df['date'] = pd.to_datetime(df['date'])
    return df


class TestComputeWeeklyWorkoutAverages:

    def test_empty_dataframe_returns_none_for_both(self):
        result = compute_weekly_workout_averages(pd.DataFrame(), reference_date=date(2026, 8, 21))
        assert result == {'avg_duration_min': None, 'avg_hr': None}

    def test_row_inside_current_week_is_included(self):
        # 2026-08-21 is a Friday; that week starts Monday 2026-08-17
        df = make_workouts_df([{'date': '2026-08-19', 'duration_min': 90.0, 'avg_hr': 130}])
        result = compute_weekly_workout_averages(df, reference_date=date(2026, 8, 21))
        assert result == {'avg_duration_min': 90.0, 'avg_hr': 130.0}

    def test_row_from_previous_week_is_excluded(self):
        df = make_workouts_df([{'date': '2026-08-14', 'duration_min': 90.0, 'avg_hr': 130}])
        result = compute_weekly_workout_averages(df, reference_date=date(2026, 8, 21))
        assert result == {'avg_duration_min': None, 'avg_hr': None}

    def test_multiple_rows_this_week_are_averaged(self):
        df = make_workouts_df([
            {'date': '2026-08-17', 'duration_min': 60.0, 'avg_hr': 120},
            {'date': '2026-08-19', 'duration_min': 120.0, 'avg_hr': 140},
        ])
        result = compute_weekly_workout_averages(df, reference_date=date(2026, 8, 21))
        assert result == {'avg_duration_min': 90.0, 'avg_hr': 130.0}

    def test_monday_of_the_week_is_included(self):
        df = make_workouts_df([{'date': '2026-08-17', 'duration_min': 45.0, 'avg_hr': 110}])
        result = compute_weekly_workout_averages(df, reference_date=date(2026, 8, 21))
        assert result == {'avg_duration_min': 45.0, 'avg_hr': 110.0}
