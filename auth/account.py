"""
Account-management actions beyond login/signup/logout: changing password
or email, and permanently deleting an account. Split from session.py
since delete_account needs a different credential (the service-role key)
than everything else in this package, which only ever uses the anon key.
"""

from typing import Optional

import streamlit as st
from supabase_auth.errors import AuthApiError

from .client import new_admin_client


def change_password(client, new_password: str) -> Optional[str]:
    """Attempts a password change on the caller's own session. Returns an
    error message, or None on success."""
    try:
        client.auth.update_user({"password": new_password})
    except AuthApiError as exc:
        return exc.message
    return None


def change_email(client, new_email: str) -> Optional[str]:
    """Starts an email change - Supabase emails a confirmation link to the
    new address before it actually takes effect. Returns an error
    message, or None if the request was accepted."""
    try:
        client.auth.update_user({"email": new_email})
    except AuthApiError as exc:
        return exc.message
    return None


def delete_account(user_id: str) -> bool:
    """Permanently deletes the given user's auth.users row. Every table
    referencing it (profiles, goals, exercise, climbing_training,
    injuries) is ON DELETE CASCADE, so this cleans up everything with no
    separate app-side cleanup. Requires the service-role key - the
    anon-key client a normal session uses can't call this."""
    try:
        admin_client = new_admin_client()
        admin_client.auth.admin.delete_user(user_id)
    except Exception as exc:
        st.error(f"Couldn't delete your account: {exc}")
        return False
    return True
