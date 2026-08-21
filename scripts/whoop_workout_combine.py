"""
Pure transforms for the WHOOP climbing-workout sync: normalizing one raw
WHOOP workout record into a flat dict, and combining a day's worth of them
into a single summary row.

Deliberately dependency-free (stdlib only) - kept separate from
whoop_sync.py so it's testable without installing `requests`, which is a
script-only dependency (see scripts/requirements-whoop.txt) not present in
the main dev environment. Also does not import the `whoop` package:
whoop/__init__.py pulls in whoop/store.py, which imports streamlit and
data_pipeline - neither of which belongs in this script's dependency set.
"""

from datetime import datetime
from typing import Optional

ZONE_MILLI_KEYS = [
    'zone_zero_milli', 'zone_one_milli', 'zone_two_milli',
    'zone_three_milli', 'zone_four_milli', 'zone_five_milli',
]


def normalize_workout(raw: dict) -> dict:
    """Flattens one raw WHOOP workout record (as returned by
    GET /developer/v2/activity/workout) into duration/calories/HR/zone
    fields, ready to combine or store."""
    start = datetime.fromisoformat(raw['start'].replace('Z', '+00:00'))
    end = datetime.fromisoformat(raw['end'].replace('Z', '+00:00'))
    score = raw.get('score') or {}
    zone_duration = score.get('zone_durations') or {}

    normalized = {
        'duration_min': (end - start).total_seconds() / 60,
        'calories': (score.get('kilojoule') or 0) * 0.239006,
        'average_heart_rate': score.get('average_heart_rate') or 0,
        'max_heart_rate': score.get('max_heart_rate') or 0,
    }
    for n, key in enumerate(ZONE_MILLI_KEYS):
        normalized[f'zone_{n}_min'] = (zone_duration.get(key) or 0) / 60000
    return normalized


def combine_climbing_workouts(workouts: list[dict]) -> Optional[dict]:
    """Reduces one day's normalized climbing workouts into a single summary
    row: duration/calories/zone minutes summed, avg HR duration-weighted
    (not a plain average - a 10-minute and a 90-minute workout shouldn't
    count equally), max HR the max across workouts. None for an empty list."""
    if not workouts:
        return None

    total_duration = sum(w['duration_min'] for w in workouts)
    total_calories = sum(w['calories'] for w in workouts)
    avg_hr = sum(w['average_heart_rate'] * w['duration_min'] for w in workouts) / total_duration
    max_hr = max(w['max_heart_rate'] for w in workouts)

    combined = {
        'duration_min': round(total_duration, 1),
        'calories': round(total_calories),
        'avg_hr': round(avg_hr),
        'max_hr': round(max_hr),
    }
    for n in range(6):
        combined[f'zone_{n}_min'] = round(sum(w[f'zone_{n}_min'] for w in workouts), 1)
    return combined
