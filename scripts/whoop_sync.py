"""
Daily WHOOP sync: refreshes the access token if needed, pulls the most
recent scored recovery/cycle data, and upserts it into
`whoop_daily_metrics`. Run by .github/workflows/whoop_sync.yml; safe to
run manually too.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv
from supabase import create_client

from whoop_workout_combine import normalize_workout, combine_climbing_workouts

TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
RECOVERY_URL = "https://api.prod.whoop.com/developer/v2/recovery"
CYCLE_URL = "https://api.prod.whoop.com/developer/v2/cycle"
WORKOUT_URL = "https://api.prod.whoop.com/developer/v2/activity/workout"
CLIMBING_SPORT_NAME = "Rock Climbing"


def _refresh_access_token(supabase, client_id: str, client_secret: str) -> str:
    """Reads the current refresh token, exchanges it for a new access
    token, and writes back the rotated pair (WHOOP invalidates both the
    old access and refresh token on every refresh)."""
    row = supabase.table('whoop_tokens').select('*').eq('id', True).single().execute().data

    response = requests.post(TOKEN_URL, data={
        'grant_type': 'refresh_token',
        'refresh_token': row['refresh_token'],
        'client_id': client_id,
        'client_secret': client_secret,
    })
    response.raise_for_status()
    tokens = response.json()

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=tokens['expires_in'])
    supabase.table('whoop_tokens').update({
        'access_token': tokens['access_token'],
        'refresh_token': tokens['refresh_token'],
        'expires_at': expires_at.isoformat(),
        'updated_at': datetime.now(timezone.utc).isoformat(),
    }).eq('id', True).execute()

    return tokens['access_token']


def _as_int(value) -> int | None:
    """WHOOP returns recovery_score/resting_heart_rate as floats (e.g.
    31.0); the Postgres columns are INTEGER and reject decimal-formatted
    text, so these need an explicit round-trip through int()."""
    return None if value is None else int(round(value))


def _fetch_recent(url: str, access_token: str, days: int = 3) -> list[dict]:
    """Records from the last `days` days. A window wider than 1 day is
    needed because WHOOP attaches a recovery to the *new* cycle that
    starts when you wake up - that cycle's start timestamp is often
    still "today" (UTC), not "yesterday", depending on wake time and
    timezone, so a narrower window can miss the most recent recovery
    entirely."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    response = requests.get(
        url,
        headers={'Authorization': f'Bearer {access_token}'},
        params={'start': start.isoformat(), 'end': end.isoformat(), 'limit': 25},
    )
    response.raise_for_status()
    return response.json().get('records', [])


def sync_latest(supabase, access_token: str) -> bool:
    """Pulls the most recent scored recovery and its matching cycle, and
    upserts one row into whoop_daily_metrics keyed to the date that
    cycle started (the calendar day WHOOP itself associates the recovery
    with). Returns False (and writes nothing) if there's no scored
    recovery yet (e.g. the device hasn't completed a first sleep cycle)."""
    recoveries = [r for r in _fetch_recent(RECOVERY_URL, access_token) if r.get('score_state') == 'SCORED']
    if not recoveries:
        print("No scored recovery available yet - skipping.")
        return False

    recovery = max(recoveries, key=lambda r: r['created_at'])
    cycles = {c['id']: c for c in _fetch_recent(CYCLE_URL, access_token)}
    cycle = cycles.get(recovery['cycle_id'], {})
    cycle_score = cycle.get('score', {}) if cycle.get('score_state') == 'SCORED' else {}

    if cycle.get('start'):
        metric_date = datetime.fromisoformat(cycle['start'].replace('Z', '+00:00')).date().isoformat()
    else:
        metric_date = datetime.now(timezone.utc).date().isoformat()

    score = recovery['score']
    supabase.table('whoop_daily_metrics').upsert({
        'date': metric_date,
        'recovery_score': _as_int(score.get('recovery_score')),
        'hrv_ms': score.get('hrv_rmssd_milli'),
        'resting_hr': _as_int(score.get('resting_heart_rate')),
        'strain': cycle_score.get('strain'),
    }).execute()
    print(f"Synced WHOOP metrics for {metric_date}.")
    return True


def sync_climbing_workouts(supabase, access_token: str) -> None:
    """Pulls recent workouts, keeps only scored entries tagged
    CLIMBING_SPORT_NAME, groups them by the UTC date each one started
    (same convention sync_latest uses for metric_date), and upserts one
    combined row per date into whoop_climbing_workouts. Writes nothing for
    days with no matching workout."""
    workouts = [
        w for w in _fetch_recent(WORKOUT_URL, access_token)
        if w.get('score_state') == 'SCORED' and w.get('sport_name') == CLIMBING_SPORT_NAME
    ]

    by_date: dict[str, list[dict]] = {}
    for raw in workouts:
        workout_date = datetime.fromisoformat(raw['start'].replace('Z', '+00:00')).date().isoformat()
        by_date.setdefault(workout_date, []).append(normalize_workout(raw))

    for workout_date, normalized in by_date.items():
        combined = combine_climbing_workouts(normalized)
        supabase.table('whoop_climbing_workouts').upsert({'date': workout_date, **combined}).execute()
        print(f"Synced {len(normalized)} climbing workout(s) for {workout_date}.")

    if not by_date:
        print("No climbing workouts in the sync window - nothing to upsert.")


def main():
    load_dotenv()
    client_id = os.environ['WHOOP_CLIENT_ID']
    client_secret = os.environ['WHOOP_CLIENT_SECRET']
    supabase = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])

    try:
        access_token = _refresh_access_token(supabase, client_id, client_secret)
        sync_latest(supabase, access_token)
        sync_climbing_workouts(supabase, access_token)
    except Exception as exc:
        print(f"WHOOP sync failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
