"""
Data pipeline for the Climbing Training Tracker.

Handles all communication with the Google Sheet that backs the tracker:
- Pulling raw form/log data and cleaning it into typed DataFrames.
- Pushing edits, new sessions, and deletions back to the sheet.

The Streamlit app (app.py) only talks to Google Sheets through this module.
"""

from typing import Any, Optional

import numpy as np
import pandas as pd
import gspread
import streamlit as st
# from pydantic import BaseModel  # TODO: add pydantic models to validate row schemas


class PipelineConfig:
    """Central place for every constant the pipeline depends on.

    Keeping these here (instead of scattered through the code) means the
    Google Sheet's column names/order can change in one place without
    touching the cleaning or writing logic below.
    """

    SPREADSHEET_NAME = 'Climbing Tracker'
    CREDENTIALS = 'credentials.json'

    # Raw Google Form column headers -> internal snake_case names
    DICT_COLUMN_NAMES = {
        'Carimbo de data/hora': 'date_entry',
        'Date': 'date',
        'Category': 'category',
        'Effort Scale': 'effort',
        'Max Gym Grade Color': 'gym_grade',
        'Max Moonboard Grade': 'moonboard_grade',
        'Injuries / Tweaks': 'injured',
        'Exercises': 'exercises'
    }

    # Pandas dtypes applied to the cleaned columns above (dates are handled separately)
    DTYPE_MAPPING = {
        'category': 'category',
        'effort': 'Int64',
        'gym_grade': 'string',
        'moonboard_grade': 'string',
        'injured': 'bool',
        'exercises': 'string'
    }

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
    COL_MAPPING = {
        'Category': 3,
        'Effort Scale': 4,
        'Max Gym Grade Color': 5,
        'Max Moonboard Grade': 6,
        'Exercises': 8
    }


def _get_google_client(config: 'PipelineConfig') -> gspread.Client:
    """Authenticate and return the gspread client based on the environment"""
    # If running in Streamlit Cloud, grab credentials from the secrets manager
    if "gcp_service_account" in st.secrets:
        return gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    
    # Otherwise, fallback to the local JSON file
    return gspread.service_account(filename=config.CREDENTIALS)


def _open_worksheet(config: 'PipelineConfig', sheet_name: str = 'Main_Log') -> gspread.Worksheet:
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

    df_main = pd.DataFrame(spreadsheet.worksheet('Main_Log').get_all_records())
    df_dict = pd.DataFrame(spreadsheet.worksheet('Exercise_Dictionary').get_all_records())

    return clean_data(df_main, df_dict, config)


def clean_data(df_main: pd.DataFrame, df_dict: pd.DataFrame, config: PipelineConfig):
    """Normalize column names/types and split sessions into past vs. future.

    Kept separate from load_clean_data() so it can be unit-tested with
    plain DataFrames, without needing a live Google Sheets connection.
    """
    df_main.columns = df_main.columns.str.strip()
    df_dict.columns = df_dict.columns.str.strip()

    # Google Forms leaves blank cells as empty strings rather than real NaNs
    df_main = df_main.replace('', np.nan)
    df_dict = df_dict.replace('', np.nan)

    df_main.rename(columns=config.DICT_COLUMN_NAMES, inplace=True)

    # Capture the original Google Sheet row number before filtering columns,
    # so later edits/deletes can target the correct row (sheet rows are
    # 1-indexed and row 1 is the header, hence index + 2)
    df_main['gsheet_row'] = df_main.index + 2

    cols_to_keep = list(config.DICT_COLUMN_NAMES.values()) + ['gsheet_row']
    df_main = df_main[cols_to_keep]

    df_dict.rename(columns={'Reps/Time': 'reps'}, inplace=True)
    df_dict.columns = df_dict.columns.str.lower()

    # Treat missing "injured" entries as "No" before casting to bool
    df_main['injured'] = df_main['injured'].map({'Yes': True, 'No': False, np.nan: False})

    df_main = df_main.astype(config.DTYPE_MAPPING)

    # Parse both date columns; day-first because the sheet uses DD/MM/YYYY
    df_main['date'] = pd.to_datetime(df_main['date'], dayfirst=True, errors='coerce').dt.normalize()
    df_main['date_entry'] = pd.to_datetime(df_main['date_entry'], dayfirst=True, errors='coerce')

    # Numeric encodings for plotting, kept alongside the original text
    # columns (moonboard_grade / gym_grade) so tooltips can still show
    # the human-readable grade
    df_main['moonboard_numeric'] = df_main['moonboard_grade'].map(config.MOONBOARD_MAPPING)
    df_main['gym_numeric'] = df_main['gym_grade'].map(config.GYM_MAPPING)

    # -1 marks "no grade logged that day" so it can be filtered out of charts
    df_main['moonboard_numeric'] = df_main['moonboard_numeric'].fillna(-1)
    df_main['gym_numeric'] = df_main['gym_numeric'].fillna(-1)

    today = pd.to_datetime('today').floor('D')

    # Past sessions are completed training (used for effort/grade analytics);
    # future sessions are the upcoming planned schedule
    df_past = df_main[df_main['date'] < today].copy()
    df_future = df_main[df_main['date'] >= today].copy()

    return df_past, df_future, df_dict


def update_session_in_sheet(row_idx: int, updated_data: dict, config: Optional[PipelineConfig] = None) -> bool:
    """Overwrite specific cells of an existing session row in 'Main_Log'."""
    if config is None:
        config = PipelineConfig()

    worksheet = _open_worksheet(config)

    for key, value in updated_data.items():
        if key in config.COL_MAPPING:
            worksheet.update_cell(row_idx, config.COL_MAPPING[key], _to_sheet_safe_str(value))

    return True


def add_session_to_sheet(new_data: dict, config: Optional[PipelineConfig] = None) -> bool:
    """Append a brand-new session as a row in 'Main_Log'.

    Row layout (columns A-H): date_entry, date, category, effort,
    gym_grade, moonboard_grade, injured, exercises. "injured" defaults
    to "No" since new sessions are logged without that field.
    """
    if config is None:
        config = PipelineConfig()

    worksheet = _open_worksheet(config)

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


def delete_session_from_sheet(row_idx: int, config: Optional[PipelineConfig] = None) -> bool:
    """Delete a session row from 'Main_Log' by its Google Sheet row number."""
    if config is None:
        config = PipelineConfig()

    worksheet = _open_worksheet(config)
    worksheet.delete_rows(row_idx)
    return True


if __name__ == "__main__":
    # Quick manual smoke test when running this file directly
    past, future, exercises = load_clean_data()
    print(f"Found {len(past)} completed sessions and {len(future)} planned sessions.")
    print("\n--- Processed Past Sessions Preview ---")
    print(past.head())