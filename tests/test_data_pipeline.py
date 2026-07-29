"""
Tests for the row validation and cleaning logic in data_pipeline.py.

These exercise clean_data() directly with hand-built rows shaped like
worksheet.get_all_records() output

Run with: pytest
"""
import pandas as pd
import pytest

from data_pipeline import clean_data, compute_acwr, get_peak_sessions, PipelineConfig


@pytest.fixture
def config():
    return PipelineConfig()


def make_session_row(**overrides):
    row = {
        'Carimbo de data/hora': '25/07/2026 10:00:00',
        'Date': '20/07/2026',
        'Category': 'Strength',
        'Effort Scale': 7,
        'Max Gym Grade Color': 'Blue',
        'Max Moonboard Grade': 'V4',
        'Injuries / Tweaks': 'No',
        'Exercises': 'Pull-ups, Hangboard',
    }
    row.update(overrides)
    return row


def make_exercise_row(**overrides):
    row = {
        'Name': 'Pull-ups',
        'Type': 'Reps',
        'Sets': '4',
        'Reps/Time': '8',
        'Rest': '2',
        'Comments': '-',
        'Phase': 'During',
    }
    row.update(overrides)
    return row


class TestSessionValidation:

    def test_valid_row_parses_correctly(self, config):
        past, future, _ = clean_data([make_session_row()], [], config)
        assert len(past) == 1
        row = past.iloc[0]
        assert row['category'] == 'Strength'
        assert row['effort'] == 7
        assert row['gym_grade'] == 'Blue'
        assert row['gym_numeric'] == 3
        assert row['injured'] == False

    def test_invalid_category_is_skipped(self, config):
        rows = [make_session_row(Category='Bouldering??')]
        past, future, _ = clean_data(rows, [], config)
        assert len(past) == 0 and len(future) == 0

    def test_invalid_gym_grade_is_skipped(self, config):
        rows = [make_session_row(**{'Max Gym Grade Color': 'Turquoise'})]
        past, future, _ = clean_data(rows, [], config)
        assert len(past) == 0

    def test_invalid_moonboard_grade_is_skipped(self, config):
        rows = [make_session_row(**{'Max Moonboard Grade': 'V99'})]
        past, future, _ = clean_data(rows, [], config)
        assert len(past) == 0

    def test_missing_date_is_skipped(self, config):
        rows = [make_session_row(Date='')]
        past, future, _ = clean_data(rows, [], config)
        assert len(past) == 0 and len(future) == 0

    def test_blank_effort_becomes_none(self, config):
        rows = [make_session_row(**{'Effort Scale': ''})]
        past, future, _ = clean_data(rows, [], config)
        assert pd.isna(past.iloc[0]['effort'])

    def test_injured_yes_no_mapping(self, config):
        rows = [make_session_row(**{'Injuries / Tweaks': 'Yes'})]
        past, _, _ = clean_data(rows, [], config)
        assert past.iloc[0]['injured'] == True

    def test_missing_grades_become_negative_one(self, config):
        rows = [make_session_row(**{'Max Gym Grade Color': '', 'Max Moonboard Grade': ''})]
        past, _, _ = clean_data(rows, [], config)
        assert past.iloc[0]['gym_numeric'] == -1
        assert past.iloc[0]['moonboard_numeric'] == -1

    def test_past_future_split(self, config):
        rows = [
            make_session_row(Date='01/01/2020'),
            make_session_row(Date='01/01/2099'),
        ]
        past, future, _ = clean_data(rows, [], config)
        assert len(past) == 1
        assert len(future) == 1

    def test_header_whitespace_is_stripped(self, config):
        rows = [{f' {k} ': v for k, v in make_session_row().items()}]
        past, future, _ = clean_data(rows, [], config)
        assert len(past) == 1

    def test_no_rows_returns_empty_frames(self, config):
        past, future, _ = clean_data([], [], config)
        assert len(past) == 0 and len(future) == 0

    def test_one_bad_row_does_not_drop_good_rows(self, config):
        rows = [
            make_session_row(Date='20/07/2026', Category='Strength'),
            make_session_row(Date='21/07/2026', Category='Not A Real Category'),
        ]
        past, future, _ = clean_data(rows, [], config)
        assert len(past) == 1
        assert past.iloc[0]['category'] == 'Strength'


class TestExerciseValidation:

    def test_valid_exercise_parses_correctly(self, config):
        _, _, df_dict = clean_data([], [make_exercise_row()], config)
        assert len(df_dict) == 1
        row = df_dict.iloc[0]
        assert row['name'] == 'Pull-ups'
        assert row['sets'] == 4
        assert row['phase'] == 'During'

    def test_missing_name_is_skipped(self, config):
        rows = [make_exercise_row(Name='')]
        _, _, df_dict = clean_data([], rows, config)
        assert len(df_dict) == 0

    def test_invalid_type_is_skipped(self, config):
        rows = [make_exercise_row(Type='Weight')]
        _, _, df_dict = clean_data([], rows, config)
        assert len(df_dict) == 0

    def test_invalid_phase_is_skipped(self, config):
        rows = [make_exercise_row(Phase='Warmup')]
        _, _, df_dict = clean_data([], rows, config)
        assert len(df_dict) == 0

    def test_missing_phase_is_allowed(self, config):
        """Phase is new as of Phase 7 - existing rows without it must still validate."""
        rows = [make_exercise_row(Phase='')]
        _, _, df_dict = clean_data([], rows, config)
        assert len(df_dict) == 1
        assert df_dict.iloc[0]['phase'] is None


class TestComputeACWR:

    def test_constant_load_converges_to_one(self):
        dates = pd.date_range('2026-06-01', periods=30, freq='D')
        df = pd.DataFrame({'date': dates, 'effort': [5] * 30, 'category': ['Strength'] * 30})
        acwr = compute_acwr(df)
        assert abs(acwr['acwr'].iloc[-1] - 1.0) < 0.05

    def test_load_ramp_produces_acwr_above_one(self):
        dates = pd.date_range('2026-06-01', periods=30, freq='D')
        efforts = [2] * 20 + [9] * 10
        df = pd.DataFrame({'date': dates, 'effort': efforts, 'category': ['Strength'] * 30})
        acwr = compute_acwr(df)
        assert acwr['acwr'].iloc[-1] > 1.2

    def test_gap_days_count_as_zero_load(self):
        dates = pd.to_datetime(['2026-06-01', '2026-06-03'])
        df = pd.DataFrame({'date': dates, 'effort': [5, 5], 'category': ['Strength', 'Strength']})
        acwr = compute_acwr(df)
        assert len(acwr) == 3
        assert acwr.loc[pd.Timestamp('2026-06-02'), 'daily_load'] == 0

    def test_empty_dataframe_returns_empty_result(self):
        df = pd.DataFrame(columns=['date', 'effort', 'category'])
        assert compute_acwr(df).empty

    def test_all_missing_effort_returns_empty_result(self):
        df = pd.DataFrame({
            'date': pd.to_datetime(['2026-06-01']),
            'effort': [pd.NA],
            'category': ['Rest'],
        })
        assert compute_acwr(df).empty


class TestGetPeakSessions:

    @pytest.fixture
    def sample_sessions(self):
        return pd.DataFrame({
            'date': pd.to_datetime(['2026-07-01', '2026-07-02', '2026-07-03', '2026-07-04', '2026-07-05']),
            'category': ['Strength', 'Rest', 'Technique', 'Free', 'Strength'],
            'effort': [8, None, 6, 9, 5],
            'gym_numeric': [3, -1, 5, -1, 2],
            'moonboard_numeric': [-1, -1, -1, 8, -1],
        })

    def test_rest_days_are_excluded(self, sample_sessions):
        top = get_peak_sessions(sample_sessions, n=3)
        assert 'Rest' not in top['category'].values

    def test_highest_grade_session_ranks_first(self, sample_sessions):
        top = get_peak_sessions(sample_sessions, n=3)
        assert top.iloc[0]['date'] == pd.Timestamp('2026-07-04')

    def test_returns_requested_count(self, sample_sessions):
        assert len(get_peak_sessions(sample_sessions, n=3)) == 3

    def test_fewer_sessions_than_n_returns_available(self, sample_sessions):
        assert len(get_peak_sessions(sample_sessions.iloc[:1], n=3)) == 1

    def test_empty_dataframe_returns_empty_result(self, sample_sessions):
        assert get_peak_sessions(sample_sessions.iloc[0:0], n=3).empty