"""
Climbing Training Tracker - Streamlit dashboard.

Reads cleaned session data from Supabase (via data_pipeline.py) and
renders:
- An interactive calendar for viewing/editing/adding training sessions.
- An analytics section (effort trend, grade progression, category mix)
  over a user-selected date range.
"""

import streamlit as st
import pandas as pd

from data_pipeline import load_clean_data, compute_kpis
from training_plan import get_active_goal, check_and_update_goal_completion
import theme

from ui import session_modal, calendar_tab, analytics_tab, library_tab, goals_tab

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Climbing Training Tracker", page_icon=":material/terrain:", layout="wide")

st.html(theme.inject_global_css())

# --- CUSTOM CSS FOR CALENDAR STYLING ---
st.html(f"""
<style>
.fc-daygrid-day-frame {{
    position: relative !important;
}}
.fc-daygrid-day-top {{
    position: absolute !important;
    top: 50% !important;
    left: 50% !important;
    transform: translate(-50%, -50%) !important;
    display: flex !important;
    justify-content: center !important;
    align-items: center !important;
    width: 100% !important;
    z-index: 10 !important;
    margin-top: 0 !important;
}}
.fc-daygrid-day-number {{
    font-family: {theme.FONT_MONO} !important;
    font-size: 1.5rem !important;
    font-weight: 700 !important;
    color: {theme.CHALK} !important;
    text-shadow: 1px 1px 3px {theme.BASALT}, -1px -1px 3px {theme.BASALT} !important;
    text-decoration: none !important;
}}
.fc-daygrid-day-events {{
    pointer-events: none !important;
}}
.fc-bg-event {{
    opacity: 0.85 !important;
}}
.fc-daygrid-day-frame {{
    cursor: pointer;
}}
@media (prefers-reduced-motion: no-preference) {{
    .fc-daygrid-day-frame {{
        transition: filter 150ms ease;
    }}
    .fc-daygrid-day-frame:hover {{
        filter: brightness(1.15);
    }}
}}
/* The calendar is a custom JS component that measures its own height and
   reports it back to Streamlit. Streamlit's tabs are purely client-side
   (switching tabs never reruns the Python script), so if a script rerun
   happens while this tab is hidden (e.g. triggered from the Goals tab),
   the component measures a hidden (0-height) element and gets stuck
   reporting 0 until a full page reload. Forcing a minimum height here
   keeps the calendar visible regardless of what the component reports. */
iframe[data-testid="stCustomComponentV1"] {{
    min-height: 650px !important;
}}
</style>
""")

# --- DATA LOADING ---
@st.cache_data
def fetch_data():
    """Cached wrapper around load_clean_data() so every rerun doesn't hit
    Supabase. Cleared explicitly after any write (see the
    modal's save/delete/add actions below)."""
    return load_clean_data()

with st.spinner("Loading your training data…"):
    df_past, df_future, df_dict = fetch_data()

@st.cache_data
def fetch_goal():
    """Cached wrapper around get_active_goal(), mirroring fetch_data()."""
    return get_active_goal()

def refresh_data():
    """Clear the cached session/exercise data. Callers decide when to
    st.rerun() themselves, since some paths need custom post-save behavior
    (see ui/session_modal.py's due-sessions carousel)."""
    fetch_data.clear()

def refresh_all():
    """Clear the cached session/exercise data and the cached active goal."""
    fetch_data.clear()
    fetch_goal.clear()

active_goal = fetch_goal()
if active_goal is not None:
    if check_and_update_goal_completion(active_goal, df_past, df_future):
        refresh_all()
        st.rerun()

# Single combined view of every dated session, used to drive the calendar
df_all_calendar = pd.concat([df_past, df_future]).dropna(subset=['date']).copy()
df_all_calendar['date_str'] = df_all_calendar['date'].dt.strftime('%Y-%m-%d')

# Group exercises by phase for the UI tabs
if not df_dict.empty and 'phase' in df_dict.columns and 'name' in df_dict.columns:
    exercises_before = df_dict[df_dict['phase'] == 'Before']['name'].dropna().unique().tolist()
    exercises_during = df_dict[df_dict['phase'] == 'During']['name'].dropna().unique().tolist()
    exercises_after = df_dict[df_dict['phase'] == 'After']['name'].dropna().unique().tolist()
else:
    exercises_before, exercises_during, exercises_after = [], [], []


# --- HEADER + KPI STRIP ---
st.title(":material/terrain: Climbing training")

kpis = compute_kpis(df_past)
with st.container(horizontal=True):
    st.metric(":material/local_fire_department: Current streak", f"{kpis['streak']} d", border=True)
    st.metric(":material/date_range: This week", kpis['sessions_this_week'], border=True)
    acwr_value = "–" if kpis['acwr_current'] is None else f"{kpis['acwr_current']:.2f}"
    acwr_delta = None if kpis['acwr_delta'] is None else f"{kpis['acwr_delta']:+.2f}"
    st.metric(":material/monitoring: ACWR", acwr_value, delta=acwr_delta, delta_color="inverse", border=True)
    since_last = "–" if kpis['days_since_last'] is None else f"{kpis['days_since_last']} d"
    st.metric(":material/schedule: Since last session", since_last, border=True)


# --- CATCH UP ON DUE SESSIONS (runs once per browser session) ---
if "due_sessions_checked" not in st.session_state:
    st.session_state.due_sessions_checked = True
    due_mask = df_past['effort'].isna() & (df_past['category'] != 'Rest')
    due_df = df_past[due_mask].sort_values(by='date', ascending=False)
    st.session_state.due_sessions_queue = due_df['id'].tolist()
    st.session_state.due_carousel_index = 0

if st.session_state.due_carousel_index < len(st.session_state.get("due_sessions_queue", [])):
    session_modal.due_sessions_carousel(
        df_all_calendar, df_past, df_dict, exercises_before, exercises_during, exercises_after, refresh_data,
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
    analytics_tab.render(df_past)

with tab_library:
    library_tab.render(df_dict, refresh_data)

with tab_goals:
    goals_tab.render(active_goal, df_past, df_future, df_dict, refresh_data, refresh_all)
