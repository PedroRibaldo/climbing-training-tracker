"""
Supabase client construction for the auth layer. Every browser session
gets its own client instance here - never cached or shared - since once a
client's auth state carries a signed-in user's tokens, sharing it across
concurrent users would leak sessions between them.
"""

import os

import streamlit as st
from dotenv import load_dotenv
from supabase import create_client, Client


def _client_for(secrets_field: str, env_var: str, error_hint: str) -> Client:
    """Builds a Supabase client from Streamlit secrets (preferred) or a
    local .env fallback. secrets_field selects which key under
    st.secrets['supabase'] to use; error_hint names what's missing if
    neither source has it."""
    load_dotenv()  # no-op if there's no .env file

    try:
        if "supabase" in st.secrets:
            return create_client(st.secrets["supabase"]["url"], st.secrets["supabase"][secrets_field])
    except Exception:
        pass

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get(env_var)
    if not url or not key:
        raise RuntimeError(
            f"Supabase {error_hint} not found. Set SUPABASE_URL/{env_var} in a .env file "
            f"for local dev, or add a [supabase] url/{secrets_field} block to Streamlit secrets in the cloud."
        )
    return create_client(url, key)


def new_client() -> Client:
    """A fresh Supabase client, authenticated with the anon key only. Used
    both for login/signup attempts and, after a successful one, as the
    per-session client stored in st.session_state."""
    return _client_for("key", "SUPABASE_KEY", "credentials")


def new_admin_client() -> Client:
    """A service-role client for admin-only operations (currently just
    account deletion). Never stored in st.session_state or reused for
    anything else - a service-role key bypasses Row-Level Security
    entirely, so every other call in the app must keep using the
    anon-key client from new_client()."""
    return _client_for("service_role_key", "SUPABASE_SERVICE_ROLE_KEY", "service-role credentials")


def reassert_session(client: Client) -> None:
    """Works around a bug in this pinned supabase-py version: client.auth.
    update_user() (used by change_password/change_email/password reset)
    fires a "USER_UPDATED" auth event, but the Client's auth-state
    listener only re-attaches the authenticated JWT to the client's
    Authorization header for SIGNED_IN/TOKEN_REFRESHED/SIGNED_OUT - for
    anything else, including USER_UPDATED, it silently resets the header
    back to the anon key. Every table query after that point then looks
    unauthenticated to Row-Level Security and just returns 0 rows instead
    of raising, rather than actually failing loudly. Call this right
    after any update_user() call to restore the correct header by
    re-firing a TOKEN_REFRESHED event."""
    session = client.auth.get_session()
    if session:
        client.auth.set_session(session.access_token, session.refresh_token)
