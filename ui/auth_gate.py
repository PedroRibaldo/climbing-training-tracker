"""
The login/signup gate shown before anything else in the app, plus the
logged-in header control. A cookie holding the Supabase refresh token
persists the session across browser refreshes, since Streamlit's own
session state doesn't survive one.
"""

import streamlit as st
from streamlit_cookies_controller import CookieController

from auth import (
    is_logged_in, log_in, sign_up, restore_session, log_out,
    REFRESH_TOKEN_COOKIE, COOKIE_MAX_AGE_SECONDS,
)


def _cookies() -> CookieController:
    if "cookie_controller" not in st.session_state:
        st.session_state.cookie_controller = CookieController()
    return st.session_state.cookie_controller


def require_login() -> bool:
    """Renders the login/signup gate and stops the script if no session
    exists yet (including a fresh session just restored from a cookie).
    Returns True only when the caller is safe to render the rest of the
    app."""
    cookies = _cookies()

    if not is_logged_in():
        token = cookies.get(REFRESH_TOKEN_COOKIE)
        if token:
            restore_session(token)

    if is_logged_in():
        return True

    st.title(":material/terrain: Climbing training")
    tab_login, tab_signup = st.tabs([":material/login: Log in", ":material/person_add: Sign up"])

    with tab_login:
        with st.form("login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Log in", type="primary", width="stretch"):
                error, refresh_token = log_in(email, password)
                if error:
                    st.error(error)
                else:
                    cookies.set(REFRESH_TOKEN_COOKIE, refresh_token, max_age=COOKIE_MAX_AGE_SECONDS)
                    st.rerun()

    with tab_signup:
        with st.form("signup_form"):
            new_email = st.text_input("Email", key="signup_email")
            new_password = st.text_input("Password", type="password", key="signup_password")
            confirm_password = st.text_input("Confirm password", type="password", key="signup_confirm_password")
            if st.form_submit_button("Sign up", type="primary", width="stretch"):
                if new_password != confirm_password:
                    st.error("Passwords don't match.")
                else:
                    needs_confirmation, message, refresh_token = sign_up(new_email, new_password)
                    if needs_confirmation:
                        st.success(message)
                    elif refresh_token:
                        cookies.set(REFRESH_TOKEN_COOKIE, refresh_token, max_age=COOKIE_MAX_AGE_SECONDS)
                        st.rerun()
                    else:
                        st.error(message)

    st.stop()
    return False


def render_logout_control() -> None:
    """Sidebar element showing the logged-in email and a logout button."""
    with st.sidebar:
        st.caption(f"Logged in as {st.session_state.auth_user_email}")
        if st.button("Log out", icon=":material/logout:", width="stretch"):
            _cookies().remove(REFRESH_TOKEN_COOKIE)
            log_out()
            st.rerun()
