"""
Daily WHOOP sync: refreshes the access token if needed, pulls yesterday's
recovery/cycle data, and upserts it into `whoop_daily_metrics`. Run by
.github/workflows/whoop_sync.yml; safe to run manually too.

UNVERIFIED: written directly against developer.whoop.com's published API
docs (endpoints confirmed against the live API reference), but has not
been run against a real account - no WHOOP device was available when this
was written. Confirm it works end-to-end before enabling the scheduled
workflow (see .github/workflows/whoop_sync.yml).
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv
from supabase import create_client

TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"
RECOVERY_URL = "https://api.prod.whoop.com/developer/v2/recovery"
CYCLE_URL = "https://api.prod.whoop.com/developer/v2/cycle"


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
    }).eq('id', True).execute()

    return tokens['access_token']


def _fetch_yesterday(url: str, access_token: str) -> list[dict]:
    """One page of records intersecting yesterday (UTC)."""
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    response = requests.get(
        url,
        headers={'Authorization': f'Bearer {access_token}'},
        params={'start': yesterday.isoformat(), 'end': today.isoformat(), 'limit': 25},
    )
    response.raise_for_status()
    return response.json().get('records', [])


def sync_yesterday(supabase, access_token: str) -> bool:
    """Pulls yesterday's recovery + cycle data and upserts one row into
    whoop_daily_metrics. Returns False (and writes nothing) if WHOOP has
    no scored recovery for that day yet (e.g. the device wasn't worn)."""
    recoveries = [r for r in _fetch_yesterday(RECOVERY_URL, access_token) if r.get('score_state') == 'SCORED']
    cycles = [c for c in _fetch_yesterday(CYCLE_URL, access_token) if c.get('score_state') == 'SCORED']

    if not recoveries:
        print("No scored recovery for yesterday - skipping.")
        return False

    recovery = recoveries[0]['score']
    cycle = cycles[0]['score'] if cycles else {}
    metric_date = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()

    supabase.table('whoop_daily_metrics').upsert({
        'date': metric_date,
        'recovery_score': recovery.get('recovery_score'),
        'hrv_ms': recovery.get('hrv_rmssd_milli'),
        'resting_hr': recovery.get('resting_heart_rate'),
        'strain': cycle.get('strain'),
    }).execute()
    print(f"Synced WHOOP metrics for {metric_date}.")
    return True


def main():
    load_dotenv()
    client_id = os.environ['WHOOP_CLIENT_ID']
    client_secret = os.environ['WHOOP_CLIENT_SECRET']
    supabase = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])

    try:
        access_token = _refresh_access_token(supabase, client_id, client_secret)
        sync_yesterday(supabase, access_token)
    except Exception as exc:
        print(f"WHOOP sync failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
