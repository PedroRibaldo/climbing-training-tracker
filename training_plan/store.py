"""
Supabase persistence for grade goals - creating, regenerating, abandoning,
and completing them, built on top of the pure algorithm in algorithm.py.
"""

from datetime import datetime
from typing import Optional

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from data_pipeline import PipelineConfig
from .algorithm import (
    PlanConfig, GoalRecord, preview_plan, _category_effort_overrides,
    _generate_days_for_range, _recent_daily_loads,
)


def get_active_goal(client, config: Optional[PipelineConfig] = None) -> Optional[dict]:
    """The current active goal, or None if there isn't one."""
    if config is None:
        config = PipelineConfig()
    response = client.table(PlanConfig.GOALS_TABLE).select('*').eq('status', 'active').limit(1).execute()
    if not response.data:
        return None
    try:
        return GoalRecord.model_validate(response.data[0]).model_dump()
    except ValidationError as exc:
        st.warning(f"Your active goal row has invalid data and was ignored: {exc}")
        return None


def _existing_session_dates(df_future: pd.DataFrame) -> set:
    """Dates that already have a session, so generation skips them."""
    if df_future.empty or 'date' not in df_future.columns:
        return set()
    return set(df_future['date'].dropna().dt.normalize())


def _write_scheduled_sessions(
    days_to_create: list[dict], date_base: pd.Timestamp, goal_id: int,
    df_dict: pd.DataFrame, config: PipelineConfig, client,
) -> None:
    """Bulk-inserts sessions and their exercise junction rows for
    days_to_create; shared by create_goal_and_plan and regenerate_plan."""
    if not days_to_create:
        return

    session_payloads = [
        {
            'date_entry': datetime.now().isoformat(),
            'date': (date_base + pd.Timedelta(days=day['day_offset'])).strftime('%Y-%m-%d'),
            'category': day['category'],
            'injured': False,
            'goal_id': goal_id,
        }
        for day in days_to_create
    ]
    sessions_response = client.table(config.SESSIONS_TABLE).insert(session_payloads).execute()

    name_to_id = dict(zip(df_dict['name'], df_dict['id']))
    junction_rows = [
        {'training_id': session_row['id'], 'exercise_id': name_to_id[name]}
        for day, session_row in zip(days_to_create, sessions_response.data)
        for name in day['exercises']['before'] + day['exercises']['during'] + day['exercises']['after']
        if name in name_to_id
    ]
    if junction_rows:
        client.table(config.JUNCTION_TABLE).insert(junction_rows).execute()


def create_goal_and_plan(
    client, current_grade: Optional[str], target_type: str, target_grade: str, training_weekdays: set[int],
    df_past: pd.DataFrame, df_future: pd.DataFrame, df_dict: pd.DataFrame, config: Optional[PipelineConfig] = None,
) -> bool:
    """Creates a goal and its scheduled sessions, skipping days that
    already have one."""
    if config is None:
        config = PipelineConfig()

    plan = preview_plan(current_grade, target_type, target_grade, training_weekdays, df_past, df_dict, config)
    if plan.get('already_at_target'):
        st.warning(f"You've already reached {target_grade} for {target_type} - no plan needed.")
        return False

    today = pd.to_datetime('today').normalize()
    existing_dates = _existing_session_dates(df_future)
    days_to_create = [
        day for day in plan['days']
        if (today + pd.Timedelta(days=day['day_offset'])) not in existing_dates
    ]
    skipped = len(plan['days']) - len(days_to_create)

    try:
        goal_response = client.table(PlanConfig.GOALS_TABLE).insert({
            'target_type': target_type,
            'target_grade': target_grade,
            'start_grade': current_grade,
            'weekly_frequency': len(training_weekdays),
            'training_weekdays': [PlanConfig.WEEKDAY_NAMES[i] for i in sorted(training_weekdays)],
            'total_weeks': plan['total_weeks'],
            'phase_breakdown': plan['phase_breakdown'],
            'status': 'active',
        }).execute()
        if not goal_response.data:
            st.error("Couldn't create the goal - no confirmation came back from the database.")
            return False
        goal_id = goal_response.data[0]['id']
        _write_scheduled_sessions(days_to_create, today, goal_id, df_dict, config, client)
    except Exception as exc:
        st.error(f"Couldn't create the plan: {exc}")
        return False

    if skipped:
        st.info(f"{skipped} day(s) in the plan already had a session logged and were left as-is.")
    return True


def regenerate_plan(
    client, goal: dict, df_past: pd.DataFrame, df_future: pd.DataFrame, df_dict: pd.DataFrame,
    config: Optional[PipelineConfig] = None,
) -> bool:
    """Re-rolls the remaining, unlogged portion of an active goal's plan
    using its stored phase_breakdown."""
    if config is None:
        config = PipelineConfig()

    created_at = pd.to_datetime(goal['created_at']).normalize()
    today = pd.to_datetime('today').normalize()
    elapsed_offset = max(0, (today - created_at).days)
    total_days = goal['total_weeks'] * 7

    if elapsed_offset >= total_days:
        st.warning("This plan has already run its full length - nothing left to regenerate.")
        return False

    try:
        to_delete_mask = (df_future['goal_id'] == goal['id']) & df_future['effort'].isna()
        delete_ids = df_future.loc[to_delete_mask, 'id'].dropna().astype(int).tolist()
        if delete_ids:
            client.table(config.SESSIONS_TABLE).delete().in_('id', delete_ids).execute()

        training_weekdays = {PlanConfig.WEEKDAY_NAMES.index(name) for name in goal['training_weekdays']}
        effort_overrides = _category_effort_overrides(df_past)
        days = _generate_days_for_range(
            goal['phase_breakdown'], training_weekdays, created_at.weekday(),
            elapsed_offset, total_days, _recent_daily_loads(df_past), df_dict, PlanConfig(),
            effort_overrides,
        )

        # Exclude the just-deleted rows so freeing their slots isn't a collision.
        existing_dates = _existing_session_dates(df_future.loc[~to_delete_mask])
        days_to_create = [
            day for day in days
            if (created_at + pd.Timedelta(days=day['day_offset'])) not in existing_dates
        ]
        skipped = len(days) - len(days_to_create)

        _write_scheduled_sessions(days_to_create, created_at, goal['id'], df_dict, config, client)
    except Exception as exc:
        st.error(f"Couldn't regenerate the plan: {exc}")
        return False

    if skipped:
        st.info(f"{skipped} day(s) in the plan already had a session logged and were left as-is.")

    return True


def abandon_goal(client, goal_id: int, df_future: pd.DataFrame, config: Optional[PipelineConfig] = None) -> bool:
    """Marks a goal abandoned and deletes its future, not-yet-logged
    sessions. Already-logged sessions (real training history) are never
    touched."""
    if config is None:
        config = PipelineConfig()
    try:
        client.table(PlanConfig.GOALS_TABLE).update({'status': 'abandoned'}).eq('id', goal_id).execute()
        to_delete_mask = (df_future['goal_id'] == goal_id) & df_future['effort'].isna()
        delete_ids = df_future.loc[to_delete_mask, 'id'].dropna().astype(int).tolist()
        if delete_ids:
            client.table(config.SESSIONS_TABLE).delete().in_('id', delete_ids).execute()
    except Exception as exc:
        st.error(f"Couldn't abandon the goal: {exc}")
        return False
    return True


def check_and_update_goal_completion(
    client, goal: dict, current_grade: Optional[str], df_future: pd.DataFrame, config: Optional[PipelineConfig] = None,
) -> bool:
    """Marks the goal completed and cleans up remaining sessions if the
    target grade's been reached. Returns True if it just changed."""
    if config is None:
        config = PipelineConfig()
    grade_mapping = PipelineConfig.GYM_MAPPING if goal['target_type'] == 'gym' else PipelineConfig.MOONBOARD_MAPPING
    target_ordinal = grade_mapping[goal['target_grade']]
    current_ordinal = grade_mapping.get(current_grade, -1)
    if current_ordinal < target_ordinal:
        return False

    try:
        client.table(PlanConfig.GOALS_TABLE).update({'status': 'completed'}).eq('id', goal['id']).execute()
        to_delete_mask = (df_future['goal_id'] == goal['id']) & df_future['effort'].isna()
        delete_ids = df_future.loc[to_delete_mask, 'id'].dropna().astype(int).tolist()
        if delete_ids:
            client.table(config.SESSIONS_TABLE).delete().in_('id', delete_ids).execute()
    except Exception as exc:
        st.error(f"Couldn't update goal status: {exc}")
        return False
    return True
