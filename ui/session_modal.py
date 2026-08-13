"""
The session-edit form shared by calendar clicks and the due-sessions
catch-up carousel, plus the carousel itself.
"""

import numpy as np
import pandas as pd
import streamlit as st

from data_pipeline import PipelineConfig, update_session, add_session, delete_session
from training_plan import select_exercises_for_day


def _category_exercise_pool(category, df_dict):
    """Every During exercise select_exercises_for_day would include for
    this category (mandatory + category-tagged, excluding anything
    flagged exclude_from_plan) - or none at all for Free/Rest, which
    can't be pre-planned."""
    if category in ('Free', 'Rest'):
        return []
    return select_exercises_for_day(category, df_dict, {})['during']


def _render_session_edit_form(
    session_data, df_past, df_dict, exercises_before, exercises_during, exercises_after,
    refresh_data, is_new=False, on_saved=None,
):
    """Renders the actual session form (fields + save/delete buttons).

    Shared by edit_session_modal() (opened from a calendar click) and
    due_sessions_carousel() (auto-opened on load for overdue sessions)

    on_saved: called instead of the default refresh_data()+st.rerun()
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
        refresh_data()
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


def _reset_delete_confirmation():
    """Clears any pending session-delete confirmation, so a modal dismissed
    via the X/backdrop/ESC (instead of Cancel) doesn't reopen with the
    warning still showing."""
    st.session_state.pop('confirm_delete_session_id', None)


@st.dialog("Session details", icon=":material/edit:", on_dismiss=_reset_delete_confirmation)
def edit_session_modal(
    session_data, df_past, df_dict, exercises_before, exercises_during, exercises_after,
    refresh_data, is_new=False,
):
    """Pop-up form for viewing/editing an existing session, or logging a
    new one when is_new=True
    """
    _render_session_edit_form(
        session_data, df_past, df_dict, exercises_before, exercises_during, exercises_after,
        refresh_data, is_new=is_new,
    )


def _advance_due_carousel():
    """Moves the due-sessions carousel to the next entry"""
    st.session_state.due_carousel_index += 1
    st.rerun()


@st.dialog("Catch up on missed sessions", icon=":material/schedule:", on_dismiss=_reset_delete_confirmation)
def due_sessions_carousel(df_all_calendar, df_past, df_dict, exercises_before, exercises_during, exercises_after, refresh_data):
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

    _render_session_edit_form(
        session_data, df_past, df_dict, exercises_before, exercises_during, exercises_after,
        refresh_data, is_new=False, on_saved=_advance_due_carousel,
    )

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
