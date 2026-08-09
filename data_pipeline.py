"""
Data pipeline for the Climbing Training Tracker.

Handles all communication with the Supabase Postgres database that backs
the tracker (climbing_training, exercise, training_exercises), validating
and cleaning rows into typed DataFrames, and pushing session/exercise
edits back to the database.
"""

import os
from datetime import date as dt_date, datetime
from typing import Any, Optional

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from supabase import create_client, Client
from pydantic import BaseModel, ValidationError, field_validator


class PipelineConfig:
    """Central place for every constant the pipeline depends on"""

    SESSIONS_TABLE = 'climbing_training'
    EXERCISES_TABLE = 'exercise'
    JUNCTION_TABLE = 'training_exercises'
    EXERCISE_CATEGORIES_TABLE = 'exercise_categories'

    ALLOWED_CATEGORIES = ['Strength', 'Stamina', 'Technique', 'Free', 'Rest']
    ALLOWED_EXERCISE_CATEGORIES = ['Strength', 'Stamina', 'Technique', 'Free']
    ALLOWED_EXERCISE_TYPES = ['Reps', 'Time']
    ALLOWED_PHASES = ['Before', 'During', 'After']

    # Ordinal encodings used for plotting progression over time
    MOONBOARD_MAPPING = {
        'V0': 0, 'V1': 0, 'V2': 1, 'V3': 2, 'V4': 3,
        'V5': 4, 'V6': 5, 'V7': 6, 'V8': 7, 'V9': 8,
        'V10': 9, 'V11': 10, 'V12': 11, 'V13': 12,
        'V14': 13, 'V15': 14, 'V16': 15, 'V17': 16
    }

    GYM_MAPPING = {
        'White': 0, 'Yellow': 1, 'Green': 2, 'Blue': 3,
        'Red': 4, 'Purple': 5, 'Black': 6
    }


# ============================================================
# Validation models
#
# Supabase's REST API returns already-typed JSON rather than raw spreadsheet 
# text, so these are lighter. What's still worth validating: date parsing 
# and membership checks (category/grade/type/phase).
# ============================================================

class SessionRecord(BaseModel):
    """A single validated row from 'climbing_training', plus a synthesized
    'exercises' comma-separated string assembled from the training_exercises join
    """

    id: int
    date_entry: Optional[datetime] = None
    date: dt_date
    category: Optional[str] = None
    effort: Optional[int] = None
    gym_grade: Optional[str] = None
    moonboard_grade: Optional[str] = None
    injured: bool = False
    exercises: Optional[str] = None
    goal_id: Optional[int] = None

    @field_validator('date_entry', mode='before')
    @classmethod
    def parse_date_entry(cls, v):
        if v is None:
            return None
        parsed = pd.to_datetime(v, errors='coerce')
        return None if pd.isna(parsed) else parsed.to_pydatetime()

    @field_validator('date', mode='before')
    @classmethod
    def parse_date(cls, v):
        if v is None:
            raise ValueError('date is required')
        parsed = pd.to_datetime(v, errors='coerce')
        if pd.isna(parsed):
            raise ValueError(f'Unparseable date: {v!r}')
        return parsed.date()

    @field_validator('category', mode='before')
    @classmethod
    def validate_category(cls, v):
        if v is None or str(v).strip() == '':
            return None
        v = str(v).strip()
        if v not in PipelineConfig.ALLOWED_CATEGORIES:
            raise ValueError(f'Unknown category: {v!r}')
        return v

    @field_validator('gym_grade', mode='before')
    @classmethod
    def validate_gym_grade(cls, v):
        if v is None or str(v).strip() == '':
            return None
        v = str(v).strip()
        if v not in PipelineConfig.GYM_MAPPING:
            raise ValueError(f'Unknown gym grade: {v!r}')
        return v

    @field_validator('moonboard_grade', mode='before')
    @classmethod
    def validate_moonboard_grade(cls, v):
        if v is None or str(v).strip() == '':
            return None
        v = str(v).strip()
        if v not in PipelineConfig.MOONBOARD_MAPPING:
            raise ValueError(f'Unknown moonboard grade: {v!r}')
        return v

    @field_validator('exercises', mode='before')
    @classmethod
    def parse_exercises(cls, v):
        if v is None or str(v).strip() == '':
            return None
        return str(v).strip()


class ExerciseRecord(BaseModel):
    """A single validated row from the 'exercise' table"""

    id: int
    name: str
    type: Optional[str] = None
    sets: Optional[int] = None
    reps: Optional[int] = None
    time: Optional[str] = None
    rest: Optional[int] = None
    comments: Optional[str] = None
    phase: Optional[str] = None
    categories: list[str] = []
    mandatory: bool = False
    exclude_from_plan: bool = False

    @field_validator('mandatory', mode='before')
    @classmethod
    def validate_mandatory(cls, v):
        return bool(v)

    @field_validator('exclude_from_plan', mode='before')
    @classmethod
    def validate_exclude_from_plan(cls, v):
        return bool(v)

    @field_validator('categories', mode='before')
    @classmethod
    def validate_categories(cls, v):
        if not v:
            return []
        cleaned = [str(c).strip() for c in v if str(c).strip()]
        invalid = [c for c in cleaned if c not in PipelineConfig.ALLOWED_EXERCISE_CATEGORIES]
        if invalid:
            raise ValueError(f'Unknown exercise categor{"y" if len(invalid) == 1 else "ies"}: {invalid!r}')
        return cleaned

    @field_validator('name', mode='before')
    @classmethod
    def name_required(cls, v):
        if v is None or str(v).strip() == '':
            raise ValueError('Exercise name is required')
        return str(v).strip()

    @field_validator('type', mode='before')
    @classmethod
    def validate_type(cls, v):
        if v is None or str(v).strip() == '':
            return None
        v = str(v).strip()
        if v not in PipelineConfig.ALLOWED_EXERCISE_TYPES:
            raise ValueError(f'Unknown exercise type: {v!r}')
        return v

    @field_validator('phase', mode='before')
    @classmethod
    def validate_phase(cls, v):
        if v is None or str(v).strip() == '':
            return None
        v = str(v).strip()
        if v not in PipelineConfig.ALLOWED_PHASES:
            raise ValueError(f'Unknown phase: {v!r}')
        return v


def _validate_records(records: list[dict], model: type[BaseModel]) -> tuple[list[BaseModel], list[tuple[Any, str]]]:
    """Validate raw Supabase rows against a model.

    Returns (valid, errors):
        valid  - list of validated models (each already carries its own id)
        errors - list of (id, error_message) for rows that failed
    """
    valid = []
    errors = []
    for record in records:
        try:
            valid.append(model.model_validate(record))
        except ValidationError as exc:
            errors.append((record.get('id', '?'), str(exc)))
    return valid, errors


# ============================================================
# Data access layer
#
# Every Supabase call lives behind one of these functions - app.py never
# imports the supabase client directly.
# ============================================================

@st.cache_resource
def _create_supabase_client() -> Client:
    """Build the Supabase client once per process and reuse it. Cached with
    st.cache_resource since re-authenticating on every single read/write
    call is avoidable overhead"""
    load_dotenv()  # no-op if there's no .env file

    try:
        if "supabase" in st.secrets:
            return create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["key"])
    except Exception:
        pass

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError(
            "Supabase credentials not found. Set SUPABASE_URL/SUPABASE_KEY in a .env file "
            "for local dev, or add a [supabase] url/key block to Streamlit secrets in the cloud."
        )
    return create_client(url, key)


def _get_supabase_client(config: Optional['PipelineConfig'] = None) -> Client:
    """Return the shared, cached Supabase client. `config` is accepted (and
    ignored) so every call site can keep passing its PipelineConfig without
    it leaking into the cache key"""
    return _create_supabase_client()


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


def load_clean_data(config: Optional[PipelineConfig] = None):
    """Fetch sessions + exercises from Supabase and return them validated,
    cleaned, and split by date.

    Returns:
        (df_past, df_future, df_dict): completed sessions, upcoming/planned
        sessions, and the exercise library reference table
    """
    if config is None:
        config = PipelineConfig()

    client = _get_supabase_client(config)

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


# --- Session (climbing_training) writes ---

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


def _sync_exercise_categories(exercise_id: int, categories: list[str], config: PipelineConfig, client: Client) -> None:
    """Replace an exercise's category tags with the given list."""
    client.table(config.EXERCISE_CATEGORIES_TABLE).delete().eq('exercise_id', exercise_id).execute()
    rows = [{'exercise_id': exercise_id, 'category': c} for c in categories]
    if rows:
        client.table(config.EXERCISE_CATEGORIES_TABLE).insert(rows).execute()


def update_session(session_id: int, updated_data: dict, config: Optional[PipelineConfig] = None) -> bool:
    """Update an existing session's editable fields"""
    if config is None:
        config = PipelineConfig()
    client = _get_supabase_client(config)

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


def add_session(new_data: dict, config: Optional[PipelineConfig] = None) -> bool:
    """Insert a brand-new session. "injured" defaults to False since new
    sessions are logged without that field"""
    if config is None:
        config = PipelineConfig()
    client = _get_supabase_client(config)

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


def delete_session(session_id: int, config: Optional[PipelineConfig] = None) -> bool:
    """Delete a session by id. training_exercises rows cascade automatically"""
    if config is None:
        config = PipelineConfig()
    client = _get_supabase_client(config)
    try:
        client.table(config.SESSIONS_TABLE).delete().eq('id', session_id).execute()
    except Exception as exc:
        st.error(f"Couldn't delete session: {exc}")
        return False
    return True


# --- Exercise writes ---

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


# ============================================================
# Analytics
#
# Pure functions over already-cleaned DataFrames.
# ============================================================

@st.cache_data
def compute_acwr(df_past: pd.DataFrame, acute_window: int = 7, chronic_window: int = 28) -> pd.DataFrame:
    """Acute:Chronic Workload Ratio - a metric of training
    load trend, used as an injury-risk / readiness signal

    Daily load is the sum of Effort Scale across all sessions on that day.
    Days with no session count as 0 load. `acute` is the rolling mean load
    over the last `acute_window` days (short-term fatigue); `chronic` is
    the rolling mean over the last `chronic_window` days (longer-term
    baseline). ACWR = acute / chronic - commonly cited "sweet spot" in the
    sports-science literature this metric comes from is roughly 0.8-1.3,
    with values above ~1.5 associated with elevated injury risk.

    Returns a DataFrame indexed by date with columns:
    daily_load, acute_load, chronic_load, acwr.
    """
    if df_past.empty:
        return pd.DataFrame(columns=['daily_load', 'acute_load', 'chronic_load', 'acwr'])

    sessions_with_effort = df_past.dropna(subset=['effort'])
    if sessions_with_effort.empty:
        return pd.DataFrame(columns=['daily_load', 'acute_load', 'chronic_load', 'acwr'])

    daily_load = sessions_with_effort.groupby(
        sessions_with_effort['date'].dt.normalize()
    )['effort'].sum()

    full_range = pd.date_range(daily_load.index.min(), daily_load.index.max(), freq='D')
    daily_load = daily_load.reindex(full_range, fill_value=0)
    daily_load.index.name = 'date'

    acute_load = daily_load.rolling(window=acute_window, min_periods=1).mean()
    chronic_load = daily_load.rolling(window=chronic_window, min_periods=1).mean()
    acwr = (acute_load / chronic_load).where(chronic_load > 0)

    return pd.DataFrame({
        'daily_load': daily_load,
        'acute_load': acute_load,
        'chronic_load': chronic_load,
        'acwr': acwr,
    })


def compute_kpis(df_past: pd.DataFrame) -> dict:
    """Snapshot KPIs for the top-of-page summary strip.

    Returns a dict with:
        streak: consecutive days up to the most recently logged day that
            have a non-Rest session (0 if none)
        sessions_this_week: non-Rest sessions logged since the most
            recent Monday
        acwr_current / acwr_delta: latest ACWR value and its change from
            the previous day with a computable ACWR (None if not enough
            training history yet)
        days_since_last: days since the most recently logged session of
            any category (None if nothing has been logged)
    """
    empty_result = {
        'streak': 0, 'sessions_this_week': 0,
        'acwr_current': None, 'acwr_delta': None, 'days_since_last': None,
    }

    dated = df_past.dropna(subset=['date']) if not df_past.empty else df_past
    if dated.empty:
        return empty_result

    today = pd.to_datetime('today').normalize()
    last_date = dated['date'].max().normalize()

    week_start = today - pd.Timedelta(days=today.weekday())
    sessions_this_week = dated[
        (dated['date'] >= week_start) & (dated['category'] != 'Rest')
    ].shape[0]

    non_rest_days = set(dated[dated['category'] != 'Rest']['date'].dt.normalize())
    streak = 0
    cursor = last_date
    while cursor in non_rest_days:
        streak += 1
        cursor -= pd.Timedelta(days=1)

    acwr_df = compute_acwr(df_past)
    acwr_series = acwr_df['acwr'].dropna() if not acwr_df.empty else pd.Series(dtype=float)
    acwr_current = float(acwr_series.iloc[-1]) if not acwr_series.empty else None
    acwr_delta = (
        float(acwr_series.iloc[-1] - acwr_series.iloc[-2])
        if len(acwr_series) >= 2 else None
    )

    return {
        'streak': streak,
        'sessions_this_week': int(sessions_this_week),
        'acwr_current': acwr_current,
        'acwr_delta': acwr_delta,
        'days_since_last': int((today - last_date).days),
    }


def get_peak_sessions(df: pd.DataFrame, n: int = 3) -> pd.DataFrame:
    """Rank sessions by a "how strong was this session" composite score and
    return the top n, with effort as a tiebreaker. Rest days are excluded.
    """
    if df.empty:
        return df.assign(score=pd.Series(dtype=float))

    ranked = df[df['category'] != 'Rest'].copy()
    if ranked.empty:
        return ranked.assign(score=pd.Series(dtype=float))

    ranked['score'] = (
        ranked['gym_numeric'].clip(lower=0)
        + ranked['moonboard_numeric'].clip(lower=0)
        + ranked['effort'].fillna(0) / 10
    )
    return ranked.sort_values('score', ascending=False).head(n)


if __name__ == "__main__":
    # Quick manual smoke test when running this file directly
    past, future, exercises = load_clean_data()
    print(f"Found {len(past)} completed sessions and {len(future)} planned sessions")
    print("\n--- Processed Past Sessions Preview ---")
    print(past.head())