"""
Pure training-plan generation algorithm - grade-distance pacing, phased
category weighting, ACWR-guarded scheduling, and exercise selection.
No Supabase calls; see store.py for goal persistence.
"""

import statistics
from datetime import datetime
from typing import Optional

import pandas as pd
from pydantic import BaseModel, field_validator

from data_pipeline import PipelineConfig


class PlanConfig:
    """Tunable constants the plan generator depends on."""

    GOALS_TABLE = 'goals'
    WEEKDAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    PLANNED_CATEGORIES = ['Strength', 'Stamina', 'Technique']

    MIN_PLAN_WEEKS = 6
    DEFAULT_STEP_BASE_WEEKS = 6
    DEFAULT_STEP_INCREMENT_WEEKS = 2
    NEGLECT_INFLUENCE = 0.5
    NEGLECT_WEIGHT_FLOOR = 0.01

    PHASE_PROPORTIONS = {'Base': 0.4, 'Build': 0.4, 'Peak': 0.2}
    # Free is excluded - it can't be scheduled in advance; convert a day to
    # Free by hand instead.
    PHASE_CATEGORY_WEIGHTS = {
        'Base': {'Technique': 0.375, 'Stamina': 0.375, 'Strength': 0.25},
        'Build': {'Strength': 0.47, 'Technique': 0.29, 'Stamina': 0.24},
        'Peak': {'Technique': 0.46, 'Strength': 0.31, 'Stamina': 0.23},
    }
    TAPER_FREQUENCY_REDUCTION = 0.3

    # Placeholder effort per category for the ACWR simulation, not real data.
    PLACEHOLDER_EFFORT = {'Strength': 8, 'Free': 7, 'Stamina': 6, 'Technique': 5}
    ACWR_ACUTE_WINDOW = 7
    ACWR_CHRONIC_WINDOW = 28
    ACWR_DOWNGRADE_THRESHOLD = 1.5


class GoalRecord(BaseModel):
    """A single validated row from the 'goals' table."""

    id: int
    created_at: Optional[datetime] = None
    target_type: str
    target_grade: str
    start_grade: Optional[str] = None
    weekly_frequency: int
    training_weekdays: list[str]
    total_weeks: int
    phase_breakdown: list[dict]
    status: str

    @field_validator('created_at', mode='before')
    @classmethod
    def parse_created_at(cls, v):
        if v is None:
            return None
        parsed = pd.to_datetime(v, errors='coerce')
        return None if pd.isna(parsed) else parsed.to_pydatetime()

    @field_validator('training_weekdays', mode='before')
    @classmethod
    def validate_training_weekdays(cls, v):
        if not v:
            return []
        invalid = [d for d in v if d not in PlanConfig.WEEKDAY_NAMES]
        if invalid:
            raise ValueError(f'Unknown weekday name(s): {invalid!r}')
        return list(v)


def compute_plan_length(
    current_ordinal: int, target_ordinal: int, config: PlanConfig,
    weeks_per_step: Optional[float] = None,
) -> int:
    """Total plan length in weeks (0 if already at/above target). Uses a
    graduated per-level cost by default, or a flat weeks_per_step from
    history when given; no upper clamp."""
    distance = target_ordinal - current_ordinal
    if distance <= 0:
        return 0
    if weeks_per_step is not None:
        weeks = distance * weeks_per_step
    else:
        weeks = sum(
            config.DEFAULT_STEP_BASE_WEEKS + config.DEFAULT_STEP_INCREMENT_WEEKS * (k - 1)
            for k in range(current_ordinal + 1, target_ordinal + 1)
        )
    return max(config.MIN_PLAN_WEEKS, round(weeks))


def _adjust_weights_for_neglect(
    base_weights: dict[str, float], neglect_scores: dict[str, float], config: PlanConfig,
) -> dict[str, float]:
    """Nudges each category's weight by its neglect score, floored above
    zero and renormalized to sum to 1."""
    adjusted = {
        cat: max(config.NEGLECT_WEIGHT_FLOOR, weight * (1 + config.NEGLECT_INFLUENCE * neglect_scores.get(cat, 0.0)))
        for cat, weight in base_weights.items()
    }
    total = sum(adjusted.values())
    return {cat: w / total for cat, w in adjusted.items()}


def build_phase_breakdown(
    total_weeks: int, config: PlanConfig, neglect_scores: Optional[dict[str, float]] = None,
) -> list[dict]:
    """Splits total_weeks across PHASE_PROPORTIONS via largest-remainder,
    so every phase gets at least 1 week."""
    names = list(config.PHASE_PROPORTIONS.keys())
    raw = {n: total_weeks * config.PHASE_PROPORTIONS[n] for n in names}
    weeks = {n: max(1, int(raw[n])) for n in names}

    remainder = total_weeks - sum(weeks.values())
    fractional_order = sorted(names, key=lambda n: raw[n] - int(raw[n]), reverse=True)
    i = 0
    while remainder > 0:
        weeks[fractional_order[i % len(fractional_order)]] += 1
        remainder -= 1
        i += 1
    while remainder < 0:
        shrinkable = sorted((n for n in names if weeks[n] > 1), key=lambda n: weeks[n], reverse=True)
        weeks[shrinkable[0]] -= 1
        remainder += 1

    breakdown = []
    start = 1
    for n in names:
        end = start + weeks[n] - 1
        weights = config.PHASE_CATEGORY_WEIGHTS[n]
        if neglect_scores:
            weights = _adjust_weights_for_neglect(weights, neglect_scores, config)
        breakdown.append({
            'name': n, 'start_week': start, 'end_week': end,
            'weights': weights,
        })
        start = end + 1
    return breakdown


def _training_day_slots(start_weekday: int, training_weekdays: set[int]) -> set[int]:
    """Maps training_weekdays to block-relative slot indices (0-6), given
    day-offset 0's real weekday."""
    return {i for i in range(7) if (start_weekday + i) % 7 in training_weekdays}


def _swrr_pick(weights: dict[str, float], state: dict[str, float]) -> str:
    """One smooth-weighted-round-robin pick: picks the highest-credit
    category, then deducts the total weight from it."""
    total = sum(weights.values())
    for category, weight in weights.items():
        state[category] = state.get(category, 0.0) + weight
    best = max(state, key=lambda c: state[c])
    state[best] -= total
    return best


def schedule_week(training_slots: set[int], phase_weights: dict[str, float], swrr_state: dict[str, float]) -> list[str]:
    """One week of category assignments: training_slots get a category via
    SWRR, everything else is 'Rest'."""
    return [
        _swrr_pick(phase_weights, swrr_state) if day in training_slots else 'Rest'
        for day in range(7)
    ]


def _simulated_acwr(window: list[float], config: PlanConfig) -> float:
    acute = statistics.mean(window[-config.ACWR_ACUTE_WINDOW:])
    chronic = statistics.mean(window[-config.ACWR_CHRONIC_WINDOW:])
    return acute / chronic if chronic > 0 else 0.0


def _downgrade_if_needed(
    category: str, window: list[float], config: PlanConfig,
    effort_overrides: Optional[dict[str, float]] = None,
) -> str:
    """Downgrades category to Technique or Rest if simulated ACWR exceeds
    the threshold; effort_overrides take priority over placeholders."""
    if category == 'Rest':
        return category
    if _simulated_acwr(window, config) <= config.ACWR_DOWNGRADE_THRESHOLD:
        return category
    if category != 'Technique':
        window[-1] = (effort_overrides or {}).get('Technique', config.PLACEHOLDER_EFFORT.get('Technique', 0))
        if _simulated_acwr(window, config) <= config.ACWR_DOWNGRADE_THRESHOLD:
            return 'Technique'
    window[-1] = 0
    return 'Rest'


def apply_acwr_guardrail(
    categories: list[str], recent_daily_loads: list[float], config: PlanConfig,
    effort_overrides: Optional[dict[str, float]] = None,
) -> list[str]:
    """Simulates rolling ACWR day by day from recent_daily_loads and
    downgrades any day that would exceed the threshold."""
    window = list(recent_daily_loads[-config.ACWR_CHRONIC_WINDOW:])
    result = []
    for category in categories:
        window.append((effort_overrides or {}).get(category, config.PLACEHOLDER_EFFORT.get(category, 0)))
        result.append(_downgrade_if_needed(category, window, config, effort_overrides))
    return result


def _category_neglect_scores(df_past: pd.DataFrame) -> dict[str, float]:
    """Per-category neglect score (positive = under-trained/lower-effort)
    for PLANNED_CATEGORIES only, excluding Free/Rest entirely. All zero
    with no history."""
    categories = PlanConfig.PLANNED_CATEGORIES
    if df_past.empty or 'category' not in df_past.columns:
        return {cat: 0.0 for cat in categories}

    sessions = df_past[df_past['category'].isin(categories)]
    if sessions.empty:
        return {cat: 0.0 for cat in categories}

    total = len(sessions)
    effort_sessions = sessions.dropna(subset=['effort'])
    overall_avg_effort = effort_sessions['effort'].mean() if not effort_sessions.empty else 0.0
    expected_share = 1 / len(categories)

    scores = {}
    for cat in categories:
        cat_sessions = sessions[sessions['category'] == cat]
        frequency_component = expected_share - (len(cat_sessions) / total)

        cat_effort_sessions = cat_sessions.dropna(subset=['effort'])
        if not cat_effort_sessions.empty and not effort_sessions.empty:
            effort_component = (overall_avg_effort - cat_effort_sessions['effort'].mean()) / 10
        else:
            effort_component = 0.0

        scores[cat] = (frequency_component + effort_component) / 2
    return scores


def _historical_weeks_per_step(df_past: pd.DataFrame, target_type: str) -> Optional[float]:
    """Average real weeks/grade-level from gaps between first-achieved
    dates; None if fewer than 2 levels are logged."""
    numeric_col = 'gym_numeric' if target_type == 'gym' else 'moonboard_numeric'
    if df_past.empty or numeric_col not in df_past.columns:
        return None
    valid = df_past[df_past[numeric_col] != -1]
    if valid.empty:
        return None

    first_achieved = valid.groupby(numeric_col)['date'].min().sort_index()
    if len(first_achieved) < 2:
        return None

    gaps_in_weeks = first_achieved.diff().dropna().dt.days / 7
    return gaps_in_weeks.mean()


def _category_effort_overrides(df_past: pd.DataFrame) -> dict[str, float]:
    """Average logged effort per category; categories never logged are
    simply absent."""
    if df_past.empty or 'effort' not in df_past.columns or 'category' not in df_past.columns:
        return {}
    logged = df_past.dropna(subset=['effort'])
    if logged.empty:
        return {}
    return logged.groupby('category')['effort'].mean().to_dict()


def _rotate_pick(pool: list[str], key: str, rotation_state: dict[str, int]) -> Optional[str]:
    if not pool:
        return None
    idx = rotation_state.get(key, 0) % len(pool)
    rotation_state[key] = idx + 1
    return pool[idx]


def _bool_col(df: pd.DataFrame, column: str, value) -> pd.Series:
    """Boolean mask for df[column] == value, or all-False if the column
    is missing."""
    if column not in df.columns:
        return pd.Series(False, index=df.index)
    return df[column] == value


def select_exercises_for_day(category: str, df_dict: pd.DataFrame, rotation_state: dict[str, int]) -> dict[str, list[str]]:
    """Exercises for one training day. Mandatory exercises are always
    included; Before/After add one rotating pick on top; During includes
    the entire category-tagged pool. Masks are combined before a single
    .loc lookup to avoid a pandas quirk with filtering already-filtered
    slices."""
    result: dict[str, list[str]] = {'before': [], 'during': [], 'after': []}
    is_mandatory = _bool_col(df_dict, 'mandatory', True)
    is_excluded = _bool_col(df_dict, 'exclude_from_plan', True)

    for key, phase_name in [('before', 'Before'), ('after', 'After')]:
        phase_mask = df_dict['phase'] == phase_name
        mandatory = df_dict.loc[phase_mask & is_mandatory & ~is_excluded, 'name'].tolist()
        rotation_pool = df_dict.loc[phase_mask & ~is_mandatory & ~is_excluded, 'name'].tolist()
        picked = list(mandatory)
        extra = _rotate_pick(rotation_pool, key, rotation_state)
        if extra:
            picked.append(extra)
        result[key] = picked

    during_mask = df_dict['phase'] == 'During'
    category_mask = during_mask & df_dict['categories'].apply(lambda cats: category in (cats or []))
    mandatory_during = df_dict.loc[during_mask & is_mandatory & ~is_excluded, 'name'].tolist()
    category_pool = df_dict.loc[category_mask & ~is_mandatory & ~is_excluded, 'name'].tolist()

    result['during'] = mandatory_during + category_pool

    return result


def _current_best_grade(df_past: pd.DataFrame, target_type: str, config: PipelineConfig) -> Optional[str]:
    """Best (highest-ordinal) grade of the given type logged in df_past, or
    None if nothing's been logged for that system yet."""
    numeric_col = 'gym_numeric' if target_type == 'gym' else 'moonboard_numeric'
    grade_col = 'gym_grade' if target_type == 'gym' else 'moonboard_grade'
    if df_past.empty or numeric_col not in df_past.columns:
        return None
    valid = df_past[df_past[numeric_col] != -1]
    if valid.empty:
        return None
    return valid.loc[valid[numeric_col].idxmax(), grade_col]


def _recent_daily_loads(df_past: pd.DataFrame, window: int = 28) -> list[float]:
    """Daily training load for the last `window` days ending yesterday,
    zero-filled for days with no session."""
    end = pd.to_datetime('today').normalize() - pd.Timedelta(days=1)
    full_range = pd.date_range(end=end, periods=window, freq='D')
    if df_past.empty:
        return [0.0] * window
    sessions_with_effort = df_past.dropna(subset=['effort'])
    if sessions_with_effort.empty:
        return [0.0] * window
    daily = sessions_with_effort.groupby(sessions_with_effort['date'].dt.normalize())['effort'].sum()
    daily = daily.reindex(full_range, fill_value=0.0)
    return daily.tolist()


def _generate_days_for_range(
    phase_breakdown: list[dict], training_weekdays: set[int], start_weekday: int,
    start_day_offset: int, end_day_offset: int,
    recent_daily_loads: list[float], df_dict: pd.DataFrame, config: PlanConfig,
    effort_overrides: Optional[dict[str, float]] = None,
) -> list[dict]:
    """Schedules categories + exercises for [start_day_offset,
    end_day_offset), always recomputed from day 0 for a deterministic
    sequence. training_weekdays map to fixed weekly slots; the final week
    tapers down to only the earliest of those slots."""
    swrr_state: dict[str, float] = {}
    all_categories: list[str] = []
    current_offset = 0
    last_week = phase_breakdown[-1]['end_week']

    training_slots = _training_day_slots(start_weekday, training_weekdays)
    taper_frequency = max(1, round(len(training_weekdays) * (1 - config.TAPER_FREQUENCY_REDUCTION)))
    taper_slots = set(sorted(training_slots)[:taper_frequency])

    for phase in phase_breakdown:
        for week_num in range(phase['start_week'], phase['end_week'] + 1):
            slots_this_week = taper_slots if week_num == last_week else training_slots
            for category in schedule_week(slots_this_week, phase['weights'], swrr_state):
                if start_day_offset <= current_offset < end_day_offset:
                    all_categories.append(category)
                current_offset += 1

    all_categories = apply_acwr_guardrail(all_categories, recent_daily_loads, config, effort_overrides)

    rotation_state: dict[str, int] = {}
    days = []
    for i, category in enumerate(all_categories):
        exercises = (
            {'before': [], 'during': [], 'after': []} if category == 'Rest'
            else select_exercises_for_day(category, df_dict, rotation_state)
        )
        days.append({'day_offset': start_day_offset + i, 'category': category, 'exercises': exercises})
    return days


def generate_plan(
    current_grade: Optional[str], target_type: str, target_grade: str,
    training_weekdays: set[int], start_weekday: int,
    recent_daily_loads: list[float], df_dict: pd.DataFrame, config: Optional[PlanConfig] = None,
    weeks_per_step: Optional[float] = None,
    neglect_scores: Optional[dict[str, float]] = None,
    effort_overrides: Optional[dict[str, float]] = None,
) -> dict:
    """Pure plan generator. start_weekday anchors training_weekdays to
    real slots; weeks_per_step/neglect_scores/effort_overrides are the
    optional personalization inputs, all no-ops by default."""
    if config is None:
        config = PlanConfig()

    grade_mapping = PipelineConfig.GYM_MAPPING if target_type == 'gym' else PipelineConfig.MOONBOARD_MAPPING
    current_ordinal = grade_mapping.get(current_grade, -1)
    target_ordinal = grade_mapping[target_grade]

    total_weeks = compute_plan_length(current_ordinal, target_ordinal, config, weeks_per_step)
    if total_weeks == 0:
        return {'already_at_target': True}

    phase_breakdown = build_phase_breakdown(total_weeks, config, neglect_scores)
    days = _generate_days_for_range(
        phase_breakdown, training_weekdays, start_weekday, 0, total_weeks * 7, recent_daily_loads, df_dict, config,
        effort_overrides,
    )
    return {
        'total_weeks': total_weeks,
        'phase_breakdown': phase_breakdown,
        'days': days,
        'weeks_per_step': weeks_per_step,
        'neglect_scores': neglect_scores or {},
    }


def preview_plan(
    target_type: str, target_grade: str, training_weekdays: set[int],
    df_past: pd.DataFrame, df_dict: pd.DataFrame, config: Optional[PipelineConfig] = None,
) -> dict:
    """Computes what create_goal_and_plan would generate, without
    writing anything."""
    if config is None:
        config = PipelineConfig()
    current_grade = _current_best_grade(df_past, target_type, config)
    weeks_per_step = _historical_weeks_per_step(df_past, target_type)
    neglect_scores = _category_neglect_scores(df_past)
    effort_overrides = _category_effort_overrides(df_past)
    start_weekday = pd.to_datetime('today').normalize().weekday()
    return generate_plan(
        current_grade, target_type, target_grade, training_weekdays, start_weekday,
        _recent_daily_loads(df_past), df_dict,
        weeks_per_step=weeks_per_step, neglect_scores=neglect_scores, effort_overrides=effort_overrides,
    )


def compute_adherence(df_past: pd.DataFrame, goal_id: int) -> dict:
    """Training-day sessions for this goal that should have already
    happened (already in df_past), split into scheduled vs. actually
    logged. Rest days are excluded - they carry no effort and can't be
    "missed"."""
    if df_past.empty:
        return {'scheduled': 0, 'logged': 0}
    goal_sessions = df_past[(df_past['goal_id'] == goal_id) & (df_past['category'] != 'Rest')]
    return {
        'scheduled': len(goal_sessions),
        'logged': int(goal_sessions['effort'].notna().sum()),
    }
