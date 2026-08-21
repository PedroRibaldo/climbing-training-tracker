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

from ui import header, calendar_tab, analytics_tab, library_tab, goals_tab, whoop_tab

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

@st.cache_data
def fetch_whoop_workouts():
    return whoop.get_climbing_workouts()

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
header.render_whoop_toggle(whoop_enabled, refresh_whoop_enabled)

if whoop_enabled:
    df_whoop = pd.DataFrame(fetch_whoop_metrics())
    if not df_whoop.empty:
        df_whoop['date'] = pd.to_datetime(df_whoop['date'])
    df_whoop_workouts = pd.DataFrame(fetch_whoop_workouts())
    if not df_whoop_workouts.empty:
        df_whoop_workouts['date'] = pd.to_datetime(df_whoop_workouts['date'])
else:
    df_whoop = pd.DataFrame()
    df_whoop_workouts = pd.DataFrame()

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

# --- HEADER + KPI STRIP ---
kpis = compute_kpis(df_past)
header.render(
    kpis, whoop_enabled, df_whoop, df_whoop_workouts, due_df, df_all_calendar, df_past, df_dict,
    exercises_before, exercises_during, exercises_after, refresh_data,
)

# --- TOP-LEVEL NAVIGATION ---
tab_labels = [":material/calendar_month: Calendar", ":material/analytics: Analytics"]
if whoop_enabled:
    tab_labels.append(":material/monitor_heart: Whoop")
tab_labels += [":material/fitness_center: Exercise library", ":material/flag: Goals"]

tabs = st.tabs(tab_labels)
tab_calendar, tab_analytics = tabs[0], tabs[1]
if whoop_enabled:
    tab_whoop, tab_library, tab_goals = tabs[2], tabs[3], tabs[4]
else:
    tab_whoop = None
    tab_library, tab_goals = tabs[2], tabs[3]

with tab_calendar:
    calendar_tab.render(
        df_all_calendar, df_past, df_dict, exercises_before, exercises_during, exercises_after, refresh_data,
        df_whoop_workouts,
    )

with tab_analytics:
    analytics_tab.render(df_past)

if whoop_enabled:
    with tab_whoop:
        whoop_tab.render(df_whoop, df_whoop_workouts)

with tab_library:
    library_tab.render(df_dict, refresh_data)

with tab_goals:
    goals_tab.render(active_goal, df_past, df_future, df_dict, refresh_data, refresh_all)
