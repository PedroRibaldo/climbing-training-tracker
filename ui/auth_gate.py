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

    # A fixed-width card centered on the page - full-width tabs/forms on
    # st.set_page_config(layout="wide") would otherwise stretch edge to
    # edge, which reads as unstyled for a first-impression login screen.
    with st.container(horizontal_alignment="center"):
        with st.container(width=420, border=True):
            st.title(":material/terrain: Climbing training", text_alignment="center")
            st.caption("Log in to track your sessions and training plans.", text_alignment="center")

            tab_login, tab_signup = st.tabs([":material/login: Log in", ":material/person_add: Sign up"])

            with tab_login:
                with st.form("login_form", border=False):
                    email = st.text_input("Email", icon=":material/mail:", autocomplete="email")
                    password = st.text_input(
                        "Password", type="password", icon=":material/lock:", autocomplete="current-password",
                    )
                    if st.form_submit_button("Log in", type="primary", width="stretch"):
                        with st.spinner("Logging in…"):
                            error, refresh_token = log_in(email, password)
                        if error:
                            st.error(error)
                        else:
                            cookies.set(REFRESH_TOKEN_COOKIE, refresh_token, max_age=COOKIE_MAX_AGE_SECONDS)
                            st.rerun()

            with tab_signup:
                with st.form("signup_form", border=False):
                    new_email = st.text_input(
                        "Email", icon=":material/mail:", autocomplete="email", key="signup_email",
                    )
                    new_password = st.text_input(
                        "Password", type="password", icon=":material/lock:", autocomplete="new-password",
                        key="signup_password",
                    )
                    st.caption("At least 6 characters.")
                    confirm_password = st.text_input(
                        "Confirm password", type="password", icon=":material/lock_reset:", autocomplete="new-password",
                        key="signup_confirm_password",
                    )
                    if st.form_submit_button("Sign up", type="primary", width="stretch"):
                        if new_password != confirm_password:
                            st.error("Passwords don't match.")
                        else:
                            with st.spinner("Creating your account…"):
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


def end_session() -> None:
    """Clears the refresh-token cookie and local session state. Shared by
    the logout button and, after a successful account deletion, by
    ui/profile_panel.py."""
    _cookies().remove(REFRESH_TOKEN_COOKIE)
    log_out()


def render_logout_control() -> None:
    """Sidebar element showing the logged-in email and a logout button."""
    with st.sidebar:
        st.caption(f":material/account_circle: Logged in as {st.session_state.auth_user_email}")
        if st.button("Log out", icon=":material/logout:", width="stretch"):
            end_session()
            st.rerun()
