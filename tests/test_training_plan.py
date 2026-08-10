"""
Tests for the pure plan-generation logic in training_plan.py. These never
touch Supabase - they exercise the algorithm functions directly with
hand-built inputs.

Run with: pytest
"""
import pandas as pd
import pytest

from training_plan import (
    PlanConfig, compute_plan_length, build_phase_breakdown,
)


@pytest.fixture
def config():
    return PlanConfig()


class TestComputePlanLength:

    def test_already_at_target_returns_zero(self, config):
        assert compute_plan_length(current_ordinal=4, target_ordinal=3, config=config) == 0
        assert compute_plan_length(current_ordinal=4, target_ordinal=4, config=config) == 0

    def test_one_step_default_model_matches_white_to_yellow(self, config):
        # White (ordinal 0) -> Yellow (ordinal 1): 6 + 2*(1-1) = 6 weeks
        assert compute_plan_length(current_ordinal=0, target_ordinal=1, config=config) == 6

    def test_mid_step_default_model_matches_blue_to_red(self, config):
        # Blue (ordinal 3) -> Red (ordinal 4), same as V4 -> V5: 6 + 2*(4-1) = 12 weeks
        assert compute_plan_length(current_ordinal=3, target_ordinal=4, config=config) == 12

    def test_two_step_default_model_matches_v4_to_v6(self, config):
        # V4 (ordinal 3) -> V6 (ordinal 5): step to 4 (12 weeks) + step to 5 (14 weeks) = 26
        assert compute_plan_length(current_ordinal=3, target_ordinal=5, config=config) == 26

    def test_large_gap_has_no_upper_clamp(self, config):
        # 16 steps of the graduated model sum to 336 weeks - far past the old
        # 16-week cap, which no longer exists.
        assert compute_plan_length(current_ordinal=0, target_ordinal=16, config=config) == 336

    def test_never_logged_grade_floors_to_min_plan_weeks(self, config):
        # current_ordinal=-1 means "never logged this grade type"; the raw
        # default-model cost for that single step is below MIN_PLAN_WEEKS (6),
        # so it gets floored up to it.
        assert compute_plan_length(current_ordinal=-1, target_ordinal=0, config=config) == config.MIN_PLAN_WEEKS
        assert config.MIN_PLAN_WEEKS == 6

    def test_personalized_weeks_per_step_overrides_default_model(self, config):
        # 2 steps * 4.5 weeks/step (from history) = 9, used flat instead of
        # the graduated default (which would give a different number).
        assert compute_plan_length(current_ordinal=0, target_ordinal=2, config=config, weeks_per_step=4.5) == 9

    def test_personalized_weeks_per_step_still_floors_to_min_plan_weeks(self, config):
        # 1 step * 2 weeks/step = 2, floored up to MIN_PLAN_WEEKS (6)
        assert compute_plan_length(current_ordinal=0, target_ordinal=1, config=config, weeks_per_step=2.0) == 6


class TestBuildPhaseBreakdown:

    def test_covers_every_week_exactly_once(self, config):
        for total_weeks in [4, 9, 16]:
            breakdown = build_phase_breakdown(total_weeks, config)
            weeks_covered = []
            for phase in breakdown:
                weeks_covered.extend(range(phase['start_week'], phase['end_week'] + 1))
            assert weeks_covered == list(range(1, total_weeks + 1))

    def test_every_phase_has_at_least_one_week(self, config):
        breakdown = build_phase_breakdown(4, config)
        assert all(p['end_week'] - p['start_week'] + 1 >= 1 for p in breakdown)

    def test_nine_week_plan_splits_roughly_four_three_two(self, config):
        breakdown = build_phase_breakdown(9, config)
        lengths = {p['name']: p['end_week'] - p['start_week'] + 1 for p in breakdown}
        assert lengths == {'Base': 4, 'Build': 3, 'Peak': 2}

    def test_phase_names_and_order(self, config):
        breakdown = build_phase_breakdown(9, config)
        assert [p['name'] for p in breakdown] == ['Base', 'Build', 'Peak']

    def test_weights_come_from_config(self, config):
        breakdown = build_phase_breakdown(9, config)
        for phase in breakdown:
            assert phase['weights'] == config.PHASE_CATEGORY_WEIGHTS[phase['name']]


class TestBuildPhaseBreakdownNeglectScores:

    def test_no_neglect_scores_keeps_base_weights(self, config):
        breakdown = build_phase_breakdown(9, config)
        for phase in breakdown:
            assert phase['weights'] == config.PHASE_CATEGORY_WEIGHTS[phase['name']]

    def test_phase_weights_have_no_free_key(self, config):
        breakdown = build_phase_breakdown(9, config)
        for phase in breakdown:
            assert 'Free' not in phase['weights']

    def test_phase_weights_sum_to_one(self, config):
        for phase_name, weights in config.PHASE_CATEGORY_WEIGHTS.items():
            assert sum(weights.values()) == pytest.approx(1.0)

    def test_all_zero_neglect_scores_keeps_base_weights(self, config):
        zero_scores = {'Strength': 0.0, 'Stamina': 0.0, 'Technique': 0.0}
        breakdown = build_phase_breakdown(9, config, neglect_scores=zero_scores)
        for phase in breakdown:
            for cat, weight in phase['weights'].items():
                assert weight == pytest.approx(config.PHASE_CATEGORY_WEIGHTS[phase['name']][cat])

    def test_positive_neglect_score_increases_that_categorys_weight(self, config):
        scores = {'Strength': 0.0, 'Stamina': 0.0, 'Technique': 1.0}
        breakdown = build_phase_breakdown(9, config, neglect_scores=scores)
        base = build_phase_breakdown(9, config)
        for adjusted_phase, base_phase in zip(breakdown, base):
            assert adjusted_phase['weights']['Technique'] > base_phase['weights']['Technique']

    def test_weights_always_sum_to_one(self, config):
        scores = {'Strength': -1.0, 'Stamina': 5.0, 'Technique': -1.0}
        breakdown = build_phase_breakdown(9, config, neglect_scores=scores)
        for phase in breakdown:
            assert sum(phase['weights'].values()) == pytest.approx(1.0)

    def test_weights_never_zero_or_negative_even_with_extreme_negative_score(self, config):
        scores = {'Strength': -100.0, 'Stamina': 0.0, 'Technique': 0.0}
        breakdown = build_phase_breakdown(9, config, neglect_scores=scores)
        for phase in breakdown:
            assert all(w > 0 for w in phase['weights'].values())


from training_plan import schedule_week, _training_day_slots


class TestScheduleWeek:

    def test_returns_seven_days(self, config):
        week = schedule_week({0, 2, 4, 6}, config.PHASE_CATEGORY_WEIGHTS['Base'], {})
        assert len(week) == 7

    def test_rest_fills_untrained_days(self, config):
        week = schedule_week({0, 2, 4}, config.PHASE_CATEGORY_WEIGHTS['Base'], {})
        assert week.count('Rest') == 4

    def test_zero_frequency_is_all_rest(self, config):
        week = schedule_week(set(), config.PHASE_CATEGORY_WEIGHTS['Base'], {})
        assert week == ['Rest'] * 7

    def test_seven_frequency_has_no_rest(self, config):
        week = schedule_week(set(range(7)), config.PHASE_CATEGORY_WEIGHTS['Base'], {})
        assert 'Rest' not in week

    def test_training_slots_land_on_exact_days(self, config):
        week = schedule_week({2, 3, 5}, config.PHASE_CATEGORY_WEIGHTS['Base'], {})
        assert week[2] != 'Rest' and week[3] != 'Rest' and week[5] != 'Rest'
        assert week[0] == 'Rest' and week[1] == 'Rest' and week[4] == 'Rest' and week[6] == 'Rest'

    def test_proportions_converge_over_many_weeks(self, config):
        weights = {'Strength': 0.5, 'Technique': 0.5}
        state = {}
        counts = {'Strength': 0, 'Technique': 0}
        for _ in range(20):
            for cat in schedule_week({0, 3}, weights, state):
                if cat in counts:
                    counts[cat] += 1
        total = sum(counts.values())
        assert abs(counts['Strength'] / total - 0.5) < 0.1

    def test_state_is_mutated_for_reuse_across_weeks(self, config):
        state = {}
        schedule_week({0, 2, 4}, config.PHASE_CATEGORY_WEIGHTS['Base'], state)
        assert state != {}


class TestTrainingDaySlots:

    def test_plan_starting_on_a_training_weekday(self, config):
        # Plan starts on Monday (0); training on Wed(2)/Thu(3)/Sat(5) lands
        # on those exact block-relative slots.
        assert _training_day_slots(start_weekday=0, training_weekdays={2, 3, 5}) == {2, 3, 5}

    def test_plan_starting_on_a_non_training_weekday(self, config):
        # Plan starts on Saturday (5); Wed(2)/Thu(3)/Sat(5) map to
        # block-relative slots 0 (Sat itself), 4 (the next Wed), 5 (the next Thu).
        assert _training_day_slots(start_weekday=5, training_weekdays={2, 3, 5}) == {0, 4, 5}

    def test_all_seven_days_selected_returns_all_slots(self, config):
        assert _training_day_slots(start_weekday=3, training_weekdays=set(range(7))) == set(range(7))

    def test_no_days_selected_returns_no_slots(self, config):
        assert _training_day_slots(start_weekday=0, training_weekdays=set()) == set()


from training_plan import apply_acwr_guardrail


class TestApplyAcwrGuardrail:

    def test_steady_state_load_leaves_schedule_unchanged(self, config):
        # recent_daily_loads already reflects this exact weekly pattern
        # repeated 4x, so acute ~= chronic (ACWR ~= 1) throughout - no
        # downgrade should be needed since nothing is actually ramping up.
        categories = ['Strength', 'Stamina', 'Technique', 'Rest', 'Strength', 'Stamina', 'Rest']
        week_loads = [config.PLACEHOLDER_EFFORT.get(c, 0) for c in categories]
        recent_daily_loads = week_loads * 4
        result = apply_acwr_guardrail(categories, recent_daily_loads, config)
        assert result == categories

    def test_returning_from_a_break_downgrades_a_hard_day(self, config):
        # No training in the last 28 days (chronic ~= 0); a sudden hard day
        # spikes simulated ACWR sharply and should get downgraded - this is
        # exactly the "returning from a break" scenario ACWR is meant to flag.
        recent_daily_loads = [0.0] * 28
        result = apply_acwr_guardrail(['Strength'], recent_daily_loads, config)
        assert result[0] in ('Technique', 'Rest')

    def test_rest_days_are_never_downgraded_further(self, config):
        recent_daily_loads = [8.0] * 28
        result = apply_acwr_guardrail(['Rest', 'Rest'], recent_daily_loads, config)
        assert result == ['Rest', 'Rest']

    def test_returns_same_length_as_input(self, config):
        categories = ['Strength'] * 10
        result = apply_acwr_guardrail(categories, [0.0] * 28, config)
        assert len(result) == 10


class TestApplyAcwrGuardrailEffortOverrides:

    def test_effort_override_used_instead_of_placeholder(self, config):
        # A very high real Strength effort (20) should still trigger a
        # downgrade on a day returning from a full break, same as the
        # existing placeholder-based test does.
        recent_daily_loads = [0.0] * 28
        result = apply_acwr_guardrail(['Strength'], recent_daily_loads, config, effort_overrides={'Strength': 20})
        assert result[0] in ('Technique', 'Rest')

    def test_no_effort_overrides_falls_back_to_placeholder(self, config):
        recent_daily_loads = [0.0] * 28
        result = apply_acwr_guardrail(['Strength'], recent_daily_loads, config)
        assert result[0] in ('Technique', 'Rest')

    def test_missing_category_in_overrides_falls_back_to_placeholder(self, config):
        categories = ['Strength', 'Stamina', 'Technique', 'Rest', 'Strength', 'Stamina', 'Rest']
        week_loads = [config.PLACEHOLDER_EFFORT.get(c, 0) for c in categories]
        recent_daily_loads = week_loads * 4
        result = apply_acwr_guardrail(categories, recent_daily_loads, config, effort_overrides={'Free': 3})
        assert result == categories


from training_plan import _category_neglect_scores


def make_past_df_for_neglect(rows):
    df = pd.DataFrame(rows)
    if not df.empty:
        df['date'] = pd.to_datetime(df['date'])
    return df


class TestCategoryNeglectScores:

    def test_no_history_gives_all_zero_scores(self, config):
        df_past = make_past_df_for_neglect([])
        scores = _category_neglect_scores(df_past)
        assert scores == {'Strength': 0.0, 'Stamina': 0.0, 'Technique': 0.0}

    def test_rarely_trained_low_effort_category_gets_positive_score(self, config):
        rows = (
            [{'date': '2026-06-01', 'category': 'Strength', 'effort': 8}] * 10
            + [{'date': '2026-06-02', 'category': 'Technique', 'effort': 2}]
        )
        df_past = make_past_df_for_neglect(rows)
        scores = _category_neglect_scores(df_past)
        assert scores['Technique'] > 0

    def test_often_trained_high_effort_category_gets_negative_score(self, config):
        rows = (
            [{'date': '2026-06-01', 'category': 'Strength', 'effort': 9}] * 10
            + [{'date': '2026-06-02', 'category': 'Technique', 'effort': 2}]
        )
        df_past = make_past_df_for_neglect(rows)
        scores = _category_neglect_scores(df_past)
        assert scores['Strength'] < 0

    def test_free_sessions_excluded_from_totals(self, config):
        # Free is a real, valid category people log by hand - but it should
        # never affect the neglect analysis for the three planned categories,
        # the same way Rest already doesn't.
        rows = (
            [{'date': '2026-06-01', 'category': 'Strength', 'effort': 8}] * 10
            + [{'date': '2026-06-02', 'category': 'Technique', 'effort': 2}]
        )
        without_free = _category_neglect_scores(make_past_df_for_neglect(rows))
        with_free = _category_neglect_scores(make_past_df_for_neglect(
            rows + [{'date': '2026-06-03', 'category': 'Free', 'effort': 5}] * 5
        ))
        assert with_free == without_free
        assert 'Free' not in with_free


from training_plan import _historical_weeks_per_step


class TestHistoricalWeeksPerStep:

    def test_no_history_returns_none(self, config):
        assert _historical_weeks_per_step(make_past_df_for_neglect([]), 'gym') is None

    def test_fewer_than_two_levels_returns_none(self, config):
        df_past = make_past_df_for_neglect([
            {'date': '2026-06-01', 'gym_grade': 'Blue', 'gym_numeric': 3},
        ])
        assert _historical_weeks_per_step(df_past, 'gym') is None

    def test_averages_gaps_between_first_achieved_levels(self, config):
        df_past = make_past_df_for_neglect([
            {'date': '2026-05-01', 'gym_grade': 'White', 'gym_numeric': 0},
            {'date': '2026-05-15', 'gym_grade': 'Yellow', 'gym_numeric': 1},  # +2 weeks
            {'date': '2026-06-12', 'gym_grade': 'Green', 'gym_numeric': 2},   # +4 weeks
        ])
        assert _historical_weeks_per_step(df_past, 'gym') == pytest.approx(3.0)

    def test_ignores_repeat_logs_of_an_already_achieved_level(self, config):
        df_past = make_past_df_for_neglect([
            {'date': '2026-05-01', 'gym_grade': 'White', 'gym_numeric': 0},
            {'date': '2026-05-08', 'gym_grade': 'White', 'gym_numeric': 0},
            {'date': '2026-05-15', 'gym_grade': 'Yellow', 'gym_numeric': 1},
        ])
        assert _historical_weeks_per_step(df_past, 'gym') == pytest.approx(2.0)


from training_plan import _category_effort_overrides


class TestCategoryEffortOverrides:

    def test_no_history_returns_empty_dict(self, config):
        assert _category_effort_overrides(make_past_df_for_neglect([])) == {}

    def test_omits_categories_never_logged(self, config):
        df_past = make_past_df_for_neglect([{'date': '2026-06-01', 'category': 'Strength', 'effort': 8}])
        overrides = _category_effort_overrides(df_past)
        assert 'Technique' not in overrides

    def test_computes_correct_mean_for_logged_category(self, config):
        df_past = make_past_df_for_neglect([
            {'date': '2026-06-01', 'category': 'Strength', 'effort': 8},
            {'date': '2026-06-02', 'category': 'Strength', 'effort': 6},
        ])
        overrides = _category_effort_overrides(df_past)
        assert overrides['Strength'] == pytest.approx(7.0)


from training_plan import select_exercises_for_day


def make_exercise_df(rows):
    return pd.DataFrame(rows)


class TestSelectExercisesForDay:

    def test_picks_one_exercise_per_phase(self, config):
        df_dict = make_exercise_df([
            {'name': 'Stretch', 'phase': 'Before', 'categories': []},
            {'name': 'Campus Board', 'phase': 'During', 'categories': ['Strength']},
            {'name': 'Foam Roll', 'phase': 'After', 'categories': []},
        ])
        result = select_exercises_for_day('Strength', df_dict, {})
        assert result == {'before': ['Stretch'], 'during': ['Campus Board'], 'after': ['Foam Roll']}

    def test_during_filters_by_category(self, config):
        df_dict = make_exercise_df([
            {'name': 'Campus Board', 'phase': 'During', 'categories': ['Strength']},
            {'name': 'Slab Drills', 'phase': 'During', 'categories': ['Technique']},
        ])
        result = select_exercises_for_day('Technique', df_dict, {})
        assert result['during'] == ['Slab Drills']

    def test_empty_pool_returns_empty_list_not_crash(self, config):
        df_dict = make_exercise_df([{'name': 'Campus Board', 'phase': 'During', 'categories': ['Strength']}])
        result = select_exercises_for_day('Stamina', df_dict, {})
        assert result['during'] == []

    def test_rotation_state_advances_through_pool(self, config):
        df_dict = make_exercise_df([
            {'name': 'A', 'phase': 'Before', 'categories': []},
            {'name': 'B', 'phase': 'Before', 'categories': []},
        ])
        state = {}
        first = select_exercises_for_day('Strength', df_dict, state)
        second = select_exercises_for_day('Strength', df_dict, state)
        assert first['before'] != second['before']

    def test_mandatory_before_exercise_always_included(self, config):
        df_dict = make_exercise_df([
            {'name': 'Warm Up', 'phase': 'Before', 'categories': [], 'mandatory': True},
        ])
        result = select_exercises_for_day('Strength', df_dict, {})
        assert result['before'] == ['Warm Up']

    def test_mandatory_during_included_regardless_of_category(self, config):
        # Campus Board is mandatory but only tagged Strength - it should
        # still show up on a Technique day, which is the whole point of
        # "mandatory".
        df_dict = make_exercise_df([
            {'name': 'Campus Board', 'phase': 'During', 'categories': ['Strength'], 'mandatory': True},
        ])
        result = select_exercises_for_day('Technique', df_dict, {})
        assert result['during'] == ['Campus Board']

    def test_mandatory_plus_full_category_pool_both_included(self, config):
        df_dict = make_exercise_df([
            {'name': 'Campus Board', 'phase': 'During', 'categories': ['Strength'], 'mandatory': True},
            {'name': 'Deadhang', 'phase': 'During', 'categories': ['Strength'], 'mandatory': False},
        ])
        result = select_exercises_for_day('Strength', df_dict, {})
        assert set(result['during']) == {'Campus Board', 'Deadhang'}

    def test_during_includes_every_category_tagged_exercise_not_just_one(self, config):
        df_dict = make_exercise_df([
            {'name': 'Campus Board', 'phase': 'During', 'categories': ['Strength']},
            {'name': 'Deadhang', 'phase': 'During', 'categories': ['Strength']},
            {'name': 'Weighted Pull-ups', 'phase': 'During', 'categories': ['Strength']},
        ])
        result = select_exercises_for_day('Strength', df_dict, {})
        assert set(result['during']) == {'Campus Board', 'Deadhang', 'Weighted Pull-ups'}

    def test_during_pool_is_identical_every_call_no_rotation(self, config):
        df_dict = make_exercise_df([
            {'name': 'A', 'phase': 'During', 'categories': ['Strength']},
            {'name': 'B', 'phase': 'During', 'categories': ['Strength']},
        ])
        state = {}
        first = select_exercises_for_day('Strength', df_dict, state)
        second = select_exercises_for_day('Strength', df_dict, state)
        assert set(first['during']) == set(second['during']) == {'A', 'B'}

    def test_non_mandatory_exercises_still_rotate_normally(self, config):
        df_dict = make_exercise_df([
            {'name': 'Warm Up', 'phase': 'Before', 'categories': [], 'mandatory': True},
            {'name': 'Dynamic Stretch', 'phase': 'Before', 'categories': [], 'mandatory': False},
            {'name': 'Foam Roll', 'phase': 'Before', 'categories': [], 'mandatory': False},
        ])
        state = {}
        first = select_exercises_for_day('Strength', df_dict, state)
        second = select_exercises_for_day('Strength', df_dict, state)
        assert 'Warm Up' in first['before'] and 'Warm Up' in second['before']
        assert first['before'] != second['before']

    def test_excluded_exercise_never_appears(self, config):
        df_dict = make_exercise_df([
            {'name': 'Crag', 'phase': 'During', 'categories': ['Free'], 'exclude_from_plan': True},
            {'name': 'Campus Board', 'phase': 'During', 'categories': ['Free']},
        ])
        result = select_exercises_for_day('Free', df_dict, {})
        assert 'Crag' not in result['during']
        assert result['during'] == ['Campus Board']

    def test_excluded_exercise_ignored_even_when_mandatory(self, config):
        df_dict = make_exercise_df([
            {'name': 'Crag', 'phase': 'During', 'categories': ['Free'], 'mandatory': True, 'exclude_from_plan': True},
        ])
        result = select_exercises_for_day('Free', df_dict, {})
        assert result['during'] == []

    def test_excluded_only_exercise_in_pool_leaves_it_empty(self, config):
        df_dict = make_exercise_df([
            {'name': 'Crag', 'phase': 'Before', 'categories': [], 'exclude_from_plan': True},
        ])
        result = select_exercises_for_day('Strength', df_dict, {})
        assert result['before'] == []


from training_plan import generate_plan, preview_plan, _recent_daily_loads


def make_past_df(rows):
    df = pd.DataFrame(rows)
    if not df.empty:
        df['date'] = pd.to_datetime(df['date'])
    return df


class TestRecentDailyLoads:

    def test_returns_window_length(self, config):
        df_past = make_past_df([])
        assert len(_recent_daily_loads(df_past, window=28)) == 28

    def test_sums_effort_per_day(self, config):
        df_past = make_past_df([
            {'date': pd.Timestamp('today').normalize() - pd.Timedelta(days=2), 'effort': 5},
            {'date': pd.Timestamp('today').normalize() - pd.Timedelta(days=2), 'effort': 3},
        ])
        loads = _recent_daily_loads(df_past, window=5)
        assert 8.0 in loads


class TestGeneratePlan:

    def test_already_at_target_short_circuits(self, config):
        result = generate_plan('Red', 'gym', 'Blue', {0, 2, 4, 6}, 0, [0.0] * 28, pd.DataFrame(columns=['name', 'phase', 'categories']))
        assert result == {'already_at_target': True}

    def test_generates_total_weeks_times_seven_days(self, config):
        result = generate_plan(None, 'gym', 'Blue', {0, 2, 4, 6}, 0, [0.0] * 28, pd.DataFrame(columns=['name', 'phase', 'categories']))
        assert len(result['days']) == result['total_weeks'] * 7

    def test_day_offsets_are_sequential_from_zero(self, config):
        result = generate_plan(None, 'gym', 'Blue', {0, 2, 4, 6}, 0, [0.0] * 28, pd.DataFrame(columns=['name', 'phase', 'categories']))
        assert [d['day_offset'] for d in result['days']] == list(range(len(result['days'])))

    def test_rest_days_get_no_exercises(self, config):
        result = generate_plan(None, 'gym', 'Blue', {0, 2, 4, 6}, 0, [0.0] * 28, pd.DataFrame(columns=['name', 'phase', 'categories']))
        rest_days = [d for d in result['days'] if d['category'] == 'Rest']
        assert rest_days  # sanity: some rest days exist at 4/7 training days
        assert all(d['exercises'] == {'before': [], 'during': [], 'after': []} for d in rest_days)

    def test_non_training_weekdays_are_always_rest(self, config):
        # start_weekday=0 (Monday); training on Wed(2)/Thu(3)/Sat(5). Mon(0),
        # Tue(1), Fri(4), Sun(6) are never training slots in ANY week -
        # taper only ever removes from the training set, never adds to it -
        # so this holds regardless of ACWR downgrades or which week it is.
        result = generate_plan(None, 'gym', 'Blue', {2, 3, 5}, 0, [0.0] * 28, pd.DataFrame(columns=['name', 'phase', 'categories']))
        for week_start in range(0, len(result['days']) - 6, 7):
            week = result['days'][week_start:week_start + 7]
            assert week[0]['category'] == 'Rest'
            assert week[1]['category'] == 'Rest'
            assert week[4]['category'] == 'Rest'
            assert week[6]['category'] == 'Rest'

    def test_taper_week_drops_the_slot_closest_to_plan_completion(self, config):
        # Isolate the taper-slot logic from the (separately-tested) ACWR
        # guardrail by making the downgrade threshold unreachable.
        config.ACWR_DOWNGRADE_THRESHOLD = 999
        # White -> Yellow is exactly 6 weeks (MIN_PLAN_WEEKS) via the default
        # pace model, so this plan's only taper week is its single final week.
        result = generate_plan(
            'White', 'gym', 'Yellow', {2, 3, 5}, 0, [0.0] * 28,
            pd.DataFrame(columns=['name', 'phase', 'categories']), config=config,
        )
        assert result['total_weeks'] == 6
        last_week = result['days'][-7:]
        # taper_frequency = round(3 * 0.7) = 2, keeping the earliest 2 of the
        # sorted training slots {2, 3, 5} - i.e. slots 2 and 3 - and dropping 5.
        assert last_week[2]['category'] != 'Rest'
        assert last_week[3]['category'] != 'Rest'
        assert last_week[5]['category'] == 'Rest'


class TestGeneratePlanPersonalization:

    def test_weeks_per_step_overrides_default_pace(self, config):
        # Blue -> Red is ordinal 3 -> 4 (default model would give 12 weeks);
        # with a personalized weeks_per_step of 4.5, distance(1)*4.5 = 4.5,
        # floored to MIN_PLAN_WEEKS (6).
        result = generate_plan(
            'Blue', 'gym', 'Red', {0, 1, 2, 3}, 0, [0.0] * 28,
            pd.DataFrame(columns=['name', 'phase', 'categories']),
            weeks_per_step=4.5,
        )
        assert result['total_weeks'] == 6
        assert result['weeks_per_step'] == 4.5

    def test_no_weeks_per_step_uses_default_pace_and_reports_none(self, config):
        result = generate_plan(
            'Blue', 'gym', 'Red', {0, 1, 2, 3}, 0, [0.0] * 28,
            pd.DataFrame(columns=['name', 'phase', 'categories']),
        )
        assert result['total_weeks'] == 12
        assert result['weeks_per_step'] is None

    def test_neglect_scores_are_threaded_into_phase_breakdown(self, config):
        scores = {'Strength': 0.0, 'Stamina': 0.0, 'Technique': 1.0, 'Free': 0.0}
        result = generate_plan(
            'Blue', 'gym', 'Red', {0, 1, 2, 3}, 0, [0.0] * 28,
            pd.DataFrame(columns=['name', 'phase', 'categories']),
            neglect_scores=scores,
        )
        base = generate_plan('Blue', 'gym', 'Red', {0, 1, 2, 3}, 0, [0.0] * 28, pd.DataFrame(columns=['name', 'phase', 'categories']))
        for adjusted_phase, base_phase in zip(result['phase_breakdown'], base['phase_breakdown']):
            assert adjusted_phase['weights']['Technique'] > base_phase['weights']['Technique']
        assert result['neglect_scores'] == scores

    def test_effort_overrides_can_change_downgrade_outcome(self, config):
        # A steady non-zero baseline load (not the all-zero "returning from
        # a break" case, which spikes the ratio regardless of magnitude)
        # plus weights pushed almost entirely onto Strength, so a real
        # logged average (18) well above the fixed placeholder (8) actually
        # tips the simulated ACWR over the threshold on different days than
        # the placeholder would.
        recent_daily_loads = [5.0] * 28
        neglect_scores = {'Strength': 3.0, 'Stamina': -3.0, 'Technique': -3.0, 'Free': -3.0}
        without_override = generate_plan(
            'Blue', 'gym', 'Red', set(range(7)), 0, recent_daily_loads,
            pd.DataFrame(columns=['name', 'phase', 'categories']),
            neglect_scores=neglect_scores,
        )
        with_override = generate_plan(
            'Blue', 'gym', 'Red', set(range(7)), 0, recent_daily_loads,
            pd.DataFrame(columns=['name', 'phase', 'categories']),
            neglect_scores=neglect_scores,
            effort_overrides={'Strength': 18},
        )
        with_categories = [d['category'] for d in with_override['days']]
        without_categories = [d['category'] for d in without_override['days']]
        assert with_categories != without_categories


class TestPreviewPlan:

    def test_matches_generate_plan_given_same_inputs(self, config):
        df_past = make_past_df([])
        df_dict = pd.DataFrame(columns=['name', 'phase', 'categories'])
        training_weekdays = {0, 2, 4}
        start_weekday = pd.to_datetime('today').normalize().weekday()
        result = preview_plan(None, 'gym', 'Blue', training_weekdays, df_past, df_dict)
        expected = generate_plan(None, 'gym', 'Blue', training_weekdays, start_weekday, _recent_daily_loads(df_past), df_dict)
        assert result['total_weeks'] == expected['total_weeks']


class TestPreviewPlanPersonalization:

    def test_preview_plan_reports_none_pace_with_thin_history(self, config):
        df_past = make_past_df([])
        df_dict = pd.DataFrame(columns=['name', 'phase', 'categories'])
        result = preview_plan(None, 'gym', 'Blue', {0, 2, 4}, df_past, df_dict)
        assert result['weeks_per_step'] is None

    def test_preview_plan_reports_personalized_pace_with_enough_history(self, config):
        df_past = make_past_df([
            {'date': '2026-05-01', 'gym_grade': 'White', 'gym_numeric': 0, 'category': 'Strength', 'effort': 5},
            {'date': '2026-05-15', 'gym_grade': 'Yellow', 'gym_numeric': 1, 'category': 'Strength', 'effort': 5},
        ])
        df_dict = pd.DataFrame(columns=['name', 'phase', 'categories'])
        result = preview_plan('Yellow', 'gym', 'Blue', {0, 2, 4}, df_past, df_dict)
        assert result['weeks_per_step'] == pytest.approx(2.0)


from datetime import datetime
from pydantic import ValidationError
from training_plan import GoalRecord


class TestGoalRecord:

    def test_valid_goal_parses(self):
        goal = GoalRecord.model_validate({
            'id': 1, 'created_at': '2026-07-01T10:00:00', 'target_type': 'gym',
            'target_grade': 'Red', 'start_grade': 'Blue', 'weekly_frequency': 4,
            'total_weeks': 9, 'phase_breakdown': [{'name': 'Base', 'start_week': 1, 'end_week': 4, 'weights': {}}],
            'status': 'active', 'training_weekdays': ['Monday', 'Wednesday', 'Friday', 'Saturday'],
        })
        assert goal.target_grade == 'Red'
        assert isinstance(goal.created_at, datetime)
        assert goal.training_weekdays == ['Monday', 'Wednesday', 'Friday', 'Saturday']

    def test_missing_start_grade_is_allowed(self):
        goal = GoalRecord.model_validate({
            'id': 1, 'created_at': None, 'target_type': 'gym', 'target_grade': 'Red',
            'start_grade': None, 'weekly_frequency': 4, 'total_weeks': 9,
            'phase_breakdown': [], 'status': 'active', 'training_weekdays': ['Monday'],
        })
        assert goal.start_grade is None

    def test_invalid_weekday_name_raises(self):
        with pytest.raises(ValidationError):
            GoalRecord.model_validate({
                'id': 1, 'created_at': None, 'target_type': 'gym', 'target_grade': 'Red',
                'start_grade': None, 'weekly_frequency': 1, 'total_weeks': 9,
                'phase_breakdown': [], 'status': 'active', 'training_weekdays': ['Notaday'],
            })


from training_plan import _existing_session_dates


class TestExistingSessionDates:

    def test_empty_df_returns_empty_set(self, config):
        assert _existing_session_dates(make_past_df([])) == set()

    def test_returns_normalized_dates_from_df(self, config):
        df_future = make_past_df([
            {'date': '2026-08-01', 'id': 1},
            {'date': '2026-08-03', 'id': 2},
        ])
        result = _existing_session_dates(df_future)
        assert result == {pd.Timestamp('2026-08-01'), pd.Timestamp('2026-08-03')}
