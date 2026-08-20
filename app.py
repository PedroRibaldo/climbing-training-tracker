"""
Climbing Training Tracker - Streamlit dashboard.

Loads session/exercise data from data_pipeline and renders the calendar,
analytics, exercise library, and goals tabs.
"""

import streamlit as st
import pandas as pd

from data_pipeline import load_clean_data, compute_kpis
from training_plan import get_active_goal, check_and_update_goal_completion
import theme
import whoop

from ui import session_modal, calendar_tab, analytics_tab, library_tab, goals_tab

st.set_page_config(page_title="Climbing Training Tracker", page_icon=":material/terrain:", layout="wide")

st.html(theme.inject_global_css())
st.html(theme.calendar_css())

# --- DATA LOADING ---
@st.cache_data
def fetch_data():
    """Cleared after writes via refresh_data()/refresh_all() below."""
    return load_clean_data()

with st.spinner("Loading your training data…"):
    df_past, df_future, df_dict = fetch_data()

@st.cache_data
def fetch_goal():
    return get_active_goal()

def refresh_data():
    """Callers rerun themselves - some need custom post-save behavior
    (see ui/session_modal.py's due-sessions carousel)."""
    fetch_data.clear()

def refresh_all():
    fetch_data.clear()
    fetch_goal.clear()

@st.cache_data
def fetch_whoop_enabled():
    return whoop.is_enabled()

@st.cache_data
def fetch_whoop_metrics():
    return whoop.get_daily_metrics()

def refresh_whoop_enabled():
    fetch_whoop_enabled.clear()

active_goal = fetch_goal()
if active_goal is not None:
    if check_and_update_goal_completion(active_goal, df_past, df_future):
        st.session_state.goal_just_completed = {
            'target_grade': active_goal['target_grade'],
            'target_type': active_goal['target_type'],
        }
        refresh_all()
        st.rerun()

completed = st.session_state.pop('goal_just_completed', None)
if completed:
    grade_label = "V-scale" if completed['target_type'] == 'moonboard' else "gym"
    st.toast(f"Goal reached: {completed['target_grade']} ({grade_label})!", icon=":material/celebration:")
    st.balloons()

# --- WHOOP TOGGLE (sidebar) ---
whoop_enabled = fetch_whoop_enabled()
with st.sidebar:
    st.subheader(":material/monitor_heart: WHOOP")
    new_whoop_enabled = st.toggle("Show WHOOP recovery data", value=whoop_enabled)
    if new_whoop_enabled != whoop_enabled:
        if whoop.set_enabled(new_whoop_enabled):
            refresh_whoop_enabled()
            st.rerun()

if whoop_enabled:
    df_whoop = pd.DataFrame(fetch_whoop_metrics())
    if not df_whoop.empty:
        df_whoop['date'] = pd.to_datetime(df_whoop['date'])
else:
    df_whoop = pd.DataFrame()

# Single combined view of every dated session, used to drive the calendar
df_all_calendar = pd.concat([df_past, df_future]).dropna(subset=['date']).copy()
df_all_calendar['date_str'] = df_all_calendar['date'].dt.strftime('%Y-%m-%d')

# Group exercises by phase for the UI tabs
exercises_before = df_dict[df_dict['phase'] == 'Before']['name'].dropna().unique().tolist()
exercises_during = df_dict[df_dict['phase'] == 'During']['name'].dropna().unique().tolist()
exercises_after = df_dict[df_dict['phase'] == 'After']['name'].dropna().unique().tolist()

# --- OVERDUE SESSIONS (drives the header notification bell) ---
due_mask = df_past['effort'].isna() & (df_past['category'] != 'Rest')
due_df = df_past[due_mask].sort_values(by='date', ascending=False)
due_count = len(due_df)

# --- HEADER + KPI STRIP ---
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

kpis = compute_kpis(df_past)
with st.container(horizontal=True):
    st.metric(":material/local_fire_department: Current streak", f"{kpis['streak']} d", border=True)
    st.metric(":material/date_range: This week", kpis['sessions_this_week'], border=True)
    acwr_value = "–" if kpis['acwr_current'] is None else f"{kpis['acwr_current']:.2f}"
    acwr_delta = None if kpis['acwr_delta'] is None else f"{kpis['acwr_delta']:+.2f}"
    st.metric(":material/monitoring: ACWR", acwr_value, delta=acwr_delta, delta_color="inverse", border=True)
    since_last = "–" if kpis['days_since_last'] is None else f"{kpis['days_since_last']} d"
    st.metric(":material/schedule: Since last session", since_last, border=True)
    if whoop_enabled and not df_whoop.empty:
        recovery = df_whoop.iloc[-1]['recovery_score']
        if pd.notna(recovery):
            st.metric(":material/monitor_heart: Recovery", f"{int(recovery)}%", border=True)

# --- CATCH UP ON DUE SESSIONS (opened via the header bell) ---
if st.session_state.get("due_carousel_open", False) and (
    st.session_state.get("due_carousel_index", 0) < len(st.session_state.get("due_sessions_queue", []))
):
    session_modal.due_sessions_carousel(
        df_all_calendar, df_past, df_whoop, df_dict, exercises_before, exercises_during, exercises_after, refresh_data,
    )

# --- TOP-LEVEL NAVIGATION ---
tab_calendar, tab_analytics, tab_library, tab_goals = st.tabs([
    ":material/calendar_month: Calendar", ":material/analytics: Analytics",
    ":material/fitness_center: Exercise library", ":material/flag: Goals",
])

with tab_calendar:
    calendar_tab.render(
        df_all_calendar, df_past, df_dict, exercises_before, exercises_during, exercises_after, refresh_data,
    )

with tab_analytics:
    analytics_tab.render(df_past, whoop_enabled, df_whoop)

with tab_library:
    library_tab.render(df_dict, refresh_data)

with tab_goals:
    goals_tab.render(active_goal, df_past, df_future, df_dict, refresh_data, refresh_all)
