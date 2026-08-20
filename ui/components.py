"""
Shared, cross-screen Streamlit UI helpers used by multiple ui/ modules.

Unlike theme.py (pure color/CSS/HTML string generation, no state), these
functions render widgets and read/write st.session_state directly.
"""

import streamlit as st


def confirm_action(
    state_key,
    warning_text,
    confirm_label,
    on_confirm,
    on_success=None,
    confirm_icon=":material/warning:",
    spinner_text="Working…",
    key_prefix=None,
):
    """Two-step confirm flow: renders nothing until state_key is present in
    st.session_state (set by the caller's trigger button), then shows a
    warning + Yes/Cancel columns.

    Checks presence, not truthiness: some callers store an id (not True) at
    state_key to scope confirmation to one entity among several (e.g. "delete
    exercise 0" must still show the warning even though 0 is falsy) - see
    ui/exercise_modals.py and ui/session_modal.py's delete-confirm call sites.

    on_confirm: zero-arg callable, runs the action and returns a success bool.
    on_success: zero-arg callable, run only if on_confirm returned True
        (e.g. refresh_data, or a caller-specific finish routine that may
        itself call st.rerun()).

    Always reruns after Yes, whether or not the action succeeded - a failed
    on_confirm clears its own confirm UI on the same click instead of
    leaving the warning/buttons stuck on screen.
    """
    if state_key not in st.session_state:
        return

    st.warning(warning_text)
    kp = key_prefix or state_key
    col_yes, col_no = st.columns(2)
    with col_yes:
        if st.button(confirm_label, icon=confirm_icon, width="stretch", key=f"danger_confirm_{kp}_yes"):
            with st.spinner(spinner_text):
                success = on_confirm()
            st.session_state.pop(state_key, None)
            if success and on_success:
                on_success()
            st.rerun()
    with col_no:
        if st.button("Cancel", icon=":material/close:", width="stretch", key=f"cancel_{kp}"):
            st.session_state.pop(state_key, None)
            st.rerun()


def chart_or_empty(has_data, render_fn, empty_message, empty_icon=":material/info:"):
    """Renders render_fn() when has_data is true, otherwise a consistent
    icon-prefixed st.info() fallback."""
    if has_data:
        render_fn()
    else:
        st.info(empty_message, icon=empty_icon)


STATIC_CHART_CONFIG = {"displayModeBar": False, "scrollZoom": False}


def render_chart(fig):
    """Renders a Plotly figure as view-only: no toolbar, no zoom/pan/select
    drag. Hover tooltips still work."""
    fig.update_layout(dragmode=False)
    st.plotly_chart(fig, config=STATIC_CHART_CONFIG)
