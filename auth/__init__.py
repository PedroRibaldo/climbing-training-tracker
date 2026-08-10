"""
Auth for the Climbing Training Tracker: Supabase Auth-backed login/signup,
plus per-browser-session client management.

Split into client.py (client construction) and session.py (login/signup/
logout/restore) internally; this file re-exports the full public surface.
"""

from .client import new_client, new_admin_client
from .session import (
    is_logged_in, log_in, sign_up, restore_session, log_out,
    request_password_reset, complete_password_reset,
    REFRESH_TOKEN_COOKIE, COOKIE_MAX_AGE_SECONDS,
)
from .account import change_password, change_email, delete_account
