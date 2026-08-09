"""
Login, signup, logout, and cookie-based session restore. All state lives
in st.session_state - there is no module-level/shared session anywhere.
"""

from typing import Optional

import streamlit as st
from supabase_auth.errors import AuthApiError

from .client import new_client

REFRESH_TOKEN_COOKIE = "ctt_refresh_token"
COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 30  # 30 days


def is_logged_in() -> bool:
    return "supabase_client" in st.session_state


def _store_session(client, session) -> None:
    st.session_state.supabase_client = client
    st.session_state.auth_user_id = session.user.id
    st.session_state.auth_user_email = session.user.email


def log_in(email: str, password: str) -> tuple[Optional[str], Optional[str]]:
    """Attempts a login. Returns (error_message, refresh_token) - exactly
    one is None. On success, the session is already stored in
    st.session_state; the refresh_token is returned so the caller can
    persist it in a cookie."""
    client = new_client()
    try:
        response = client.auth.sign_in_with_password({"email": email, "password": password})
    except AuthApiError as exc:
        return exc.message, None
    if not response.session:
        return "Invalid email or password.", None
    _store_session(client, response.session)
    return None, response.session.refresh_token


def sign_up(email: str, password: str) -> tuple[bool, str, Optional[str]]:
    """Attempts a signup. Returns (needs_email_confirmation, message,
    refresh_token). If email confirmation is required, Supabase returns no
    session yet, so refresh_token is None and the caller shouldn't treat
    the user as logged in."""
    client = new_client()
    try:
        response = client.auth.sign_up({"email": email, "password": password})
    except AuthApiError as exc:
        return False, exc.message, None
    if response.session:
        _store_session(client, response.session)
        return False, "Account created.", response.session.refresh_token
    return True, "Account created - check your email to confirm it before logging in.", None


def restore_session(refresh_token: str) -> bool:
    """Attempts to restore a session from a stored refresh token. Returns
    True on success. Any failure (expired/revoked/malformed token, network
    issue) just means the caller falls back to showing the login form -
    never raises."""
    client = new_client()
    try:
        response = client.auth.refresh_session(refresh_token)
    except Exception:
        return False
    if not response.session:
        return False
    _store_session(client, response.session)
    return True


def log_out() -> None:
    client = st.session_state.get("supabase_client")
    if client is not None:
        try:
            client.auth.sign_out()
        except Exception:
            pass
    for key in ("supabase_client", "auth_user_id", "auth_user_email"):
        st.session_state.pop(key, None)
