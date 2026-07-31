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
import theme

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Climbing Training Tracker", page_icon="🧗", layout="wide")

st.markdown(theme.inject_global_css(), unsafe_allow_html=True)

# --- CUSTOM CSS FOR CALENDAR STYLING ---
# Centers the day number over each cell and makes it legible against the
# background color used for that day's training category (see theme.CATEGORY_COLORS).
st.markdown(f"""
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
</style>
""", unsafe_allow_html=True)

# --- DATA LOADING ---
@st.cache_data
def fetch_data():
    """Cached wrapper around load_clean_data() so every rerun doesn't hit
    Supabase. Cleared explicitly after any write (see the
    modal's save/delete/add actions below)."""
    return load_clean_data()

df_past, df_future, df_dict = fetch_data()

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
st.title("🧗 Climbing Training")

kpis = compute_kpis(df_past)
kpi_cols = st.columns(4)
with kpi_cols[0]:
    st.metric("Current Streak", f"{kpis['streak']} d")
with kpi_cols[1]:
    st.metric("This Week", kpis['sessions_this_week'])
with kpi_cols[2]:
    acwr_value = "–" if kpis['acwr_current'] is None else f"{kpis['acwr_current']:.2f}"
    acwr_delta = None if kpis['acwr_delta'] is None else f"{kpis['acwr_delta']:+.2f}"
    st.metric("ACWR", acwr_value, delta=acwr_delta, delta_color="inverse")
with kpi_cols[3]:
    since_last = "–" if kpis['days_since_last'] is None else f"{kpis['days_since_last']} d"
    st.metric("Since Last Session", since_last)


# --- EDIT/CREATE SESSION MODAL (POP-UP) ---
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
            st.write(f"**Category:** {session_data['category']}")
            new_cat = session_data['category']

        current_effort = None if pd.isna(session_data['effort']) else int(session_data['effort'])
        new_effort = st.number_input("Effort Scale (1-10)", min_value=1, max_value=10, value=current_effort, step=1)

        gym_opts = [""] + list(PipelineConfig.GYM_MAPPING.keys())
        current_gym = session_data['gym_grade'] if pd.notna(session_data['gym_grade']) and session_data['gym_grade'] in gym_opts else ""
        new_gym = st.selectbox("Max Gym Grade", gym_opts, index=gym_opts.index(current_gym))

        mb_opts = [""] + list(PipelineConfig.MOONBOARD_MAPPING.keys())
        current_mb = session_data['moonboard_grade'] if pd.notna(session_data['moonboard_grade']) and session_data['moonboard_grade'] in mb_opts else ""
        new_mb = st.selectbox("Max Moonboard Grade", mb_opts, index=mb_opts.index(current_mb))

    with st.container(border=True):
        # 2. Exercises
        st.markdown("**Exercises**")

        session_key = session_data['id'] if pd.notna(session_data['id']) else session_data['date'].strftime('%Y%m%d')

        # Determine default selections
        if is_new:
            # Smart State Injection: Fetch "Before" and "After" from the most recent past session
            default_before = []
            default_during = [] # Always start blank for climbing
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

        # Render Mobile Tabs
        tab1, tab2, tab3 = st.tabs(["🏃 Warm-up", "🧗 Climbing", "🏋️ Cool-down"])

        with tab1:
            selected_before = st.multiselect(
                "Before", options=exercises_before, default=default_before,
                key=f"ex_before_{session_key}", label_visibility="collapsed"
            )
        with tab2:
            selected_during = st.multiselect(
                "During", options=exercises_during, default=default_during,
                key=f"ex_during_{session_key}", label_visibility="collapsed"
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
        if st.button("💾 Log New Session", use_container_width=True):
            new_session_data = {
                'Date': session_data['date'].strftime('%d/%m/%Y'),
                'Category': new_cat,
                'Effort Scale': new_effort,
                'Max Gym Grade Color': new_gym,
                'Max Moonboard Grade': new_mb,
                'Exercises': ", ".join(selected_exercises)
            }
            if add_session(new_session_data):
                _finish()
    else:
        session_id = int(session_data['id'])
        col_save, col_del = st.columns(2)
        with col_save:
            if st.button("💾 Save Changes", use_container_width=True):
                updated_data = {
                    'Effort Scale': new_effort,
                    'Max Gym Grade Color': new_gym,
                    'Max Moonboard Grade': new_mb,
                    'Exercises': ", ".join(selected_exercises)
                }
                if update_session(session_id, updated_data):
                    _finish()
        with col_del:
            if st.button("🗑️ Delete Session", use_container_width=True):
                st.session_state.confirm_delete_session_id = session_id

        # Two-step delete confirmation, mirroring the exercise delete pattern
        if st.session_state.get('confirm_delete_session_id') == session_id:
            st.warning("Delete this session permanently? This also removes its logged exercises.")
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("⚠️ Yes, delete", use_container_width=True, key=f"confirm_del_session_yes_{session_id}"):
                    if delete_session(session_id):
                        _finish()
            with col_no:
                if st.button("Cancel", use_container_width=True, key=f"confirm_del_session_no_{session_id}"):
                    st.session_state.pop('confirm_delete_session_id', None)
                    st.rerun()


@st.dialog("✏️ Session Details")
def edit_session_modal(session_data, is_new=False):
    """Pop-up form for viewing/editing an existing session, or logging a
    new one when is_new=True
    """
    _render_session_edit_form(session_data, is_new=is_new)


def _advance_due_carousel():
    """Moves the due-sessions carousel to the next entry"""
    st.session_state.due_carousel_index += 1
    st.rerun()


@st.dialog("⏰ Catch Up on Missed Sessions")
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
        if st.button("◀", disabled=(idx == 0), use_container_width=True, key="due_carousel_prev"):
            st.session_state.due_carousel_index -= 1
            st.rerun()
    with col_mid:
        st.markdown(f"<p style='text-align:center'>Overdue session {idx + 1} of {len(queue)}</p>", unsafe_allow_html=True)
    with col_next:
        if st.button("▶", disabled=(idx == len(queue) - 1), use_container_width=True, key="due_carousel_next"):
            st.session_state.due_carousel_index += 1
            st.rerun()

    st.warning("This session is missing its effort - fill it in, delete it, remind yourself later, or dismiss the whole list for now.")

    _render_session_edit_form(session_data, is_new=False, on_saved=_advance_due_carousel)

    col_skip, col_dismiss = st.columns(2)
    with col_skip:
        if st.button("⏭️ Remind Me Later", use_container_width=True, key="due_carousel_skip"):
            _advance_due_carousel()
    with col_dismiss:
        if st.button("✖️ Dismiss All", use_container_width=True, key="due_carousel_dismiss_all"):
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
tab_calendar, tab_analytics, tab_library = st.tabs(["📅 Calendar", "📊 Analytics", "🏋️ Exercise Library"])

with tab_calendar:
    st.markdown("*Click any colored session to edit it, or click a blank day to log a missed session.*")
    st.markdown(theme.color_key_html(theme.CATEGORY_COLORS, title="Category Key"), unsafe_allow_html=True)

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

    cal = calendar(events=calendar_events, options=calendar_options, callbacks=['dateClick'])

    # Handle a day-click by opening the modal for that date. The "last_click_event"
    # guard prevents the modal from immediately reopening on every rerun that
    # Streamlit triggers after the dialog is dismissed.
    if cal.get("callback") == "dateClick":
        current_click_event = str(cal)

        if st.session_state.get("last_click_event") != current_click_event:
            st.session_state.last_click_event = current_click_event

            raw_clicked_date = str(cal["dateClick"]["date"])
            clean_clicked_date = raw_clicked_date.split("T")[0]

            existing_session = df_all_calendar[df_all_calendar['date_str'] == clean_clicked_date]

            if not existing_session.empty:
                edit_session_modal(existing_session.iloc[0], is_new=False)
            else:
                edit_session_modal(_make_blank_session(clean_clicked_date), is_new=True)


with tab_analytics:
    today_date = pd.to_datetime('today').date()
    last_month_date = today_date - pd.Timedelta(days=30)

    date_range = st.date_input(
        "🗓️ Select Analytics Date Range",
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
            st.subheader("🔥 Training Intensity")
            df_effort = df_analytics.dropna(subset=['effort']).sort_values(by='date')

            if not df_effort.empty:
                fig = px.line(df_effort, x='date', y='effort', markers=True, template=theme.PLOTLY_TEMPLATE)
                fig.update_traces(line_color=theme.ACCENT, marker=dict(color=theme.ACCENT, size=8))
                fig.update_yaxes(title="Effort (1-10)", range=[0, 10.5])
                fig.update_xaxes(title="", tickformat="%d/%m")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No effort data logged.")

        with col2:
            st.subheader("📈 Grade Progression")
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
                st.plotly_chart(fig_grades, use_container_width=True)
            else:
                st.info("No grade data logged.")

        with col3:
            st.subheader("📊 Distribution")
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
                st.plotly_chart(fig_dist, use_container_width=True)
            else:
                st.info("No training sessions logged.")

        st.markdown("---")
        st.subheader("🎯 Advanced Analytics")

        col4, col5 = st.columns(2)

        with col4:
            st.markdown("**📉 Acute:Chronic Workload Ratio**")
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
                st.plotly_chart(fig_acwr, use_container_width=True)
                st.caption("Recent (7-day) vs. baseline (28-day) training load. Needs a few weeks of consistent logging to be meaningful.")
            else:
                st.info("Not enough training history yet to compute ACWR.")

        with col5:
            st.markdown("**🎯 Effort vs. Grade Yield**")
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
                st.plotly_chart(fig_yield, use_container_width=True)
            else:
                st.info("No grade data logged in this range.")

        st.markdown("**🏆 Peak Performance Highlights**")
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
                        st.write(f"🧗 Gym: {gym_rev_map.get(int(session['gym_numeric']), '-')}")
                    if session['moonboard_numeric'] != -1:
                        st.write(f"🪨 Moonboard: {mb_rev_map.get(int(session['moonboard_numeric']), '-')}")
                    if pd.notna(session['effort']):
                        st.write(f"🔥 Effort: {int(session['effort'])}/10")
        else:
            st.info("No sessions to highlight in this range yet.")
    else:
        st.warning("Please select an end date to view analytics.")


@st.dialog("➕ New Exercise")
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

    if st.button("💾 Create Exercise", use_container_width=True):
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
            }
            if add_exercise(payload):
                fetch_data.clear()
                st.rerun()


@st.dialog("✏️ Edit Exercise")
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

    st.markdown("---")
    col_save, col_del = st.columns(2)

    with col_save:
        if st.button("💾 Save Changes", use_container_width=True):
            payload = {
                'Type': new_type,
                'Sets': new_sets,
                'Reps': new_reps,
                'Time': new_time,
                'Rest': new_rest,
                'Comments': new_comments,
                'Phase': new_phase,
            }
            if update_exercise(exercise_id, payload):
                fetch_data.clear()
                st.session_state.pop('confirm_delete_exercise_id', None)
                st.rerun()

    with col_del:
        if st.button("🗑️ Delete Exercise", use_container_width=True):
            st.session_state.confirm_delete_exercise_id = exercise_id

    # Two-step delete confirmation
    if st.session_state.get('confirm_delete_exercise_id') == exercise_id:
        st.warning(f"Delete **{exercise_data['name']}** permanently? This also removes it from any sessions it's linked to.")
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.button("⚠️ Yes, delete", use_container_width=True):
                if delete_exercise(exercise_id):
                    fetch_data.clear()
                    st.session_state.pop('confirm_delete_exercise_id', None)
                    st.rerun()
        with col_no:
            if st.button("Cancel", use_container_width=True):
                st.session_state.pop('confirm_delete_exercise_id', None)
                st.rerun()


with tab_library:
    st.markdown("*Click any exercise below to edit or delete it.*")

    if st.button("➕ Add New Exercise"):
        add_exercise_modal()

    _browse_cols = ['name', 'type', 'sets', 'reps', 'time', 'rest', 'comments']
    _browse_cols = [c for c in _browse_cols if c in df_dict.columns]

    phase_tabs = st.tabs(PipelineConfig.ALLOWED_PHASES)
    for tab, phase in zip(phase_tabs, PipelineConfig.ALLOWED_PHASES):
        with tab:
            phase_df = df_dict[df_dict['phase'] == phase].reset_index(drop=True)
            if phase_df.empty:
                st.info(f"No exercises tagged '{phase}' yet.")
                continue

            event = st.dataframe(
                phase_df[_browse_cols],
                use_container_width=True,
                hide_index=True,
                on_select="rerun",
                selection_mode="single-row",
                key=f"exercise_browse_{phase}",
            )

            selected_rows = event.selection.rows
            selection_signature = f"{phase}:{selected_rows}"

            if selected_rows and st.session_state.get("last_exercise_selection") != selection_signature:
                st.session_state.last_exercise_selection = selection_signature
                edit_exercise_modal(phase_df.iloc[selected_rows[0]])