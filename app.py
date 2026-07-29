"""
Climbing Training Tracker - Streamlit dashboard.

Reads cleaned session data from Google Sheets (via data_pipeline.py) and
renders:
- An interactive calendar for viewing/editing/adding training sessions.
- An analytics section (effort trend, grade progression, category mix)
  over a user-selected date range.
"""

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
from streamlit_calendar import calendar

from data_pipeline import load_clean_data, update_session, add_session, delete_session, PipelineConfig

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Climbing Training Tracker", layout="wide")

# --- CUSTOM CSS FOR CALENDAR STYLING ---
# Centers the day number over each cell and makes it legible against the
# background color used for that day's training category (see category_colors).
st.markdown("""
<style>
.fc-daygrid-day-frame {
    position: relative !important;
}
.fc-daygrid-day-top {
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
}
.fc-daygrid-day-number {
    font-size: 1.5rem !important;
    font-weight: 800 !important;
    color: white !important;
    text-shadow: 2px 2px 4px rgba(0,0,0,0.8), -1px -1px 4px rgba(0,0,0,0.8) !important;
    text-decoration: none !important;
}
.fc-daygrid-day-events {
    pointer-events: none !important;
}
.fc-bg-event {
    opacity: 0.85 !important;
}
</style>
""", unsafe_allow_html=True)

# --- DATA LOADING ---
@st.cache_data
def fetch_data():
    """Cached wrapper around load_clean_data() so every rerun doesn't hit
    the Google Sheets API. Cleared explicitly after any write (see the
    modal's save/delete/add actions below)."""
    return load_clean_data()

df_past, df_future, df_dict = fetch_data()

# Single combined view of every dated session, used to drive the calendar
df_all_calendar = pd.concat([df_past, df_future]).dropna(subset=['date']).copy()
df_all_calendar['date_str'] = df_all_calendar['date'].dt.strftime('%Y-%m-%d')

available_exercises = df_dict['name'].dropna().unique().tolist() if 'name' in df_dict.columns else []


# --- EDIT/CREATE SESSION MODAL (POP-UP) ---
@st.dialog("✏️ Session Details")
def edit_session_modal(session_data, is_new=False):
    """Pop-up form for viewing/editing an existing session, or logging a
    new one when is_new=True. session_data is a single row (Series) from
    df_all_calendar for edits, or a synthetic blank row for new entries.
    """
    st.write(f"**Date:** {session_data['date'].strftime('%d/%m/%Y')}")

    # 1. Initialize per-session widget state.
    # We re-initialize whenever the modal is opened for a *different*
    # session (different row or date) so stale exercise text from a
    # previously edited session doesn't leak into this one.
    if ("current_edit_row" not in st.session_state or
        st.session_state.current_edit_row != session_data['gsheet_row'] or
        st.session_state.get("current_edit_date") != session_data['date']):

        st.session_state.current_edit_row = session_data['gsheet_row']
        st.session_state.current_edit_date = session_data['date']
        st.session_state.edit_exercises = "" if pd.isna(session_data['exercises']) else str(session_data['exercises'])

    # 2. Callbacks for appending/removing exercises from the comma-separated list
    def append_exercise():
        ex = st.session_state.ex_selector
        if ex:
            if st.session_state.edit_exercises:
                separator = " " if st.session_state.edit_exercises.strip().endswith(',') else ", "
                st.session_state.edit_exercises += f"{separator}{ex}"
            else:
                st.session_state.edit_exercises = ex

    def remove_exercise(ex_to_remove):
        # Convert the current comma-separated text to a list, drop the
        # item, and rejoin it back into the stored string.
        current_list = [e.strip() for e in st.session_state.edit_exercises.split(',')] if st.session_state.edit_exercises else []
        if ex_to_remove in current_list:
            current_list.remove(ex_to_remove)
            st.session_state.edit_exercises = ", ".join(current_list)

    # 3. Form inputs
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

    # 4. Interactive exercises grid (click a logged exercise to remove it)
    st.markdown("---")
    st.markdown("**Exercises Logged (Click to remove):**")

    current_text = st.session_state.edit_exercises
    current_list = [ex.strip() for ex in current_text.split(',')] if current_text else []

    if current_list and current_list[0] != "":
        # 3-column wrapping grid; modulo creates the wrap-around effect
        grid_cols = st.columns(3)
        for i, ex in enumerate(current_list):
            if ex:
                with grid_cols[i % 3]:
                    # args=(ex,) safely passes this specific exercise to the callback
                    st.button(f"{ex} ✖", key=f"del_{i}_{ex}", on_click=remove_exercise, args=(ex,), use_container_width=True)
    else:
        st.info("No exercises logged for this session yet")

    # Don't offer exercises that are already logged for this session
    filtered_exercises = [ex for ex in available_exercises if ex not in current_list]

    st.markdown("**(Optional) Append an exercise:**")
    col_sel, col_btn = st.columns([3, 1])
    with col_sel:
        st.selectbox("Select Exercise", [""] + filtered_exercises, key="ex_selector", label_visibility="collapsed")
    with col_btn:
        st.button("➕ Add", on_click=append_exercise, use_container_width=True)

    st.markdown("---")

    # 5. Save & delete actions
    if is_new:
        if st.button("💾 Log New Session", use_container_width=True):
            new_session_data = {
                'Date': session_data['date'].strftime('%d/%m/%Y'),
                'Category': new_cat,
                'Effort Scale': new_effort,
                'Max Gym Grade Color': new_gym,
                'Max Moonboard Grade': new_mb,
                'Exercises': st.session_state.edit_exercises
            }
            if add_session(new_session_data):
                fetch_data.clear()
                st.rerun()
    else:
        col_save, col_del = st.columns(2)
        with col_save:
            if st.button("💾 Save Changes", use_container_width=True):
                updated_data = {
                    'Effort Scale': new_effort,
                    'Max Gym Grade Color': new_gym,
                    'Max Moonboard Grade': new_mb,
                    'Exercises': st.session_state.edit_exercises
                }
                if update_session(int(session_data['gsheet_row']), updated_data):
                    fetch_data.clear()
                    st.rerun()
        with col_del:
            if st.button("🗑️ Delete Session", use_container_width=True):
                if delete_session(int(session_data['gsheet_row'])):
                    fetch_data.clear()
                    st.rerun()


def _make_blank_session(clicked_date_str: str) -> pd.Series:
    """Build a synthetic empty session row for a day with no logged data,
    so the modal can be reused for both editing and creating sessions."""
    return pd.Series({
        'gsheet_row': None,
        'date': pd.to_datetime(clicked_date_str),
        'category': '',
        'effort': pd.NA,
        'gym_grade': np.nan,
        'moonboard_grade': np.nan,
        'exercises': ''
    })


# --- INTERACTIVE CALENDAR ---
st.header("📅 Training Calendar")
st.markdown("*Click any colored session to edit it, or click a blank day to log a missed session.*")

category_colors = {
    "Strength": "#FF5733",
    "Stamina": "#33C3FF",
    "Technique": "#28B463",
    "Free": "#8E44AD",
    "Rest": "#95A5A6"
}

# Sessions are rendered as full-day background color blocks rather than
# titled events, so the calendar reads like a training-day heatmap
calendar_events = [
    {
        "title": str(row['category']) if pd.notna(row['category']) else "Unknown",
        "start": row['date_str'],
        "color": category_colors.get(str(row['category']), "#34495E"),
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

# --- ANALYTICS DASHBOARD ---
st.markdown("---")

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
            fig, ax = plt.subplots(figsize=(5, 3.5))
            sns.lineplot(data=df_effort, x='date', y='effort', marker='o', color='#FF5733', ax=ax)
            ax.set_ylim(0, 10.5)
            ax.set_ylabel("Effort (1-10)")
            ax.set_xlabel("")
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
            plt.xticks(rotation=45)
            st.pyplot(fig, use_container_width=True)
        else:
            st.info("No effort data logged.")

    with col2:
        st.subheader("📈 Grade Progression")
        # -1 encodes "no grade logged that day" (see clean_data), so those rows are excluded here
        df_gym = df_analytics[df_analytics['gym_numeric'] != -1].sort_values(by='date')
        df_moonboard = df_analytics[df_analytics['moonboard_numeric'] != -1].sort_values(by='date')

        if not df_gym.empty or not df_moonboard.empty:
            fig_grades, ax1 = plt.subplots(figsize=(5, 3.5))
            gym_rev_map = {v: k for k, v in PipelineConfig.GYM_MAPPING.items()}
            mb_rev_map = {v: k for k, v in PipelineConfig.MOONBOARD_MAPPING.items()}

            # Gym grade and Moonboard grade use different scales, so they
            # share the x-axis (date) but get independent y-axes
            color1 = '#2E86C1'
            ax1.set_ylabel('Gym Color', color=color1)
            if not df_gym.empty:
                sns.lineplot(data=df_gym, x='date', y='gym_numeric', marker='s', color=color1, ax=ax1, label='Gym Grade')

            ax1.set_yticks(list(gym_rev_map.keys()))
            ax1.set_yticklabels(list(gym_rev_map.values()))
            ax1.tick_params(axis='y', labelcolor=color1)

            ax2 = ax1.twinx()
            color2 = '#8E44AD'
            ax2.set_ylabel('Moonboard (V)', color=color2)
            if not df_moonboard.empty:
                sns.lineplot(data=df_moonboard, x='date', y='moonboard_numeric', marker='^', color=color2, ax=ax2, label='Moonboard')

            ax2.set_yticks(list(mb_rev_map.keys()))
            ax2.set_yticklabels(list(mb_rev_map.values()))
            ax2.tick_params(axis='y', labelcolor=color2)

            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m'))
            ax1.set_xlabel("")
            plt.xticks(rotation=45)

            # Merge both axes' legends into a single legend box
            lines_1, labels_1 = ax1.get_legend_handles_labels()
            lines_2, labels_2 = ax2.get_legend_handles_labels()
            ax2.legend(lines_1 + lines_2, labels_1 + labels_2, loc='upper left', fontsize='small')

            if ax1.get_legend() is not None:
                ax1.get_legend().remove()

            st.pyplot(fig_grades, use_container_width=True)
        else:
            st.info("No grade data logged.")

    with col3:
        st.subheader("📊 Distribution")
        df_dist = df_analytics[df_analytics['category'] != 'Rest']

        if not df_dist.empty:
            fig_dist, ax_dist = plt.subplots(figsize=(5, 3.5))
            category_counts = df_dist['category'].value_counts()

            ax_dist.pie(
                category_counts,
                labels=category_counts.index,
                autopct='%1.1f%%',
                startangle=140,
                colors=sns.color_palette('viridis', n_colors=len(category_counts)),
                wedgeprops={'edgecolor': 'white', 'linewidth': 1.5}
            )
            ax_dist.axis('equal')
            st.pyplot(fig_dist, use_container_width=True)
        else:
            st.info("No training sessions logged.")
else:
    st.warning("Please select an end date to view analytics.")