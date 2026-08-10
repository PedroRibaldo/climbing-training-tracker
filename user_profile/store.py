"""
Supabase persistence for the athlete profile (profiles table) and injury
log (injuries table), plus avatar uploads to the 'avatars' storage bucket.
"""

from datetime import date as dt_date
from typing import Optional

import streamlit as st
from pydantic import ValidationError
from supabase import Client

from data_pipeline import _clean_write_value
from .models import ProfileRecord, InjuryRecord

PROFILES_TABLE = 'profiles'
INJURIES_TABLE = 'injuries'
AVATARS_BUCKET = 'avatars'


def current_grade_for(profile: dict, target_type: str) -> Optional[str]:
    """The profile's current grade for the given goal system ('gym' or
    'moonboard') - the one place app.py and ui/goals_tab.py both read
    this from, instead of re-deriving the same lookup twice."""
    return profile.get('current_gym_grade') if target_type == 'gym' else profile.get('current_moonboard_grade')


def get_profile(client: Client, user_id: str) -> dict:
    """The caller's own profile row, validated. Every column beyond
    id/role is None until the user fills the panel in - the signup
    trigger only ever inserts id/role, so this is the expected shape for
    a brand-new account, not an error case."""
    response = client.table(PROFILES_TABLE).select('*').eq('id', user_id).single().execute()
    try:
        return ProfileRecord.model_validate(response.data).model_dump()
    except ValidationError as exc:
        st.warning(f"Your profile has invalid data and was ignored: {exc}")
        return ProfileRecord(id=user_id, role='user').model_dump()


def update_profile(
    client: Client, user_id: str,
    display_name: Optional[str] = None, weight_kg: Optional[float] = None, height_cm: Optional[float] = None,
    current_gym_grade: Optional[str] = None, current_moonboard_grade: Optional[str] = None,
) -> bool:
    """Overwrites the athlete-profile fields on the caller's own row."""
    payload = {
        'display_name': _clean_write_value(display_name),
        'weight_kg': _clean_write_value(weight_kg),
        'height_cm': _clean_write_value(height_cm),
        'current_gym_grade': _clean_write_value(current_gym_grade),
        'current_moonboard_grade': _clean_write_value(current_moonboard_grade),
    }
    try:
        client.table(PROFILES_TABLE).update(payload).eq('id', user_id).execute()
    except Exception as exc:
        st.error(f"Couldn't save your profile: {exc}")
        return False
    return True


def upload_avatar(client: Client, user_id: str, file) -> Optional[str]:
    """Uploads a Streamlit UploadedFile to avatars/{user_id}/{filename},
    stores the resulting public URL on the profile, and returns it (None
    on failure)."""
    path = f"{user_id}/{file.name}"
    try:
        client.storage.from_(AVATARS_BUCKET).upload(
            path, file.getvalue(), {"upsert": "true", "content-type": file.type},
        )
        avatar_url = client.storage.from_(AVATARS_BUCKET).get_public_url(path)
        client.table(PROFILES_TABLE).update({'avatar_url': avatar_url}).eq('id', user_id).execute()
    except Exception as exc:
        st.error(f"Couldn't upload avatar: {exc}")
        return None
    return avatar_url


def list_injuries(client: Client) -> list[dict]:
    """Every injury the caller has logged (RLS scopes this to their own
    rows automatically), most recently started first."""
    response = client.table(INJURIES_TABLE).select('*').order('started_at', desc=True).execute()
    records = []
    for row in response.data:
        try:
            records.append(InjuryRecord.model_validate(row).model_dump())
        except ValidationError as exc:
            st.warning(f"An injury row had invalid data and was skipped: {exc}")
    return records


def add_injury(client: Client, body_part: str, description: Optional[str], started_at: dt_date) -> bool:
    """Logs a new active injury (resolved_at stays NULL). user_id isn't
    set explicitly - the column defaults to auth.uid(), same pattern as
    goals/exercise/climbing_training inserts."""
    payload = {
        'body_part': body_part,
        'description': _clean_write_value(description),
        'started_at': started_at.isoformat(),
    }
    try:
        client.table(INJURIES_TABLE).insert(payload).execute()
    except Exception as exc:
        st.error(f"Couldn't log injury: {exc}")
        return False
    return True


def resolve_injury(client: Client, injury_id: int, started_at: dt_date) -> bool:
    """Marks an injury resolved as of today. Rejected before any Supabase
    call if that would be before the injury started - the DB CHECK
    constraint enforces the same rule server-side as a backstop."""
    resolved_at = dt_date.today()
    if resolved_at < started_at:
        st.error("Resolved date can't be before the injury started.")
        return False
    try:
        client.table(INJURIES_TABLE).update({'resolved_at': resolved_at.isoformat()}).eq('id', injury_id).execute()
    except Exception as exc:
        st.error(f"Couldn't update injury: {exc}")
        return False
    return True
