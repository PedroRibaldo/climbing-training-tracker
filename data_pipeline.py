"""
Data pipeline for the Climbing Training Tracker.

Handles all communication with the Google Sheet that backs the tracker:
- Pulling raw form/log data and cleaning it into typed DataFrames.
- Pushing edits, new sessions, and deletions back to the sheet.

The Streamlit app (app.py) only talks to Google Sheets through this module.
"""

from typing import Any, Optional
from datetime import date as dt_date, datetime

import numpy as np
import pandas as pd
import gspread
import streamlit as st
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class PipelineConfig:
    """Central place for every constant the pipeline depends on.

    Keeping these here (instead of scattered through the code) means the
    Google Sheet's column names/order can change in one place without
    touching the cleaning or writing logic below.
    """

    SPREADSHEET_NAME = 'Climbing Tracker'
    CREDENTIALS = 'credentials.json'

    ALLOWED_CATEGORIES = ['Strength', 'Stamina', 'Technique', 'Free', 'Rest']
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

    # 1-indexed column positions in the 'Main_Log' worksheet, used when
    # writing single-cell updates back to Google Sheets
    SESSION_COL_MAPPING = {
        'Category': 3,
        'Effort Scale': 4,
        'Max Gym Grade Color': 5,
        'Max Moonboard Grade': 6,
        'Exercises': 8
    }

    # 1-indexed column positions in 'Exercise_Dictionary'
    EXERCISE_COL_MAPPING = {
        'Name': 1,
        'Type': 2,
        'Sets': 3,
        'Reps/Time': 4,
        'Rest': 5,
        'Comments': 6,
        'Phase': 7
    }

# ============================================================
# Validation models
#
# These are the single source of truth for what a valid row looks like.
# Field aliases map directly to the raw Google Sheet column headers, so
# rows can be validated immediately after get_all_records(), before any
# pandas involvement
# ============================================================

class SessionRecord(BaseModel):
    """A single validated row from 'Main_Log'"""
    model_config = ConfigDict(populate_by_name=True)
 
    date_entry: Optional[datetime] = Field(default=None, alias='Carimbo de data/hora')
    date: dt_date = Field(alias='Date')
    category: Optional[str] = Field(default=None, alias='Category')
    effort: Optional[int] = Field(default=None, alias='Effort Scale')
    gym_grade: Optional[str] = Field(default=None, alias='Max Gym Grade Color')
    moonboard_grade: Optional[str] = Field(default=None, alias='Max Moonboard Grade')
    injured: bool = Field(default=False, alias='Injuries / Tweaks')
    exercises: Optional[str] = Field(default=None, alias='Exercises')
 
    @field_validator('date_entry', mode='before')
    @classmethod
    def parse_date_entry(cls, v):
        if v is None or str(v).strip() == '':
            return None
        parsed = pd.to_datetime(str(v).strip(), dayfirst=True, errors='coerce')
        return None if pd.isna(parsed) else parsed.to_pydatetime()
 
    @field_validator('date', mode='before')
    @classmethod
    def parse_date(cls, v):
        if v is None or str(v).strip() == '':
            raise ValueError('date is required')
        parsed = pd.to_datetime(str(v).strip(), dayfirst=True, errors='coerce')
        if pd.isna(parsed):
            raise ValueError(f'Unparseable date: {v!r}')
        return parsed.date()
 
    @field_validator('category', mode='before')
    @classmethod
    def parse_category(cls, v):
        if v is None or str(v).strip() == '':
            return None
        v = str(v).strip()
        if v not in PipelineConfig.ALLOWED_CATEGORIES:
            raise ValueError(f'Unknown category: {v!r}')
        return v
 
    @field_validator('effort', mode='before')
    @classmethod
    def parse_effort(cls, v):
        if v is None or str(v).strip() == '':
            return None
        return int(v)
 
    @field_validator('gym_grade', mode='before')
    @classmethod
    def parse_gym_grade(cls, v):
        if v is None or str(v).strip() == '':
            return None
        v = str(v).strip()
        if v not in PipelineConfig.GYM_MAPPING:
            raise ValueError(f'Unknown gym grade: {v!r}')
        return v
 
    @field_validator('moonboard_grade', mode='before')
    @classmethod
    def parse_moonboard_grade(cls, v):
        if v is None or str(v).strip() == '':
            return None
        v = str(v).strip()
        if v not in PipelineConfig.MOONBOARD_MAPPING:
            raise ValueError(f'Unknown moonboard grade: {v!r}')
        return v
 
    @field_validator('injured', mode='before')
    @classmethod
    def parse_injured(cls, v):
        if isinstance(v, bool):
            return v
        if v is None or str(v).strip() == '':
            return False
        return str(v).strip().lower() == 'yes'
 
    @field_validator('exercises', mode='before')
    @classmethod
    def parse_exercises(cls, v):
        if v is None or str(v).strip() == '':
            return None
        return str(v).strip()


class ExerciseRecord(BaseModel):
    """A single validated row from 'Exercise_Dictionary'"""
    model_config = ConfigDict(populate_by_name=True)
 
    name: str = Field(alias='Name')
    type: Optional[str] = Field(default=None, alias='Type')
    sets: Optional[int] = Field(default=None, alias='Sets')
    reps: Optional[str] = Field(default=None, alias='Reps/Time')
    rest: Optional[int] = Field(default=None, alias='Rest')
    comments: Optional[str] = Field(default=None, alias='Comments')
    # Existing rows without phase simply validate as None until backfilled.
    phase: Optional[str] = Field(default=None, alias='Phase')
 
    @field_validator('name', mode='before')
    @classmethod
    def name_required(cls, v):
        if v is None or str(v).strip() == '':
            raise ValueError('Exercise name is required')
        return str(v).strip()
 
    @field_validator('type', mode='before')
    @classmethod
    def parse_type(cls, v):
        if v is None or str(v).strip() == '':
            return None
        v = str(v).strip()
        if v not in PipelineConfig.ALLOWED_EXERCISE_TYPES:
            raise ValueError(f'Unknown exercise type: {v!r}')
        return v
 
    @field_validator('sets', 'rest', mode='before')
    @classmethod
    def parse_optional_int(cls, v):
        if v is None or str(v).strip() == '':
            return None
        return int(v)
 
    @field_validator('reps', 'comments', mode='before')
    @classmethod
    def parse_optional_str(cls, v):
        if v is None or str(v).strip() == '':
            return None
        return str(v).strip()
 
    @field_validator('phase', mode='before')
    @classmethod
    def parse_phase(cls, v):
        if v is None or str(v).strip() == '':
            return None
        v = str(v).strip()
        if v not in PipelineConfig.ALLOWED_PHASES:
            raise ValueError(f'Unknown phase: {v!r}')
        return v


def _validate_records(records: list[dict], model: type[BaseModel]) -> tuple[list[tuple[int, BaseModel]], list[tuple[int, str]]]:
    """Validate raw sheet rows (as returned by get_all_records()) against a model
 
    Returns (valid, errors):
        valid  - list of (gsheet_row, validated_model) for rows that passed
        errors - list of (gsheet_row, error_message) for rows that failed
 
    Row numbers assume row 1 is the header, matching Google Sheets own
    numbering (row 2 = the first data row).
    """
    valid = []
    errors = []
    for i, record in enumerate(records):
        gsheet_row = i + 2
        try:
            valid.append((gsheet_row, model.model_validate(record)))
        except ValidationError as exc:
            errors.append((gsheet_row, str(exc)))
    return valid, errors


# ============================================================
# Data access layer
#
# Every gspread call lives behind one of these functions. app.py (and any
# future caller) only ever imports from here - it never talks to gspread
# directly
# ============================================================

def _get_google_client(config: 'PipelineConfig') -> gspread.Client:
    """Authenticate and return the gspread client based on the environment"""
    try:
        # If running in Streamlit Cloud, grab credentials from the secrets manager
        if "gcp_service_account" in st.secrets:
            return gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    except Exception:
        pass

    # Otherwise, fallback to the local JSON file
    return gspread.service_account(filename=config.CREDENTIALS)


def _open_worksheet(config: 'PipelineConfig', sheet_name: str) -> gspread.Worksheet:
    """Authenticate and return a handle to a worksheet in the tracker spreadsheet."""
    gc = _get_google_client(config)
    return gc.open(config.SPREADSHEET_NAME).worksheet(sheet_name)


def _to_sheet_safe_str(value: Any) -> str:
    """Convert a value for writing to a Google Sheets cell.

    Null-like values (None, NaN, pd.NA) become an empty string so gspread
    doesn't choke on them; everything else is stringified as-is.
    """
    return "" if pd.isna(value) or value is None else str(value)


def load_clean_data(config: Optional[PipelineConfig] = None):
    """Fetch the raw sheet data and return it cleaned and split by date.

    Returns:
        (df_past, df_future, df_dict): completed sessions, upcoming/planned
        sessions, and the exercise dictionary reference table.
    """
    if config is None:
        config = PipelineConfig()

    gc = _get_google_client(config)
    spreadsheet = gc.open(config.SPREADSHEET_NAME)

    main_records = spreadsheet.worksheet('Main_Log').get_all_records()
    dict_records = spreadsheet.worksheet('Exercise_Dictionary').get_all_records()

    return clean_data(main_records, dict_records, config)


def clean_data(main_records: list[dict], dict_records: list[dict], config: PipelineConfig):
    """Validate raw sheet rows and split sessions into past vs. future
 
    main_records / dict_records are exactly what worksheet.get_all_records() returns
 
    Rows that fail validation are skipped rather than crashing the whole dashboard
    """
    # Strip trailing/leading spaces from the Google Sheet column headers
    clean_main = [{str(k).strip(): v for k, v in row.items()} for row in main_records]
    clean_dict = [{str(k).strip(): v for k, v in row.items()} for row in dict_records]

    valid_sessions, session_errors = _validate_records(clean_main, SessionRecord)
    valid_exercises, exercise_errors = _validate_records(clean_dict, ExerciseRecord)
 
    if session_errors:
        st.warning(f"Skipped {len(session_errors)} invalid row(s) in Main_Log "
                   f"(rows {[row for row, _ in session_errors]}). Check for typos")
    if exercise_errors:
        st.warning(f"Skipped {len(exercise_errors)} invalid row(s) in Exercise_Dictionary "
                   f"(rows {[row for row, _ in exercise_errors]}). Check for typos")
 
    df_main = pd.DataFrame([
        {**model.model_dump(), 'gsheet_row': row} for row, model in valid_sessions
    ])
    df_dict = pd.DataFrame([
        {**model.model_dump(), 'gsheet_row': row} for row, model in valid_exercises
    ])

    if df_main.empty:
        df_main = pd.DataFrame(columns=list(SessionRecord.model_fields.keys()) + ['gsheet_row'])

    df_main['date'] = pd.to_datetime(df_main['date'])
    if 'date_entry' in df_main.columns:
        df_main['date_entry'] = pd.to_datetime(df_main['date_entry'])

    # Numeric encodings for plotting, kept alongside the original text
    # columns (moonboard_grade / gym_grade) so tooltips can still show
    # the human-readable grade
    df_main['moonboard_numeric'] = df_main['moonboard_grade'].map(config.MOONBOARD_MAPPING).fillna(-1)
    df_main['gym_numeric'] = df_main['gym_grade'].map(config.GYM_MAPPING).fillna(-1)

    today = pd.to_datetime('today').floor('D')

    # Past sessions are completed training (used for effort/grade analytics);
    # future sessions are the upcoming planned schedule
    df_past = df_main[df_main['date'] < today].copy()
    df_future = df_main[df_main['date'] >= today].copy()

    return df_past, df_future, df_dict


# --- Session (Main_Log) writes ---

def update_session(row_idx: int, updated_data: dict, config: Optional[PipelineConfig] = None) -> bool:
    """Overwrite specific cells of an existing session row in 'Main_Log'."""
    if config is None:
        config = PipelineConfig()

    worksheet = _open_worksheet(config, 'Main_Log')

    for key, value in updated_data.items():
        if key in config.SESSION_COL_MAPPING:
            worksheet.update_cell(row_idx, config.SESSION_COL_MAPPING[key], _to_sheet_safe_str(value))

    return True


def add_session(new_data: dict, config: Optional[PipelineConfig] = None) -> bool:
    """Append a brand-new session as a row in 'Main_Log'.

    Row layout (columns A-H): date_entry, date, category, effort,
    gym_grade, moonboard_grade, injured, exercises. "injured" defaults
    to "No" since new sessions are logged without that field.
    """
    if config is None:
        config = PipelineConfig()

    worksheet = _open_worksheet(config, 'Main_Log')

    row_to_append = ["", "", "", "", "", "", "No", ""]
    row_to_append[0] = pd.Timestamp.now().strftime("%d/%m/%Y %H:%M:%S")
    row_to_append[1] = new_data.get('Date', '')
    row_to_append[2] = new_data.get('Category', '')
    row_to_append[3] = _to_sheet_safe_str(new_data.get('Effort Scale'))
    row_to_append[4] = new_data.get('Max Gym Grade Color', '')
    row_to_append[5] = new_data.get('Max Moonboard Grade', '')
    row_to_append[7] = new_data.get('Exercises', '')

    # value_input_option='USER_ENTERED' lets Sheets parse dates/numbers the
    # same way it would if typed in by hand, rather than storing raw text
    worksheet.append_row(
        row_to_append,
        value_input_option='USER_ENTERED',
        insert_data_option='INSERT_ROWS'
    )
    return True


def delete_session(row_idx: int, config: Optional[PipelineConfig] = None) -> bool:
    """Delete a session row from 'Main_Log' by its Google Sheet row number"""
    if config is None:
        config = PipelineConfig()

    worksheet = _open_worksheet(config, 'Main_Log')
    worksheet.delete_rows(row_idx)
    return True


# --- Exercise (Exercise_Dictionary) writes ---

def add_exercise(new_data: dict, config: Optional[PipelineConfig] = None) -> bool:
    """Append a brand-new exercise as a row in 'Exercise_Dictionary'
 
    Expected keys (all optional except Name): Name, Type, Sets, Reps/Time,
    Rest, Comments, Phase
    """
    if config is None:
        config = PipelineConfig()
 
    worksheet = _open_worksheet(config, 'Exercise_Dictionary')
 
    row_to_append = [
        new_data.get('Name', ''),
        new_data.get('Type', ''),
        _to_sheet_safe_str(new_data.get('Sets')),
        new_data.get('Reps/Time', ''),
        _to_sheet_safe_str(new_data.get('Rest')),
        new_data.get('Comments', ''),
        new_data.get('Phase', ''),
    ]
 
    worksheet.append_row(
        row_to_append,
        value_input_option='USER_ENTERED',
        insert_data_option='INSERT_ROWS'
    )
    return True
 
 
def update_exercise(row_idx: int, updated_data: dict, config: Optional[PipelineConfig] = None) -> bool:
    """Overwrite specific cells of an existing exercise row in 'Exercise_Dictionary'."""
    if config is None:
        config = PipelineConfig()
 
    worksheet = _open_worksheet(config, 'Exercise_Dictionary')
 
    for key, value in updated_data.items():
        if key in config.EXERCISE_COL_MAPPING:
            worksheet.update_cell(row_idx, config.EXERCISE_COL_MAPPING[key], _to_sheet_safe_str(value))
 
    return True
 
 
def delete_exercise(row_idx: int, config: Optional[PipelineConfig] = None) -> bool:
    """Delete an exercise row from 'Exercise_Dictionary' by its Google Sheet row number"""
    if config is None:
        config = PipelineConfig()
 
    worksheet = _open_worksheet(config, 'Exercise_Dictionary')
    worksheet.delete_rows(row_idx)
    return True

if __name__ == "__main__":
    # Quick manual smoke test when running this file directly
    past, future, exercises = load_clean_data()
    print(f"Found {len(past)} completed sessions and {len(future)} planned sessions")
    print("\n--- Processed Past Sessions Preview ---")
    print(past.head())