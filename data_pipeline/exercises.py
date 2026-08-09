"""
Supabase writes for the exercise reference table and its category tags.
"""

from typing import Optional

import streamlit as st
from supabase import Client

from .client import _get_supabase_client
from .cleaning import _clean_write_value
from .models import PipelineConfig


def _sync_exercise_categories(exercise_id: int, categories: list[str], config: PipelineConfig, client: Client) -> None:
    """Replace an exercise's category tags with the given list."""
    client.table(config.EXERCISE_CATEGORIES_TABLE).delete().eq('exercise_id', exercise_id).execute()
    rows = [{'exercise_id': exercise_id, 'category': c} for c in categories]
    if rows:
        client.table(config.EXERCISE_CATEGORIES_TABLE).insert(rows).execute()


def add_exercise(new_data: dict, config: Optional[PipelineConfig] = None) -> bool:
    """Insert a brand-new exercise"""
    if config is None:
        config = PipelineConfig()
    client = _get_supabase_client(config)

    name = _clean_write_value(new_data.get('Name'))
    if not name:
        return False

    payload = {
        'name': name,
        'type': _clean_write_value(new_data.get('Type')),
        'sets': _clean_write_value(new_data.get('Sets')),
        'reps': _clean_write_value(new_data.get('Reps')),
        'time': _clean_write_value(new_data.get('Time')),
        'rest': _clean_write_value(new_data.get('Rest')),
        'comments': _clean_write_value(new_data.get('Comments')),
        'phase': _clean_write_value(new_data.get('Phase')),
        'mandatory': bool(new_data.get('Mandatory', False)),
        'exclude_from_plan': bool(new_data.get('ExcludeFromPlan', False)),
    }
    try:
        response = client.table(config.EXERCISES_TABLE).insert(payload).execute()
    except Exception as exc:
        st.error(f"Couldn't create exercise: {exc}")
        return False

    if response.data:
        try:
            _sync_exercise_categories(response.data[0]['id'], new_data.get('Categories') or [], config, client)
        except Exception as exc:
            st.warning(f"Exercise created, but its categories couldn't be saved: {exc}")
    return True


def update_exercise(exercise_id: int, updated_data: dict, config: Optional[PipelineConfig] = None) -> bool:
    """Update specific fields of an existing exercise"""
    if config is None:
        config = PipelineConfig()
    client = _get_supabase_client(config)

    field_map = {
        'Name': 'name', 'Type': 'type', 'Sets': 'sets', 'Reps': 'reps',
        'Time': 'time', 'Rest': 'rest', 'Comments': 'comments', 'Phase': 'phase',
        'Mandatory': 'mandatory', 'ExcludeFromPlan': 'exclude_from_plan',
    }
    payload = {
        field_map[k]: _clean_write_value(v)
        for k, v in updated_data.items()
        if k in field_map
    }
    try:
        if payload:
            client.table(config.EXERCISES_TABLE).update(payload).eq('id', exercise_id).execute()
    except Exception as exc:
        st.error(f"Couldn't save exercise: {exc}")
        return False

    if 'Categories' in updated_data:
        try:
            _sync_exercise_categories(exercise_id, updated_data.get('Categories') or [], config, client)
        except Exception as exc:
            st.warning(f"Exercise saved, but its categories couldn't be updated: {exc}")
    return True


def delete_exercise(exercise_id: int, config: Optional[PipelineConfig] = None) -> bool:
    """Delete an exercise by id. Linked training_exercises rows cascade automatically"""
    if config is None:
        config = PipelineConfig()
    client = _get_supabase_client(config)
    try:
        client.table(config.EXERCISES_TABLE).delete().eq('id', exercise_id).execute()
    except Exception as exc:
        st.error(f"Couldn't delete exercise: {exc}")
        return False
    return True
