"""
Sidebar WHOOP toggle, page header (title, notification bell, KPI strip),
and the due-sessions catch-up carousel the bell opens.
"""

import pandas as pd
import streamlit as st

import theme
import whoop
from . import session_modal


def render_whoop_toggle(whoop_enabled: bool, refresh_whoop_enabled) -> None:
    """Sidebar toggle for WHOOP recovery data; reruns immediately on
    change so the rest of this run already reflects the new value."""
    with st.sidebar:
        st.subheader(":material/monitor_heart: WHOOP")
        new_whoop_enabled = st.toggle("Show WHOOP recovery data", value=whoop_enabled)
        if new_whoop_enabled != whoop_enabled:
            if whoop.set_enabled(new_whoop_enabled):
                refresh_whoop_enabled()
                st.rerun()


def render(
    kpis, whoop_enabled, df_whoop, df_whoop_workouts, due_df, df_all_calendar, df_past, df_dict,
    exercises_before, exercises_during, exercises_after, refresh_data,
):
    """Title, notification bell, and KPI strip; opens the due-sessions
    carousel when the bell is clicked or a catch-up is already in progress."""
    due_count = len(due_df)

    col_title, col_bell = st.columns([10, 1], vertical_alignment="center")
    with col_title:
        st.title(":material/terrain: Climbing training")
    with col_bell:
        st.html(theme.notification_bell_css(due_count))
        bell_help = f"{due_count} overdue session{'s' if due_count != 1 else ''}" if due_count else "You're all caught up"
        if st.button("", icon=":material/notifications:", key="notif_bell", help=bell_help, disabled=(due_count == 0)):
            st.session_state.due_sessions_queue = due_df['id'].tolist()
            st.session_state.due_carousel_index = 0
            st.session_state.due_carousel_open = True

    with st.container(horizontal=True):
        st.metric(":material/date_range: This week", kpis['sessions_this_week'], border=True)
        acwr_value = "–" if kpis['acwr_current'] is None else f"{kpis['acwr_current']:.2f}"
        acwr_delta = None if kpis['acwr_delta'] is None else f"{kpis['acwr_delta']:+.2f}"
        st.metric(":material/monitoring: ACWR", acwr_value, delta=acwr_delta, delta_color="inverse", border=True)
        if whoop_enabled and not df_whoop.empty:
            recovery = df_whoop.iloc[-1]['recovery_score']
            if pd.notna(recovery):
                st.metric(":material/monitor_heart: Recovery", f"{int(recovery)}%", border=True)
        if whoop_enabled:
            weekly_averages = whoop.compute_weekly_workout_averages(df_whoop_workouts)
            avg_duration_text = "–" if weekly_averages['avg_duration_min'] is None else f"{weekly_averages['avg_duration_min']:.0f} min"
            st.metric(":material/timer: Avg duration (week)", avg_duration_text, border=True)
            avg_hr_text = "–" if weekly_averages['avg_hr'] is None else f"{weekly_averages['avg_hr']:.0f} bpm"
            st.metric(":material/monitor_heart: Avg HR (week)", avg_hr_text, border=True)

    if st.session_state.get("due_carousel_open", False) and (
        st.session_state.get("due_carousel_index", 0) < len(st.session_state.get("due_sessions_queue", []))
    ):
        session_modal.due_sessions_carousel(
            df_all_calendar, df_past, df_whoop, df_whoop_workouts, df_dict, exercises_before, exercises_during, exercises_after, refresh_data,
        )
