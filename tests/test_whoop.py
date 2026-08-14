"""
Tests for WhoopMetricsRecord validation in whoop/models.py.

Run with: pytest
"""
from datetime import date

import pytest
from pydantic import ValidationError

from whoop import WhoopMetricsRecord


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
