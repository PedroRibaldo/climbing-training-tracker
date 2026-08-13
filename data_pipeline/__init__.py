"""
Data pipeline for the Climbing Training Tracker.

Handles all communication with the Supabase Postgres database that backs
the tracker (climbing_training, exercise, training_exercises), validating
and cleaning rows into typed DataFrames, and pushing session/exercise
edits back to the database.

Split into models/client/cleaning/sessions/exercises/analytics internally;
this file re-exports the full public surface so `from data_pipeline import
X` keeps working exactly as it did when this was a single module.
"""

from .models import PipelineConfig, SessionRecord, ExerciseRecord, _validate_records
from .client import _create_supabase_client, _get_supabase_client
from .cleaning import (
    _clean_write_value, _to_iso_date, _flatten_session_row, _flatten_exercise_row,
    load_clean_data, clean_data,
)
from .sessions import _sync_session_exercises, update_session, add_session, delete_session
from .exercises import _sync_exercise_categories, add_exercise, update_exercise, delete_exercise
from .analytics import compute_acwr, compute_kpis, get_peak_sessions

if __name__ == "__main__":
    # Quick manual smoke test: python -m data_pipeline
    past, future, exercises = load_clean_data()
    print(f"Found {len(past)} completed sessions and {len(future)} planned sessions")
    print("\n--- Processed Past Sessions Preview ---")
    print(past.head())
