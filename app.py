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
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from streamlit_calendar import calendar

from data_pipeline import load_clean_data, update_session, add_session, delete_session, add_exercise, update_exercise, delete_exercise, compute_acwr, compute_kpis, get_peak_sessions, PipelineConfig
from training_plan import (
    PlanConfig, preview_plan, create_goal_and_plan, get_active_goal, regenerate_plan, abandon_goal,
    check_and_update_goal_completion, select_exercises_for_day,
)
import theme

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Climbing Training Tracker", page_icon=":material/terrain:", layout="wide")

st.html(theme.inject_global_css())

# --- CUSTOM CSS FOR CALENDAR STYLING ---
# Centers the day number over each cell and makes it legible against the
# background color used for that day's training category (see theme.CATEGORY_COLORS).
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

active_goal = fetch_goal()
if active_goal is not None:
    if check_and_update_goal_completion(active_goal, df_past, df_future):
        fetch_data.clear()
        fetch_goal.clear()
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


# --- EDIT/CREATE SESSION MODAL (POP-UP) ---
def _category_exercise_pool(category, df_dict):
    """Every During exercise select_exercises_for_day would include for
    this category (mandatory + category-tagged, excluding anything
    flagged exclude_from_plan) - or none at all for Free/Rest, which
    can't be pre-planned."""
    if category in ('Free', 'Rest'):
        return []
    return select_exercises_for_day(category, df_dict, {})['during']


def _render_session_edit_form(session_data, is_new=False, on_saved=None):
    """Renders the actual session form (fields + save/delete buttons).

    Shared by edit_session_modal() (opened from a calendar click) and
    due_sessions_carousel() (auto-opened on load for overdue sessions)

    on_saved: called instead of the default fetch_data.clear()+st.rerun()
    after a successful save/delete
    """
    st.write(f"**Date:** {session_data['date'].strftime('%d/%m/%Y')}")

    with st.container(border=True):
        st.markdown("**Details**")

        # 1. Form inputs
        if is_new:
            cat_opts = PipelineConfig.ALLOWED_CATEGORIES
            new_cat = st.selectbox("Category", cat_opts)
        else:
            cat_opts = PipelineConfig.ALLOWED_CATEGORIES
            current_cat = session_data['category'] if session_data['category'] in cat_opts else cat_opts[0]
            new_cat = st.selectbox("Category", cat_opts, index=cat_opts.index(current_cat))

        current_effort = None if pd.isna(session_data['effort']) else int(session_data['effort'])
        new_effort = st.number_input("Effort (1-10)", min_value=1, max_value=10, value=current_effort, step=1)

        gym_opts = [""] + list(PipelineConfig.GYM_MAPPING.keys())
        current_gym = session_data['gym_grade'] if pd.notna(session_data['gym_grade']) and session_data['gym_grade'] in gym_opts else ""
        new_gym = st.selectbox("Max gym grade", gym_opts, index=gym_opts.index(current_gym))

        mb_opts = [""] + list(PipelineConfig.MOONBOARD_MAPPING.keys())
        current_mb = session_data['moonboard_grade'] if pd.notna(session_data['moonboard_grade']) and session_data['moonboard_grade'] in mb_opts else ""
        new_mb = st.selectbox("Max Moonboard grade", mb_opts, index=mb_opts.index(current_mb))

    with st.container(border=True):
        # 2. Exercises
        st.markdown("**Exercises**")

        session_key = session_data['id'] if pd.notna(session_data['id']) else session_data['date'].strftime('%Y%m%d')

        # Determine default selections
        if is_new:
            # Smart State Injection: Fetch "Before" and "After" from the most recent past session
            default_before = []
            default_during = _category_exercise_pool(new_cat, df_dict)
            default_after = []

            if not df_past.empty:
                # Grab the absolute most recent session logged
                latest_session = df_past.sort_values(by='date', ascending=False).iloc[0]
                if pd.notna(latest_session['exercises']):
                    last_exercises = [ex.strip() for ex in str(latest_session['exercises']).split(',') if ex.strip()]
                    # Only inject the ones that belong to the Before or After phases
                    default_before = [ex for ex in last_exercises if ex in exercises_before]
                    default_after = [ex for ex in last_exercises if ex in exercises_after]
        else:
            # Editing an existing session: Load its specific exercises
            current_text = "" if pd.isna(session_data['exercises']) else str(session_data['exercises'])
            current_list = [ex.strip() for ex in current_text.split(',') if ex.strip()]

            default_before = [ex for ex in current_list if ex in exercises_before]
            default_during = [ex for ex in current_list if ex in exercises_during]
            default_after = [ex for ex in current_list if ex in exercises_after]

        during_key = f"ex_during_{session_key}"
        prev_cat_key = f"prev_cat_{session_key}"
        if prev_cat_key in st.session_state and st.session_state[prev_cat_key] != new_cat:
            st.session_state[during_key] = _category_exercise_pool(new_cat, df_dict)
        st.session_state[prev_cat_key] = new_cat

        # Render Mobile Tabs
        tab1, tab2, tab3 = st.tabs([
            ":material/directions_run: Warm-up", ":material/terrain: Climbing", ":material/self_improvement: Cool-down",
        ])

        with tab1:
            selected_before = st.multiselect(
                "Before", options=exercises_before, default=default_before,
                key=f"ex_before_{session_key}", label_visibility="collapsed"
            )
        with tab2:
            selected_during = st.multiselect(
                "During", options=exercises_during, default=default_during,
                key=during_key, label_visibility="collapsed"
            )
        with tab3:
            selected_after = st.multiselect(
                "After", options=exercises_after, default=default_after,
                key=f"ex_after_{session_key}", label_visibility="collapsed"
            )

        # Combine them all into a single list for the save function
        selected_exercises = selected_before + selected_during + selected_after

    def _finish():
        fetch_data.clear()
        st.session_state.pop('confirm_delete_session_id', None)
        if on_saved:
            on_saved()
        else:
            st.rerun()

    # 3. Save & delete actions
    if is_new:
        if st.button("Log new session", icon=":material/save:", type="primary", width="stretch"):
            new_session_data = {
                'Date': session_data['date'].strftime('%d/%m/%Y'),
                'Category': new_cat,
                'Effort Scale': new_effort,
                'Max Gym Grade Color': new_gym,
                'Max Moonboard Grade': new_mb,
                'Exercises': ", ".join(selected_exercises)
            }
            with st.spinner("Saving…"):
                success = add_session(new_session_data)
            if success:
                _finish()
    else:
        session_id = int(session_data['id'])
        col_save, col_del = st.columns(2)
        with col_save:
            if st.button("Save changes", icon=":material/save:", type="primary", width="stretch"):
                updated_data = {
                    'Category': new_cat,
                    'Effort Scale': new_effort,
                    'Max Gym Grade Color': new_gym,
                    'Max Moonboard Grade': new_mb,
                    'Exercises': ", ".join(selected_exercises)
                }
                with st.spinner("Saving…"):
                    success = update_session(session_id, updated_data)
                if success:
                    _finish()
        with col_del:
            if st.button("Delete session", icon=":material/delete:", width="stretch", key=f"danger_delete_session_{session_id}"):
                st.session_state.confirm_delete_session_id = session_id

        # Two-step delete confirmation, mirroring the exercise delete pattern
        if st.session_state.get('confirm_delete_session_id') == session_id:
            st.warning("Delete this session permanently? This also removes its logged exercises.")
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("Yes, delete", icon=":material/warning:", width="stretch", key=f"danger_confirm_del_session_yes_{session_id}"):
                    with st.spinner("Deleting…"):
                        success = delete_session(session_id)
                    if success:
                        _finish()
            with col_no:
                if st.button("Cancel", icon=":material/close:", width="stretch", key=f"confirm_del_session_no_{session_id}"):
                    st.session_state.pop('confirm_delete_session_id', None)
                    st.rerun()


@st.dialog("Session details", icon=":material/edit:")
def edit_session_modal(session_data, is_new=False):
    """Pop-up form for viewing/editing an existing session, or logging a
    new one when is_new=True
    """
    _render_session_edit_form(session_data, is_new=is_new)


def _advance_due_carousel():
    """Moves the due-sessions carousel to the next entry"""
    st.session_state.due_carousel_index += 1
    st.rerun()


@st.dialog("Catch up on missed sessions", icon=":material/schedule:")
def due_sessions_carousel():
    """Auto-opened on page load when past sessions have no effort logged.
    Saving, deleting, or skipping the current one all advance
    to the next; running out of the queue closes the dialog.
    """
    queue = st.session_state.due_sessions_queue
    idx = st.session_state.due_carousel_index

    if idx >= len(queue):
        return  # queue exhausted - nothing left to show, dialog closes

    session_id = queue[idx]
    matches = df_all_calendar[df_all_calendar['id'] == session_id]
    if matches.empty:
        # Edited/deleted by some other path since the queue was built
        _advance_due_carousel()
        return
    session_data = matches.iloc[0]

    col_prev, col_mid, col_next = st.columns([1, 3, 1])
    with col_prev:
        if st.button("", icon=":material/chevron_left:", disabled=(idx == 0), width="stretch", key="due_carousel_prev", help="Previous overdue session"):
            st.session_state.due_carousel_index -= 1
            st.rerun()
    with col_mid:
        st.markdown(f"Overdue session {idx + 1} of {len(queue)}", text_alignment="center")
    with col_next:
        if st.button("", icon=":material/chevron_right:", disabled=(idx == len(queue) - 1), width="stretch", key="due_carousel_next", help="Next overdue session"):
            st.session_state.due_carousel_index += 1
            st.rerun()

    st.warning("This session is missing its effort - fill it in, delete it, remind yourself later, or dismiss the whole list for now.")

    _render_session_edit_form(session_data, is_new=False, on_saved=_advance_due_carousel)

    col_skip, col_dismiss = st.columns(2)
    with col_skip:
        if st.button("Remind me later", icon=":material/skip_next:", width="stretch", key="due_carousel_skip"):
            _advance_due_carousel()
    with col_dismiss:
        if st.button("Dismiss all", icon=":material/close:", width="stretch", key="due_carousel_dismiss_all"):
            st.session_state.due_carousel_index = len(queue)
            st.rerun()


def _make_blank_session(clicked_date_str: str) -> pd.Series:
    """Build a synthetic empty session row for a day with no logged data,
    so the modal can be reused for both editing and creating sessions."""
    return pd.Series({
        'id': None,
        'date': pd.to_datetime(clicked_date_str),
        'category': '',
        'effort': pd.NA,
        'gym_grade': np.nan,
        'moonboard_grade': np.nan,
        'exercises': ''
    })


# --- CATCH UP ON DUE SESSIONS (runs once per browser session) ---
# "Due" = a past session with no effort logged, i.e. it was scheduled but
# never followed up on. Rest days are excluded
if "due_sessions_checked" not in st.session_state:
    st.session_state.due_sessions_checked = True
    due_mask = df_past['effort'].isna() & (df_past['category'] != 'Rest')
    due_df = df_past[due_mask].sort_values(by='date', ascending=False)
    st.session_state.due_sessions_queue = due_df['id'].tolist()
    st.session_state.due_carousel_index = 0

# Re-checked on every rerun (not just the first). A dialog only stays visually open if the
# script re-invokes its function on the following rerun
if st.session_state.due_carousel_index < len(st.session_state.get("due_sessions_queue", [])):
    due_sessions_carousel()


# --- TOP-LEVEL NAVIGATION ---
tab_calendar, tab_analytics, tab_library, tab_goals = st.tabs([
    ":material/calendar_month: Calendar", ":material/analytics: Analytics",
    ":material/fitness_center: Exercise library", ":material/flag: Goals",
])

with tab_calendar:
    st.caption("Click any colored session to edit it, or click a blank day to log a missed session.")
    st.html(theme.color_key_html(theme.CATEGORY_COLORS, title="Category key"))

    # Sessions are rendered as full-day background color blocks rather than
    # titled events, so the calendar reads like a training-day heatmap
    calendar_events = [
        {
            "title": str(row['category']) if pd.notna(row['category']) else "Unknown",
            "start": row['date_str'],
            "color": theme.CATEGORY_COLORS.get(str(row['category']), theme.CATEGORY_FALLBACK_COLOR),
            "display": "background",
            "extendedProps": {"date_str": row['date_str']}
        }
        for _, row in df_all_calendar.iterrows()
    ]

    calendar_options = {
        "editable": "false",
        "selectable": "true",
        "height": "auto",
        "headerToolbar": {
            "left": "prev,next today",
            "center": "title",
            "right": "dayGridMonth,dayGridWeek"
        },
        "initialView": "dayGridMonth",
    }
    if st.session_state.get("calendar_initial_date"):
        calendar_options["initialDate"] = st.session_state.calendar_initial_date
    
    cal = calendar(
        events=calendar_events, options=calendar_options, callbacks=['dateClick'],
        key=f"calendar_{st.session_state.get('calendar_nonce', 0)}",
    )

    if cal.get("callback") == "dateClick":
        raw_clicked_date = str(cal["dateClick"]["date"])
        clean_clicked_date = raw_clicked_date.split("T")[0]

        existing_session = df_all_calendar[df_all_calendar['date_str'] == clean_clicked_date]

        st.session_state.calendar_nonce = st.session_state.get("calendar_nonce", 0) + 1
        st.session_state.calendar_initial_date = clean_clicked_date

        if not existing_session.empty:
            edit_session_modal(existing_session.iloc[0], is_new=False)
        else:
            edit_session_modal(_make_blank_session(clean_clicked_date), is_new=True)


with tab_analytics:
    today_date = pd.to_datetime('today').date()
    last_month_date = today_date - pd.Timedelta(days=30)

    date_range = st.date_input(
        ":material/date_range: Select analytics date range",
        value=(last_month_date, today_date),
        max_value=today_date
    )

    if len(date_range) == 2:
        start_date, end_date = date_range
        # Rest days are excluded from analytics since they carry no effort/grade data
        mask = (df_past['date'].dt.date >= start_date) & (df_past['date'].dt.date <= end_date) & (df_past['category'] != 'Rest')
        df_analytics = df_past[mask].copy()

        col1, col2, col3 = st.columns(3)

        with col1:
            st.subheader(":material/local_fire_department: Training intensity")
            df_effort = df_analytics.dropna(subset=['effort']).sort_values(by='date')

            if not df_effort.empty:
                fig = px.line(df_effort, x='date', y='effort', markers=True, template=theme.PLOTLY_TEMPLATE)
                fig.update_traces(line_color=theme.ACCENT, marker=dict(color=theme.ACCENT, size=8))
                fig.update_yaxes(title="Effort (1-10)", range=[0, 10.5])
                fig.update_xaxes(title="", tickformat="%d/%m")
                st.plotly_chart(fig)
            else:
                st.info("No effort data logged.")

        with col2:
            st.subheader(":material/trending_up: Grade progression")
            # -1 encodes "no grade logged that day" (see clean_data), so those rows are excluded here
            df_gym = df_analytics[df_analytics['gym_numeric'] != -1].sort_values(by='date')
            df_moonboard = df_analytics[df_analytics['moonboard_numeric'] != -1].sort_values(by='date')

            if not df_gym.empty or not df_moonboard.empty:
                gym_rev_map = {v: k for k, v in PipelineConfig.GYM_MAPPING.items()}
                mb_rev_map = {v: k for k, v in PipelineConfig.MOONBOARD_MAPPING.items()}

                # Gym grade and Moonboard grade use different scales, so they
                # share the x-axis (date) but get independent y-axes
                fig_grades = make_subplots(specs=[[{"secondary_y": True}]])
                if not df_gym.empty:
                    fig_grades.add_trace(go.Scatter(
                        x=df_gym['date'], y=df_gym['gym_numeric'], name='Gym Grade',
                        mode='lines+markers', marker=dict(symbol='square'),
                        line_color=theme.GRADE_COLORS["Blue"],
                    ), secondary_y=False)
                if not df_moonboard.empty:
                    fig_grades.add_trace(go.Scatter(
                        x=df_moonboard['date'], y=df_moonboard['moonboard_numeric'], name='Moonboard',
                        mode='lines+markers', marker=dict(symbol='triangle-up'),
                        line_color=theme.GRADE_COLORS["Purple"],
                    ), secondary_y=True)

                fig_grades.update_layout(template=theme.PLOTLY_TEMPLATE, legend=dict(orientation='h', y=1.15))
                fig_grades.update_yaxes(
                    title_text="Gym Color", secondary_y=False, color=theme.GRADE_COLORS["Blue"],
                    tickvals=list(gym_rev_map.keys()), ticktext=list(gym_rev_map.values()),
                )
                fig_grades.update_yaxes(
                    title_text="Moonboard (V)", secondary_y=True, color=theme.GRADE_COLORS["Purple"],
                    tickvals=list(mb_rev_map.keys()), ticktext=list(mb_rev_map.values()),
                )
                fig_grades.update_xaxes(title="", tickformat="%d/%m")
                st.plotly_chart(fig_grades)
            else:
                st.info("No grade data logged.")

        with col3:
            st.subheader(":material/pie_chart: Distribution")
            df_dist = df_analytics[df_analytics['category'] != 'Rest']

            if not df_dist.empty:
                category_counts = df_dist['category'].value_counts()
                fig_dist = px.pie(
                    names=category_counts.index,
                    values=category_counts.values,
                    color=category_counts.index,
                    color_discrete_map=theme.CATEGORY_COLORS,
                    template=theme.PLOTLY_TEMPLATE,
                )
                fig_dist.update_traces(
                    textinfo='percent+label',
                    marker=dict(line=dict(color=theme.BASALT, width=1.5)),
                )
                st.plotly_chart(fig_dist)
            else:
                st.info("No training sessions logged.")

        st.subheader(":material/query_stats: Advanced analytics")

        col4, col5 = st.columns(2)

        with col4:
            st.markdown("**:material/monitoring: Acute:Chronic Workload Ratio**")
            # Computed over the full training history (not just the selected
            # range)
            acwr_df = compute_acwr(df_past)
            acwr_windowed = acwr_df[(acwr_df.index.date >= start_date) & (acwr_df.index.date <= end_date)]

            if not acwr_windowed.empty and acwr_windowed['acwr'].notna().any():
                band_top = max(2.0, acwr_windowed['acwr'].max(skipna=True) + 0.2)
                band_defs = [
                    (0.8, 1.3, "sweet_spot", "Sweet spot"),
                    (1.3, 1.5, "caution", "Caution"),
                    (1.5, band_top, "high_risk", "High risk"),
                ]
                fig_acwr = go.Figure()
                for y0, y1, key, label in band_defs:
                    fig_acwr.add_hrect(y0=y0, y1=y1, fillcolor=theme.ACWR_BAND_COLORS[key], opacity=0.15, line_width=0)
                    fig_acwr.add_trace(go.Scatter(
                        x=[None], y=[None], mode='markers',
                        marker=dict(size=10, color=theme.ACWR_BAND_COLORS[key]), name=label,
                    ))
                fig_acwr.add_trace(go.Scatter(
                    x=acwr_windowed.index, y=acwr_windowed['acwr'], mode='lines+markers',
                    line_color=theme.ACCENT, name='ACWR', showlegend=False,
                ))
                fig_acwr.update_layout(template=theme.PLOTLY_TEMPLATE, legend=dict(orientation='h', y=1.2, x=0))
                fig_acwr.update_yaxes(title="ACWR", range=[0, band_top])
                fig_acwr.update_xaxes(title="", type='date', tickformat="%d/%m")
                st.plotly_chart(fig_acwr)
                st.caption("Recent (7-day) vs. baseline (28-day) training load. Needs a few weeks of consistent logging to be meaningful.")
            else:
                st.info("Not enough training history yet to compute ACWR.")

        with col5:
            st.markdown("**:material/scatter_plot: Effort vs. grade yield**")
            df_yield = df_analytics.dropna(subset=['effort'])
            df_gym_yield = df_yield[df_yield['gym_numeric'] != -1]
            df_mb_yield = df_yield[df_yield['moonboard_numeric'] != -1]

            if not df_gym_yield.empty or not df_mb_yield.empty:
                fig_yield = go.Figure()
                if not df_gym_yield.empty:
                    fig_yield.add_trace(go.Scatter(
                        x=df_gym_yield['effort'], y=df_gym_yield['gym_numeric'], mode='markers', name='Gym',
                        marker=dict(color=theme.GRADE_COLORS["Blue"], opacity=0.7),
                    ))
                if not df_mb_yield.empty:
                    fig_yield.add_trace(go.Scatter(
                        x=df_mb_yield['effort'], y=df_mb_yield['moonboard_numeric'], mode='markers', name='Moonboard',
                        marker=dict(color=theme.GRADE_COLORS["Purple"], opacity=0.7),
                    ))
                fig_yield.update_layout(template=theme.PLOTLY_TEMPLATE, xaxis_title="Effort (1-10)", yaxis_title="Max grade (encoded)")
                st.plotly_chart(fig_yield)
            else:
                st.info("No grade data logged in this range.")

        st.markdown("**:material/emoji_events: Peak performance highlights**")
        top_sessions = get_peak_sessions(df_analytics, n=3)

        if not top_sessions.empty:
            gym_rev_map = {v: k for k, v in PipelineConfig.GYM_MAPPING.items()}
            mb_rev_map = {v: k for k, v in PipelineConfig.MOONBOARD_MAPPING.items()}
            highlight_cols = st.columns(len(top_sessions))

            for col, (_, session) in zip(highlight_cols, top_sessions.iterrows()):
                with col:
                    st.markdown(f"**{session['date'].strftime('%d/%m/%Y')}**")
                    st.caption(session['category'])
                    if session['gym_numeric'] != -1:
                        st.markdown(f":material/terrain: Gym: {gym_rev_map.get(int(session['gym_numeric']), '-')}")
                    if session['moonboard_numeric'] != -1:
                        st.markdown(f":material/grid_view: Moonboard: {mb_rev_map.get(int(session['moonboard_numeric']), '-')}")
                    if pd.notna(session['effort']):
                        st.markdown(f":material/local_fire_department: Effort: {int(session['effort'])}/10")
        else:
            st.info("No sessions to highlight in this range yet.")
    else:
        st.warning("Please select an end date to view analytics.")


@st.dialog("New exercise", icon=":material/add:")
def add_exercise_modal():
    new_name = st.text_input("Name")

    type_opts = PipelineConfig.ALLOWED_EXERCISE_TYPES
    new_type = st.selectbox("Type", type_opts)

    new_sets = st.number_input("Sets", min_value=0, value=None, step=1)
    if new_type == 'Reps':
        new_reps = st.number_input("Reps", min_value=0, value=None, step=1)
        new_time = None
    else:
        new_reps = None
        new_time = st.text_input("Time (e.g. 00:15)")
    new_rest = st.number_input("Rest", min_value=0, value=None, step=1)
    new_comments = st.text_area("Comments")

    phase_opts = PipelineConfig.ALLOWED_PHASES
    new_phase = st.selectbox("Phase", phase_opts)

    category_opts = PipelineConfig.ALLOWED_EXERCISE_CATEGORIES
    new_categories = st.multiselect("Categories", category_opts)

    new_mandatory = st.checkbox("Always include in generated plans", value=False)
    new_exclude_from_plan = st.checkbox("Exclude from generated plans", value=False)

    if st.button("Create exercise", icon=":material/save:", type="primary", width="stretch"):
        name_clean = new_name.strip()
        existing_names_lower = df_dict['name'].dropna().str.lower().tolist() if 'name' in df_dict.columns else []

        if not name_clean:
            st.error("Name is required.")
        elif name_clean.lower() in existing_names_lower:
            st.error(f"An exercise named '{name_clean}' already exists.")
        else:
            payload = {
                'Name': name_clean,
                'Type': new_type,
                'Sets': new_sets,
                'Reps': new_reps,
                'Time': new_time,
                'Rest': new_rest,
                'Comments': new_comments,
                'Phase': new_phase,
                'Categories': new_categories,
                'Mandatory': new_mandatory,
                'ExcludeFromPlan': new_exclude_from_plan,
            }
            with st.spinner("Saving…"):
                success = add_exercise(payload)
            if success:
                fetch_data.clear()
                st.rerun()


@st.dialog("Edit exercise", icon=":material/edit:")
def edit_exercise_modal(exercise_data):
    st.write(f"**Name:** {exercise_data['name']}")
    exercise_id = int(exercise_data['id'])

    type_opts = PipelineConfig.ALLOWED_EXERCISE_TYPES
    current_type = exercise_data['type'] if pd.notna(exercise_data['type']) and exercise_data['type'] in type_opts else type_opts[0]
    new_type = st.selectbox("Type", type_opts, index=type_opts.index(current_type))

    current_sets = None if pd.isna(exercise_data['sets']) else int(exercise_data['sets'])
    new_sets = st.number_input("Sets", min_value=0, value=current_sets, step=1)

    if new_type == 'Reps':
        current_reps = None if pd.isna(exercise_data['reps']) else int(exercise_data['reps'])
        new_reps = st.number_input("Reps", min_value=0, value=current_reps, step=1)
        new_time = None
    else:
        current_time = "" if pd.isna(exercise_data['time']) else str(exercise_data['time'])
        new_time = st.text_input("Time (e.g. 00:15)", value=current_time)
        new_reps = None

    current_rest = None if pd.isna(exercise_data['rest']) else int(exercise_data['rest'])
    new_rest = st.number_input("Rest", min_value=0, value=current_rest, step=1)

    current_comments = "" if pd.isna(exercise_data['comments']) else str(exercise_data['comments'])
    new_comments = st.text_area("Comments", value=current_comments)

    phase_opts = PipelineConfig.ALLOWED_PHASES
    current_phase = exercise_data['phase'] if pd.notna(exercise_data['phase']) and exercise_data['phase'] in phase_opts else phase_opts[0]
    new_phase = st.selectbox("Phase", phase_opts, index=phase_opts.index(current_phase))

    category_opts = PipelineConfig.ALLOWED_EXERCISE_CATEGORIES
    current_categories = [c for c in (exercise_data.get('categories') or []) if c in category_opts]
    new_categories = st.multiselect("Categories", category_opts, default=current_categories)

    current_mandatory = bool(exercise_data.get('mandatory', False))
    new_mandatory = st.checkbox("Always include in generated plans", value=current_mandatory)
    current_exclude_from_plan = bool(exercise_data.get('exclude_from_plan', False))
    new_exclude_from_plan = st.checkbox("Exclude from generated plans", value=current_exclude_from_plan)

    col_save, col_del = st.columns(2)

    with col_save:
        if st.button("Save changes", icon=":material/save:", type="primary", width="stretch"):
            payload = {
                'Type': new_type,
                'Sets': new_sets,
                'Reps': new_reps,
                'Time': new_time,
                'Rest': new_rest,
                'Comments': new_comments,
                'Phase': new_phase,
                'Categories': new_categories,
                'Mandatory': new_mandatory,
                'ExcludeFromPlan': new_exclude_from_plan,
            }
            with st.spinner("Saving…"):
                success = update_exercise(exercise_id, payload)
            if success:
                fetch_data.clear()
                st.session_state.pop('confirm_delete_exercise_id', None)
                st.rerun()

    with col_del:
        if st.button("Delete exercise", icon=":material/delete:", width="stretch", key="danger_delete_exercise"):
            st.session_state.confirm_delete_exercise_id = exercise_id

    # Two-step delete confirmation
    if st.session_state.get('confirm_delete_exercise_id') == exercise_id:
        st.warning(f"Delete **{exercise_data['name']}** permanently? This also removes it from any sessions it's linked to.")
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.button("Yes, delete", icon=":material/warning:", width="stretch", key="danger_confirm_del_exercise_yes"):
                with st.spinner("Deleting…"):
                    success = delete_exercise(exercise_id)
                if success:
                    fetch_data.clear()
                    st.session_state.pop('confirm_delete_exercise_id', None)
                    st.rerun()
        with col_no:
            if st.button("Cancel", icon=":material/close:", width="stretch"):
                st.session_state.pop('confirm_delete_exercise_id', None)
                st.rerun()


with tab_library:
    st.caption("Click any exercise below to edit or delete it.")

    if st.button("Add new exercise", icon=":material/add:", type="primary"):
        add_exercise_modal()

    _browse_cols = ['name', 'type', 'sets', 'reps', 'time', 'rest', 'comments']
    _browse_cols = [c for c in _browse_cols if c in df_dict.columns]

    if "last_exercise_selection" not in st.session_state:
        st.session_state.last_exercise_selection = {}

    modal_opened_this_run = False

    _phase_icons = {'Before': 'directions_run', 'During': 'terrain', 'After': 'self_improvement'}
    phase_tabs = st.tabs([f":material/{_phase_icons.get(p, 'fitness_center')}: {p}" for p in PipelineConfig.ALLOWED_PHASES])
    for tab, phase in zip(phase_tabs, PipelineConfig.ALLOWED_PHASES):
        with tab:
            phase_df = df_dict[df_dict['phase'] == phase].reset_index(drop=True)
            if phase_df.empty:
                st.info(f"No exercises tagged '{phase}' yet.")
                continue

            event = st.dataframe(
                phase_df[_browse_cols],
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key=f"exercise_browse_{phase}",
            )

            selected_rows = event.selection.rows
            is_new_selection = bool(selected_rows) and st.session_state.last_exercise_selection.get(phase) != selected_rows

            if is_new_selection and not modal_opened_this_run:
                st.session_state.last_exercise_selection[phase] = selected_rows
                modal_opened_this_run = True
                edit_exercise_modal(phase_df.iloc[selected_rows[0]])


with tab_goals:
    if active_goal is None:
        st.caption("Set a grade goal and get a generated training plan to reach it.")

        target_type_label = st.radio("Grade system", ["Gym", "Moonboard"], horizontal=True)
        target_type = 'gym' if target_type_label == 'Gym' else 'moonboard'
        grade_opts = list(PipelineConfig.GYM_MAPPING.keys() if target_type == 'gym' else PipelineConfig.MOONBOARD_MAPPING.keys())
        target_grade = st.selectbox("Target grade", grade_opts, index=len(grade_opts) - 1)
        selected_days = st.multiselect("Training days", PlanConfig.WEEKDAY_NAMES)
        training_weekdays = {PlanConfig.WEEKDAY_NAMES.index(name) for name in selected_days}

        if st.button("Preview plan", icon=":material/visibility:", width="stretch", disabled=not training_weekdays):
            st.session_state.plan_preview = preview_plan(target_type, target_grade, training_weekdays, df_past, df_dict)
            st.session_state.plan_preview_params = (target_type, target_grade, training_weekdays)
        if not training_weekdays:
            st.caption("Pick at least one training day to preview a plan.")

        preview = st.session_state.get('plan_preview')
        if preview is not None:
            if preview.get('already_at_target'):
                st.success(f"You've already reached {target_grade} - no plan needed.")
            else:
                weeks_per_step = preview.get('weeks_per_step')
                if weeks_per_step is not None:
                    st.caption(f"Pace: {weeks_per_step:.1f} weeks/grade step, from your own history")
                else:
                    st.caption("Pace: using the default model (gets longer for higher grades)")

                neglect_scores = preview.get('neglect_scores') or {}
                most_neglected = max(neglect_scores, key=neglect_scores.get, default=None)
                if most_neglected is not None and neglect_scores[most_neglected] > 0.1:
                    st.caption(f"{most_neglected} is trained least relative to your other categories — weighted up in this plan")

                st.markdown(f"**{preview['total_weeks']}-week plan**")
                for phase in preview['phase_breakdown']:
                    weeks = phase['end_week'] - phase['start_week'] + 1
                    mix = ", ".join(f"{cat} {int(w * 100)}%" for cat, w in phase['weights'].items())
                    st.write(f"**{phase['name']}** (weeks {phase['start_week']}-{phase['end_week']}, {weeks}w): {mix}")

                if st.button("Confirm & generate plan", icon=":material/check_circle:", type="primary", width="stretch"):
                    saved_type, saved_grade, saved_weekdays = st.session_state.plan_preview_params
                    with st.spinner("Generating your plan…"):
                        success = create_goal_and_plan(saved_type, saved_grade, saved_weekdays, df_past, df_future, df_dict)
                    if success:
                        fetch_data.clear()
                        fetch_goal.clear()
                        st.session_state.pop('plan_preview', None)
                        st.rerun()
    else:
        created_at = pd.to_datetime(active_goal['created_at']).normalize()
        today = pd.to_datetime('today').normalize()
        elapsed_weeks = (today - created_at).days / 7
        current_week = min(active_goal['total_weeks'], int(elapsed_weeks) + 1)
        current_phase = next(
            (p['name'] for p in active_goal['phase_breakdown'] if p['start_week'] <= current_week <= p['end_week']),
            active_goal['phase_breakdown'][-1]['name'],
        )
        st.markdown(f"**Goal:** {active_goal['target_grade']} ({active_goal['target_type']})")
        st.write(f"Week {current_week} of {active_goal['total_weeks']} — {current_phase} phase")
        st.html(theme.phase_timeline_html(active_goal['phase_breakdown'], active_goal['total_weeks'], elapsed_weeks))

        col_regen, col_abandon = st.columns(2)
        with col_regen:
            if st.button("Regenerate plan", icon=":material/refresh:", width="stretch"):
                st.session_state.confirm_regenerate_goal = True
        with col_abandon:
            if st.button("Abandon goal", icon=":material/delete:", width="stretch", key="danger_abandon_goal"):
                st.session_state.confirm_abandon_goal = True

        if st.session_state.get('confirm_regenerate_goal'):
            st.warning("Re-roll the remaining weeks of this plan? Future, not-yet-logged sessions from this goal will be replaced.")
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("Yes, regenerate", icon=":material/warning:", width="stretch", key="danger_confirm_regenerate_yes"):
                    with st.spinner("Regenerating…"):
                        success = regenerate_plan(active_goal, df_past, df_future, df_dict)
                    st.session_state.pop('confirm_regenerate_goal', None)
                    if success:
                        fetch_data.clear()
                        st.rerun()
            with col_no:
                if st.button("Cancel", icon=":material/close:", width="stretch", key="cancel_regenerate_goal"):
                    st.session_state.pop('confirm_regenerate_goal', None)
                    st.rerun()

        if st.session_state.get('confirm_abandon_goal'):
            st.warning("Abandon this goal? Future, not-yet-logged sessions from it will be deleted. Already-logged sessions stay as real history.")
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("Yes, abandon", icon=":material/warning:", width="stretch", key="danger_confirm_abandon_yes"):
                    with st.spinner("Abandoning…"):
                        success = abandon_goal(active_goal['id'], df_future)
                    st.session_state.pop('confirm_abandon_goal', None)
                    if success:
                        fetch_data.clear()
                        fetch_goal.clear()
                        st.rerun()
            with col_no:
                if st.button("Cancel", icon=":material/close:", width="stretch", key="cancel_abandon_goal"):
                    st.session_state.pop('confirm_abandon_goal', None)
                    st.rerun()