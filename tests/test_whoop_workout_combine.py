"""
Tests for the pure WHOOP workout transforms in scripts/whoop_workout_combine.py.

Deliberately dependency-free (stdlib only) so these run without installing
requests, which is a script-only dependency (scripts/requirements-whoop.txt)
not present in the main dev environment.

Run with: pytest
"""
import pytest

from scripts.whoop_workout_combine import normalize_workout, combine_climbing_workouts


def make_raw_workout(**overrides):
    row = {
        'start': '2026-08-10T14:00:00.000Z',
        'end': '2026-08-10T15:30:00.000Z',
        'sport_name': 'Rock Climbing',
        'score_state': 'SCORED',
        'score': {
            'kilojoule': 2500.0,
            'average_heart_rate': 130,
            'max_heart_rate': 175,
            'zone_duration': {
                'zone_zero_milli': 300000,
                'zone_one_milli': 1200000,
                'zone_two_milli': 1800000,
                'zone_three_milli': 1500000,
                'zone_four_milli': 600000,
                'zone_five_milli': 0,
            },
        },
    }
    row.update(overrides)
    return row


def make_normalized(**overrides):
    row = {
        'duration_min': 60.0,
        'calories': 400.0,
        'average_heart_rate': 130,
        'max_heart_rate': 170,
        'zone_0_min': 5.0, 'zone_1_min': 10.0, 'zone_2_min': 15.0,
        'zone_3_min': 20.0, 'zone_4_min': 8.0, 'zone_5_min': 2.0,
    }
    row.update(overrides)
    return row


class TestNormalizeWorkout:

    def test_computes_duration_from_start_and_end(self):
        assert normalize_workout(make_raw_workout())['duration_min'] == 90.0

    def test_converts_kilojoule_to_calories(self):
        assert normalize_workout(make_raw_workout())['calories'] == pytest.approx(597.5, abs=0.1)

    def test_extracts_heart_rate_fields(self):
        normalized = normalize_workout(make_raw_workout())
        assert normalized['average_heart_rate'] == 130
        assert normalized['max_heart_rate'] == 175

    def test_converts_zone_milliseconds_to_minutes(self):
        normalized = normalize_workout(make_raw_workout())
        assert normalized['zone_0_min'] == 5.0
        assert normalized['zone_1_min'] == 20.0
        assert normalized['zone_2_min'] == 30.0
        assert normalized['zone_3_min'] == 25.0
        assert normalized['zone_4_min'] == 10.0
        assert normalized['zone_5_min'] == 0.0

    def test_missing_score_fields_default_to_zero(self):
        normalized = normalize_workout(make_raw_workout(score={}))
        assert normalized['calories'] == 0.0
        assert normalized['average_heart_rate'] == 0
        assert normalized['max_heart_rate'] == 0
        assert normalized['zone_0_min'] == 0.0


class TestCombineClimbingWorkouts:

    def test_empty_list_returns_none(self):
        assert combine_climbing_workouts([]) is None

    def test_single_workout_passes_through(self):
        combined = combine_climbing_workouts([make_normalized()])
        assert combined['duration_min'] == 60.0
        assert combined['calories'] == 400
        assert combined['avg_hr'] == 130
        assert combined['max_hr'] == 170
        assert combined['zone_3_min'] == 20.0

    def test_two_workouts_sum_duration_calories_and_zones(self):
        combined = combine_climbing_workouts([
            make_normalized(duration_min=60.0, calories=400.0, zone_1_min=10.0),
            make_normalized(duration_min=30.0, calories=200.0, zone_1_min=5.0),
        ])
        assert combined['duration_min'] == 90.0
        assert combined['calories'] == 600
        assert combined['zone_1_min'] == 15.0

    def test_avg_hr_is_duration_weighted_not_plain_average(self):
        combined = combine_climbing_workouts([
            make_normalized(duration_min=60.0, average_heart_rate=100.0),
            make_normalized(duration_min=20.0, average_heart_rate=180.0),
        ])
        # weighted: (100*60 + 180*20) / 80 = 120.0; plain average would be 140.0
        assert combined['avg_hr'] == 120

    def test_max_hr_takes_the_max_not_the_sum(self):
        combined = combine_climbing_workouts([
            make_normalized(max_heart_rate=150),
            make_normalized(max_heart_rate=185),
        ])
        assert combined['max_hr'] == 185
