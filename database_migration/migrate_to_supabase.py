"""
One-off migration script to move data from Google Sheets into the new
normalized 3-table Supabase PostgreSQL database.

Safe to re-run: exercise and training_exercises rows are upserted, and the
script refuses to insert duplicate sessions into climbing_training without
an explicit confirmation if it looks like it's already been run once.
"""

import os
import sys
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from supabase import create_client, Client

# Leverage existing pipeline to get perfectly clean, validated data
from data_pipeline import load_clean_data


def clean_val(val):
    """Convert pandas/numpy nulls to standard Python None for Supabase JSON serialization"""
    if pd.isna(val):
        return None
    if isinstance(val, (np.int64, np.int32)):
        return int(val)
    if isinstance(val, (np.float64, np.float32, float)):
        if float(val).is_integer():
            return int(val)
        return float(val)
    if isinstance(val, np.bool_):
        return bool(val)
    return val


def run_migration():
    # Authenticate with Supabase
    load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    if not url or not key:
        print("Error: SUPABASE_URL or SUPABASE_KEY not found in .env file")
        return

    supabase: Client = create_client(url, key)

    # Fetch clean data from Google Sheets
    print("Fetching validated data from Google Sheets...")
    df_past, df_future, df_dict = load_clean_data()
    df_sessions = pd.concat([df_past, df_future]).copy()

    print(f"Found {len(df_dict)} exercises and {len(df_sessions)} sessions")

    # Refuse to silently duplicate sessions on a second run
    existing = supabase.table("climbing_training").select("id", count="exact").execute()
    if existing.count:
        print(f"\nclimbing_training already has {existing.count} row(s)")
        answer = input("Sessions aren't upserted, so continuing WILL create duplicates. Continue anyway? [y/N] ")
        if answer.strip().lower() != 'y':
            print("Aborted - no changes made.")
            return

    # Collected instead of printed inline, so nothing gets lost in the scroll
    dropped_reps_time = []
    unmatched_exercise_names = set()

    # Migrate Table 1: exercise
    print("\n🚀 Migrating Table 1: 'exercise'...")
    exercise_map = {}  # This will store { 'Exercise Name': Supabase_ID } for the junction table

    for _, row in df_dict.iterrows():
        name = clean_val(row.get('name'))
        if not name:
            continue

        ex_type = clean_val(row.get('type'))
        reps_time_raw = clean_val(row.get('reps'))  # This holds the old 'Reps/Time' string

        # Split reps and time into their proper new columns based on Type
        reps_val, time_val = None, None
        if ex_type == 'Reps' and reps_time_raw is not None:
            try:
                reps_val = int(reps_time_raw)
            except ValueError:
                dropped_reps_time.append((name, ex_type, reps_time_raw, 'not a valid integer'))
        elif ex_type == 'Time' and reps_time_raw is not None:
            time_val = str(reps_time_raw)
        elif reps_time_raw is not None:
            # Type is blank/unknown, so there's no safe column to put this in
            dropped_reps_time.append((name, ex_type, reps_time_raw, 'no Type set'))

        ex_data = {
            "name": name,
            "type": ex_type,
            "sets": clean_val(row.get('sets')),
            "reps": reps_val,
            "time": time_val,
            "rest": clean_val(row.get('rest')),
            "comments": clean_val(row.get('comments')),
            "phase": clean_val(row.get('phase'))
        }

        # Upsert ensures we don't crash if running the script twice
        response = supabase.table("exercise").upsert(ex_data, on_conflict="name").execute()

        if response.data:
            # Save the new database ID for this exercise
            exercise_map[name] = response.data[0]['id']

    print(f"   Successfully migrated {len(exercise_map)} exercises.")

    # Migrate Table 2: climbing_training & Table 3: training_exercises
    print("\n🚀 Migrating Table 2 & 3: Sessions and Junctions...")
    sessions_migrated = 0
    junctions_created = 0

    for _, row in df_sessions.iterrows():
        date_val = clean_val(row.get('date'))
        if not date_val:
            continue

        date_entry = clean_val(row.get('date_entry'))
        date_entry_str = date_entry.isoformat() if date_entry else None

        session_data = {
            "date_entry": date_entry_str,
            "date": date_val.date().isoformat(),
            "category": clean_val(row.get('category')),
            "effort": clean_val(row.get('effort')),
            "gym_grade": clean_val(row.get('gym_grade')),
            "moonboard_grade": clean_val(row.get('moonboard_grade')),
            "injured": clean_val(row.get('injured')) or False
        }

        # Insert the session and grab its new ID
        sess_resp = supabase.table("climbing_training").insert(session_data).execute()

        if not sess_resp.data:
            continue

        session_id = sess_resp.data[0]['id']
        sessions_migrated += 1

        # Parse the old comma-separated exercises string
        exercises_str = clean_val(row.get('exercises'))
        if exercises_str:
            ex_list = [e.strip() for e in exercises_str.split(',') if e.strip()]

            for ex_name in ex_list:
                ex_id = exercise_map.get(ex_name)
                if ex_id:
                    junction_data = {
                        "training_id": session_id,
                        "exercise_id": ex_id
                    }
                    # Upsert handles any accidental duplicates in string (e.g., "Pull-ups, Pull-ups")
                    supabase.table("training_exercises").upsert(junction_data).execute()
                    junctions_created += 1
                else:
                    unmatched_exercise_names.add(ex_name)

    print(f"Successfully migrated {sessions_migrated} sessions.")
    print(f"Successfully mapped {junctions_created} exercise relationships.")

    # Summary of anything that didn't migrate cleanly
    if dropped_reps_time:
        print(f"\n{len(dropped_reps_time)} exercise(s) had a Reps/Time value that couldn't be migrated:")
        for name, ex_type, raw, reason in dropped_reps_time:
            print(f"- {name!r}: value {raw!r} dropped ({reason}, Type was {ex_type!r})")
        print("Fix these directly in Supabase's 'exercise' table once the migration finishes")

    if unmatched_exercise_names:
        print(f"\n{len(unmatched_exercise_names)} exercise name(s) mentioned in sessions didn't match Exercise_Dictionary:")
        for name in sorted(unmatched_exercise_names):
            print(f"- {name!r}")
        print("Likely a typo/capitalization mismatch - those sessions migrated without this exercise linked")

    if not dropped_reps_time and not unmatched_exercise_names:
        print("\nMigration complete, nothing was skipped. Go check your Supabase dashboard")
    else:
        print("\nMigration complete with the warnings above - review them before treating Supabase as the source of truth")


if __name__ == "__main__":
    run_migration()