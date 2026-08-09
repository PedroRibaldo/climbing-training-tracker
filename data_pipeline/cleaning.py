"""
Fetching, flattening, and validating Supabase rows into clean DataFrames.
"""

from typing import Any, Optional

import pandas as pd
import streamlit as st

from .models import PipelineConfig, SessionRecord, ExerciseRecord, _validate_records


def _clean_write_value(v: Any) -> Any:
    """Normalize a value before sending it to Supabase: blanks become None
    so the database gets NULL instead of an empty string"""
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    if isinstance(v, str) and v.strip() == '':
        return None
    return v


def _to_iso_date(date_str: Optional[str]) -> Optional[str]:
    """Convert the apps DD/MM/YYYY display format to the ISO date string
    Postgres DATE columns expect."""
    if not date_str:
        return None
    parsed = pd.to_datetime(date_str, dayfirst=True, errors='coerce')
    return None if pd.isna(parsed) else parsed.date().isoformat()


def _flatten_session_row(row: dict) -> dict:
    """Supabase returns each session with a nested training_exercises list.
    Flatten that into a single comma-separated 'exercises' string, matching the shape the rest of the app has always worked with"""
    names = [
        te['exercise']['name']
        for te in (row.get('training_exercises') or [])
        if te.get('exercise')
    ]
    flat = {k: v for k, v in row.items() if k != 'training_exercises'}
    flat['exercises'] = ', '.join(names) if names else None
    return flat


def _flatten_exercise_row(row: dict) -> dict:
    """Supabase returns each exercise with a nested exercise_categories list
    (via the embedded join). Flatten that into a plain 'categories' list of
    strings, matching the shape ExerciseRecord expects."""
    categories = [
        ec['category']
        for ec in (row.get('exercise_categories') or [])
        if ec.get('category')
    ]
    flat = {k: v for k, v in row.items() if k != 'exercise_categories'}
    flat['categories'] = categories
    return flat


def load_clean_data(client, config: Optional[PipelineConfig] = None):
    """Fetch sessions + exercises from Supabase and return them validated,
    cleaned, and split by date.

    Returns:
        (df_past, df_future, df_dict): completed sessions, upcoming/planned
        sessions, and the exercise library reference table
    """
    if config is None:
        config = PipelineConfig()

    session_response = client.table(config.SESSIONS_TABLE).select(
        '*, training_exercises(exercise(name))'
    ).execute()
    exercise_response = client.table(config.EXERCISES_TABLE).select(
        '*, exercise_categories(category)'
    ).execute()

    main_records = [_flatten_session_row(row) for row in session_response.data]
    dict_records = [_flatten_exercise_row(row) for row in exercise_response.data]

    return clean_data(main_records, dict_records, config)


def clean_data(main_records: list[dict], dict_records: list[dict], config: PipelineConfig):
    """Validate raw rows and split sessions into past vs. future.

    main_records / dict_records are plain dicts shaped like Supabase's
    response rows.

    Rows that fail validation are skipped rather than crashing the whole
    dashboard.
    """
    valid_sessions, session_errors = _validate_records(main_records, SessionRecord)
    valid_exercises, exercise_errors = _validate_records(dict_records, ExerciseRecord)

    if session_errors:
        st.warning(f"Skipped {len(session_errors)} invalid session row(s) "
                   f"(id {[i for i, _ in session_errors]}). Check that row in Supabase.")
    if exercise_errors:
        st.warning(f"Skipped {len(exercise_errors)} invalid exercise row(s) "
                   f"(id {[i for i, _ in exercise_errors]}). Check that row in Supabase.")

    df_main = pd.DataFrame([m.model_dump() for m in valid_sessions])
    df_dict = pd.DataFrame([m.model_dump() for m in valid_exercises])

    if df_main.empty:
        df_main = pd.DataFrame(columns=list(SessionRecord.model_fields.keys()))

    df_main['date'] = pd.to_datetime(df_main['date'])
    if 'date_entry' in df_main.columns:
        df_main['date_entry'] = pd.to_datetime(df_main['date_entry'])

    # Numeric encodings for plotting, kept alongside the original text
    # columns (moonboard_grade / gym_grade) so tooltips can still show
    # the human-readable grade
    df_main['moonboard_numeric'] = df_main['moonboard_grade'].map(config.MOONBOARD_MAPPING).fillna(-1)
    df_main['gym_numeric'] = df_main['gym_grade'].map(config.GYM_MAPPING).fillna(-1)

    today = pd.to_datetime('today').floor('D')

    df_past = df_main[df_main['date'] < today].copy()
    df_future = df_main[df_main['date'] >= today].copy()

    return df_past, df_future, df_dict
