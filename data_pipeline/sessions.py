"""
Supabase writes for individual training sessions (climbing_training rows)
and their linked exercises.
"""

from datetime import datetime
from typing import Optional

import streamlit as st
from supabase import Client

from .cleaning import _clean_write_value, _to_iso_date
from .models import PipelineConfig


def _sync_session_exercises(session_id: int, exercises_str: Optional[str], config: PipelineConfig, client: Client) -> None:
    """Replace a sessions linked exercises with the given comma-separated
    list of names. Clears existing links and re-creates them"""
    client.table(config.JUNCTION_TABLE).delete().eq('training_id', session_id).execute()

    names = [n.strip() for n in (exercises_str or '').split(',') if n.strip()]
    if not names:
        return

    lookup = client.table(config.EXERCISES_TABLE).select('id, name').in_('name', names).execute()
    name_to_id = {row['name']: row['id'] for row in lookup.data}

    unmatched = [n for n in names if n not in name_to_id]
    if unmatched:
        st.warning(f"These exercises weren't found in your Exercise Library and weren't linked to this session: {unmatched}")

    junction_rows = [{'training_id': session_id, 'exercise_id': name_to_id[n]} for n in names if n in name_to_id]
    if junction_rows:
        client.table(config.JUNCTION_TABLE).insert(junction_rows).execute()


def update_session(client: Client, session_id: int, updated_data: dict, config: Optional[PipelineConfig] = None) -> bool:
    """Update an existing session's editable fields"""
    if config is None:
        config = PipelineConfig()

    field_map = {
        'Category': 'category',
        'Effort Scale': 'effort',
        'Max Gym Grade Color': 'gym_grade',
        'Max Moonboard Grade': 'moonboard_grade',
    }
    payload = {
        field_map[k]: _clean_write_value(v)
        for k, v in updated_data.items()
        if k in field_map
    }
    try:
        if payload:
            client.table(config.SESSIONS_TABLE).update(payload).eq('id', session_id).execute()

        if 'Exercises' in updated_data:
            _sync_session_exercises(session_id, updated_data.get('Exercises'), config, client)
    except Exception as exc:
        st.error(f"Couldn't save changes: {exc}")
        return False

    return True


def add_session(client: Client, new_data: dict, config: Optional[PipelineConfig] = None) -> bool:
    """Insert a brand-new session. "injured" defaults to False since new
    sessions are logged without that field"""
    if config is None:
        config = PipelineConfig()

    session_payload = {
        'date_entry': datetime.now().isoformat(),
        'date': _to_iso_date(new_data.get('Date')),
        'category': _clean_write_value(new_data.get('Category')),
        'effort': _clean_write_value(new_data.get('Effort Scale')),
        'gym_grade': _clean_write_value(new_data.get('Max Gym Grade Color')),
        'moonboard_grade': _clean_write_value(new_data.get('Max Moonboard Grade')),
        'injured': False,
    }
    try:
        response = client.table(config.SESSIONS_TABLE).insert(session_payload).execute()
        if not response.data:
            return False

        session_id = response.data[0]['id']
        _sync_session_exercises(session_id, new_data.get('Exercises'), config, client)
    except Exception as exc:
        st.error(f"Couldn't log session: {exc}")
        return False

    return True


def delete_session(client: Client, session_id: int, config: Optional[PipelineConfig] = None) -> bool:
    """Delete a session by id. training_exercises rows cascade automatically"""
    if config is None:
        config = PipelineConfig()
    try:
        client.table(config.SESSIONS_TABLE).delete().eq('id', session_id).execute()
    except Exception as exc:
        st.error(f"Couldn't delete session: {exc}")
        return False
    return True
