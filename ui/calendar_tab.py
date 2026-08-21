"""
The Calendar tab: a month/week view of every logged or scheduled session,
color-coded by category, that opens the session-edit modal on click.
"""

import pandas as pd
import streamlit as st
from streamlit_calendar import calendar

import theme
from . import session_modal


def render(df_all_calendar, df_past, df_dict, exercises_before, exercises_during, exercises_after, refresh_data):
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
        "initialView": st.session_state.get("calendar_initial_view", "dayGridMonth"),
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
        st.session_state.calendar_initial_view = cal["dateClick"]["view"]["type"]

        if not existing_session.empty:
            session_modal.edit_session_modal(
                existing_session.iloc[0], df_past, df_dict, exercises_before, exercises_during, exercises_after,
                refresh_data, is_new=False,
            )
        else:
            session_modal.edit_session_modal(
                session_modal._make_blank_session(clean_clicked_date), df_past, df_dict,
                exercises_before, exercises_during, exercises_after, refresh_data, is_new=True,
            )
