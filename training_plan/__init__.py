"""
Training plan generation for the Climbing Training Tracker.

Given a grade goal, generates a deterministic, phased (Base -> Build ->
Peak/Taper) weekly training schedule, guarded against overtraining via the
app's existing ACWR metric, with specific exercises prescribed per day.
Generation is a pure function of its inputs - no randomness - so the same
goal parameters always produce the same plan.

Split into algorithm.py (pure generation) and store.py (Supabase
persistence) internally; this file re-exports the full public surface so
`from training_plan import X` keeps working exactly as it did when this
was a single module.
"""

from .algorithm import (
    PlanConfig, GoalRecord, compute_plan_length, build_phase_breakdown, schedule_week,
    apply_acwr_guardrail, select_exercises_for_day, generate_plan, preview_plan,
    compute_adherence,
    _adjust_weights_for_neglect, _training_day_slots, _swrr_pick, _simulated_acwr,
    _downgrade_if_needed, _category_neglect_scores,
    _category_effort_overrides, _rotate_pick, _bool_col, _current_best_grade, _current_achieved_grade,
    _recent_daily_loads, _generate_days_for_range,
)
from .store import (
    get_active_goal, create_goal_and_plan, regenerate_plan, abandon_goal,
    check_and_update_goal_completion, _existing_session_dates, _write_scheduled_sessions,
)
