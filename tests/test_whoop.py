"""
Tests for WhoopMetricsRecord validation in whoop/models.py.

Run with: pytest
"""
from datetime import date

import pytest
from pydantic import ValidationError

from whoop import WhoopMetricsRecord, WhoopClimbingWorkoutRecord


def make_whoop_row(**overrides):
    row = {
        'date': '2026-08-10',
        'recovery_score': 62,
        'hrv_ms': 45.3,
        'strain': 12.8,
        'resting_hr': 54,
    }
    row.update(overrides)
    return row


class TestWhoopMetricsValidation:

    def test_valid_row_parses_correctly(self):
        record = WhoopMetricsRecord.model_validate(make_whoop_row())
        assert record.date == date(2026, 8, 10)
        assert record.recovery_score == 62
        assert record.hrv_ms == 45.3
        assert record.strain == 12.8
        assert record.resting_hr == 54

    def test_missing_optional_fields_default_to_none(self):
        row = make_whoop_row()
        del row['recovery_score'], row['hrv_ms'], row['strain'], row['resting_hr']
        record = WhoopMetricsRecord.model_validate(row)
        assert record.recovery_score is None
        assert record.hrv_ms is None
        assert record.strain is None
        assert record.resting_hr is None

    def test_recovery_score_above_100_is_rejected(self):
        with pytest.raises(ValidationError):
            WhoopMetricsRecord.model_validate(make_whoop_row(recovery_score=150))

    def test_recovery_score_below_zero_is_rejected(self):
        with pytest.raises(ValidationError):
            WhoopMetricsRecord.model_validate(make_whoop_row(recovery_score=-5))

    def test_strain_above_21_is_rejected(self):
        with pytest.raises(ValidationError):
            WhoopMetricsRecord.model_validate(make_whoop_row(strain=25.0))

    def test_strain_below_zero_is_rejected(self):
        with pytest.raises(ValidationError):
            WhoopMetricsRecord.model_validate(make_whoop_row(strain=-1.0))

    def test_hrv_below_zero_is_rejected(self):
        with pytest.raises(ValidationError):
            WhoopMetricsRecord.model_validate(make_whoop_row(hrv_ms=-1.0))

    def test_resting_hr_below_zero_is_rejected(self):
        with pytest.raises(ValidationError):
            WhoopMetricsRecord.model_validate(make_whoop_row(resting_hr=-1))

    def test_missing_date_is_rejected(self):
        row = make_whoop_row()
        del row['date']
        with pytest.raises(ValidationError):
            WhoopMetricsRecord.model_validate(row)


def make_climbing_workout_row(**overrides):
    row = {
        'date': '2026-08-10',
        'duration_min': 95.5,
        'calories': 620,
        'avg_hr': 128,
        'max_hr': 171,
        'zone_0_min': 5.0,
        'zone_1_min': 20.0,
        'zone_2_min': 30.0,
        'zone_3_min': 25.0,
        'zone_4_min': 10.0,
        'zone_5_min': 5.5,
    }
    row.update(overrides)
    return row


class TestWhoopClimbingWorkoutValidation:

    def test_valid_row_parses_correctly(self):
        record = WhoopClimbingWorkoutRecord.model_validate(make_climbing_workout_row())
        assert record.date == date(2026, 8, 10)
        assert record.duration_min == 95.5
        assert record.calories == 620
        assert record.avg_hr == 128
        assert record.max_hr == 171
        assert record.zone_3_min == 25.0

    def test_missing_optional_fields_default_to_none(self):
        record = WhoopClimbingWorkoutRecord.model_validate({'date': '2026-08-10'})
        assert record.duration_min is None
        assert record.calories is None
        assert record.avg_hr is None
        assert record.max_hr is None
        assert record.zone_0_min is None

    def test_negative_duration_is_rejected(self):
        with pytest.raises(ValidationError):
            WhoopClimbingWorkoutRecord.model_validate(make_climbing_workout_row(duration_min=-1.0))

    def test_negative_calories_is_rejected(self):
        with pytest.raises(ValidationError):
            WhoopClimbingWorkoutRecord.model_validate(make_climbing_workout_row(calories=-5))

    def test_negative_max_hr_is_rejected(self):
        with pytest.raises(ValidationError):
            WhoopClimbingWorkoutRecord.model_validate(make_climbing_workout_row(max_hr=-1))

    def test_negative_zone_minutes_is_rejected(self):
        with pytest.raises(ValidationError):
            WhoopClimbingWorkoutRecord.model_validate(make_climbing_workout_row(zone_2_min=-0.5))

    def test_missing_date_is_rejected(self):
        row = make_climbing_workout_row()
        del row['date']
        with pytest.raises(ValidationError):
            WhoopClimbingWorkoutRecord.model_validate(row)
