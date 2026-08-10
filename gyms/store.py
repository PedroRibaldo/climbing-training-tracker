"""
Supabase persistence for gyms and gym memberships: listing gyms, joining
one, and (for gym admins) viewing/editing a gym's member roster.
"""

import streamlit as st
from pydantic import ValidationError
from supabase import Client

from .models import GymRecord, GymMembershipRecord, GymMemberRecord

GYMS_TABLE = 'gyms'
GYM_MEMBERSHIPS_TABLE = 'gym_memberships'
PROFILES_TABLE = 'profiles'


def list_gyms(client: Client) -> list[dict]:
    """Every gym in the system, for the join picker. Gyms are only ever
    written manually (service-role key), so this is read-only from the
    app's perspective."""
    response = client.table(GYMS_TABLE).select('*').order('name').execute()
    records = []
    for row in response.data:
        try:
            records.append(GymRecord.model_validate(row).model_dump())
        except ValidationError as exc:
            st.warning(f"A gym row had invalid data and was skipped: {exc}")
    return records


def _flatten_membership_row(row: dict) -> dict:
    """Supabase returns each membership with a nested 'gyms' object (the
    embedded join on gym_id). Flatten that into a plain 'gym_name' field,
    matching the shape GymMembershipRecord expects - same pattern as
    data_pipeline.cleaning's _flatten_session_row/_flatten_exercise_row."""
    flat = {k: v for k, v in row.items() if k != 'gyms'}
    flat['gym_name'] = (row.get('gyms') or {}).get('name')
    return flat


def get_user_memberships(client: Client) -> list[dict]:
    """The caller's own gym memberships, joined with each gym's name (RLS
    scopes this to the caller automatically)."""
    response = client.table(GYM_MEMBERSHIPS_TABLE).select('*, gyms(name)').execute()
    records = []
    for row in response.data:
        try:
            records.append(GymMembershipRecord.model_validate(_flatten_membership_row(row)).model_dump())
        except ValidationError as exc:
            st.warning(f"A gym membership had invalid data and was skipped: {exc}")
    return records


def join_gym(client: Client, gym_id: int) -> bool:
    """Joins a gym as a 'climber' (the default, non-elevated role) - the
    'join gym' RLS policy rejects any insert that tries to set a
    different role, so the payload never needs to specify one."""
    try:
        client.table(GYM_MEMBERSHIPS_TABLE).insert({'gym_id': gym_id}).execute()
    except Exception as exc:
        st.error(f"Couldn't join that gym: {exc}")
        return False
    return True


def list_gym_members(client: Client, gym_id: int) -> list[dict]:
    """Every member of a gym, joined with their display name. RLS only
    returns rows at all if the caller is an admin at this gym (see
    is_gym_admin() in the schema) - a non-admin gets an empty list rather
    than an error.

    profiles isn't directly foreign-keyed to gym_memberships (both
    separately reference auth.users), so this can't use a single
    embedded-join select the way get_user_memberships does - it's two
    queries, merged in Python."""
    memberships_response = client.table(GYM_MEMBERSHIPS_TABLE).select('*').eq('gym_id', gym_id).execute()
    memberships = memberships_response.data
    user_ids = [m['user_id'] for m in memberships]

    names_by_id = {}
    if user_ids:
        profiles_response = client.table(PROFILES_TABLE).select('id, display_name').in_('id', user_ids).execute()
        names_by_id = {p['id']: p['display_name'] for p in profiles_response.data}

    records = []
    for row in memberships:
        flat = {**row, 'display_name': names_by_id.get(row['user_id'])}
        try:
            records.append(GymMemberRecord.model_validate(flat).model_dump())
        except ValidationError as exc:
            st.warning(f"A member row had invalid data and was skipped: {exc}")
    return records


def update_member_role(client: Client, membership_id: int, new_role: str) -> bool:
    """Changes a member's role. Only succeeds (per the 'admin updates
    member role' RLS policy) if the caller is an admin at that member's
    gym."""
    try:
        client.table(GYM_MEMBERSHIPS_TABLE).update({'role': new_role}).eq('id', membership_id).execute()
    except Exception as exc:
        st.error(f"Couldn't update that member's role: {exc}")
        return False
    return True
