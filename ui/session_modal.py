"""
The session-edit form shared by calendar clicks and the due-sessions
catch-up carousel, plus the carousel itself.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import theme
from data_pipeline import PipelineConfig, update_session, add_session, delete_session
from training_plan import select_exercises_for_day
from whoop import suggest_effort
from . import components


def _category_exercise_pool(category, df_dict):
    """Every During exercise select_exercises_for_day would include for
    this category (mandatory + category-tagged, excluding anything
    flagged exclude_from_plan) - or none at all for Free/Rest, which
    can't be pre-planned."""
    if category in ('Free', 'Rest'):
        return []
    return select_exercises_for_day(category, df_dict, {})['during']


def _lookup_workout_hint(df_whoop_workouts, session_date):
    """That date's combined WHOOP climbing-workout stats, or None if WHOOP
    is disabled or nothing has synced for that day yet."""
    if df_whoop_workouts.empty:
        return None
    match = df_whoop_workouts[df_whoop_workouts['date'] == session_date]
    if match.empty:
        return None
    row = match.iloc[0]
    if pd.isna(row['duration_min']):
        return None
    return {
        'duration_min': float(row['duration_min']),
        'calories': None if pd.isna(row['calories']) else int(row['calories']),
        'avg_hr': None if pd.isna(row['avg_hr']) else int(row['avg_hr']),
        'max_hr': None if pd.isna(row['max_hr']) else int(row['max_hr']),
        'zones': [float(row[f'zone_{n}_min']) if pd.notna(row[f'zone_{n}_min']) else 0.0 for n in range(6)],
    }


def _render_session_edit_form(
    session_data, df_past, df_dict, exercises_before, exercises_during, exercises_after,
    refresh_data, is_new=False, on_saved=None, whoop_hint=None, workout_hint=None,
):
    """Renders the actual session form (fields + save/delete buttons).

    Shared by edit_session_modal() (opened from a calendar click) and
    due_sessions_carousel() (opened via the header bell for overdue sessions)

    on_saved: called instead of the default refresh_data()+st.rerun()
    after a successful save/delete
    """
    st.write(f"**Date:** {session_data['date'].strftime('%d/%m/%Y')}")

    with st.container(border=True):
        st.markdown("**Details**")

        if is_new:
            cat_opts = PipelineConfig.ALLOWED_CATEGORIES
            new_cat = st.selectbox("Category", cat_opts)
        else:
            cat_opts = PipelineConfig.ALLOWED_CATEGORIES
            current_cat = session_data['category'] if session_data['category'] in cat_opts else cat_opts[0]
            new_cat = st.selectbox("Category", cat_opts, index=cat_opts.index(current_cat))

        current_effort = None if pd.isna(session_data['effort']) else int(session_data['effort'])
        effort_value = current_effort
        if current_effort is None and whoop_hint is not None:
            effort_value = whoop_hint['suggested_effort']
        new_effort = st.number_input("Effort (1-10)", min_value=1, max_value=10, value=effort_value, step=1)
        if current_effort is None and whoop_hint is not None:
            recovery = whoop_hint['recovery_score']
            recovery_text = f"recovery {recovery}%" if recovery is not None else "recovery unavailable"
            st.caption(f"Suggested from WHOOP - strain {whoop_hint['strain']:.1f}, {recovery_text}")

        gym_opts = [""] + list(PipelineConfig.GYM_MAPPING.keys())
        current_gym = session_data['gym_grade'] if pd.notna(session_data['gym_grade']) and session_data['gym_grade'] in gym_opts else ""
        new_gym = st.selectbox("Max gym grade", gym_opts, index=gym_opts.index(current_gym))

        mb_opts = [""] + list(PipelineConfig.MOONBOARD_MAPPING.keys())
        current_mb = session_data['moonboard_grade'] if pd.notna(session_data['moonboard_grade']) and session_data['moonboard_grade'] in mb_opts else ""
        new_mb = st.selectbox("Max Moonboard grade", mb_opts, index=mb_opts.index(current_mb))

    if workout_hint is not None:
        with st.container(border=True):
            st.markdown("**WHOOP climbing workout**")
            col_dur, col_cal = st.columns(2)
            with col_dur:
                st.metric("Duration", f"{workout_hint['duration_min']:.0f} min")
            with col_cal:
                st.metric("Calories", "–" if workout_hint['calories'] is None else str(workout_hint['calories']))
            col_avg, col_max = st.columns(2)
            with col_avg:
                st.metric("Avg HR", "–" if workout_hint['avg_hr'] is None else f"{workout_hint['avg_hr']} bpm")
            with col_max:
                st.metric("Max HR", "–" if workout_hint['max_hr'] is None else f"{workout_hint['max_hr']} bpm")

            zone_labels = ["Zone 0", "Zone 1", "Zone 2", "Zone 3", "Zone 4", "Zone 5"]
            zone_colors = [
                theme.STONE, theme.GRADE_COLORS["Blue"], theme.GRADE_COLORS["Green"],
                theme.GRADE_COLORS["Yellow"], theme.GRADE_COLORS["Red"], theme.GRADE_COLORS["Purple"],
            ]
            fig_zones = go.Figure()
            for label, minutes, color in zip(zone_labels, workout_hint['zones'], zone_colors):
                fig_zones.add_trace(go.Bar(
                    y=["Zones"], x=[minutes], name=label, orientation='h',
                    marker=dict(color=color), hovertemplate=f"{label}: %{{x:.0f}} min<extra></extra>",
                ))
            fig_zones.update_layout(
                template=theme.PLOTLY_TEMPLATE, barmode='stack', height=60,
                showlegend=False,
                xaxis=dict(title="Minutes"), yaxis=dict(visible=False),
                margin=dict(l=10, r=10, t=10, b=30),
            )
            components.render_chart(fig_zones)
            st.html(theme.color_key_html(
                {f"{label} ({minutes:.0f}m)": color for label, minutes, color in zip(zone_labels, workout_hint['zones'], zone_colors)},
                title="HR Zones",
            ))

    with st.container(border=True):
        st.markdown("**Exercises**")

        session_key = session_data['id'] if pd.notna(session_data['id']) else session_data['date'].strftime('%Y%m%d')

        if is_new:
            # Before/After default to the most recent past session's picks
            default_before = []
            default_during = _category_exercise_pool(new_cat, df_dict)
            default_after = []

            if not df_past.empty:
                latest_session = df_past.sort_values(by='date', ascending=False).iloc[0]
                if pd.notna(latest_session['exercises']):
                    last_exercises = [ex.strip() for ex in str(latest_session['exercises']).split(',') if ex.strip()]
                    default_before = [ex for ex in last_exercises if ex in exercises_before]
                    default_after = [ex for ex in last_exercises if ex in exercises_after]
        else:
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

        selected_exercises = selected_before + selected_during + selected_after

    def _finish():
        refresh_data()
        st.session_state.pop('confirm_delete_session_id', None)
        if on_saved:
            on_saved()
        else:
            st.rerun()

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

        components.confirm_action(
            'confirm_delete_session_id' if st.session_state.get('confirm_delete_session_id') == session_id else '__no_match__',
            "Delete this session permanently? This also removes its logged exercises.",
            "Yes, delete",
            on_confirm=lambda: delete_session(session_id),
            on_success=_finish,
            spinner_text="Deleting…",
            key_prefix=f'delete_session_{session_id}',
        )


def _reset_delete_confirmation():
    """Clears any pending session-delete confirmation, so a modal dismissed
    via the X/backdrop/ESC (instead of Cancel) doesn't reopen with the
    warning still showing."""
    st.session_state.pop('confirm_delete_session_id', None)


@st.dialog("Session details", icon=":material/edit:", on_dismiss=_reset_delete_confirmation)
def edit_session_modal(
    session_data, df_past, df_dict, exercises_before, exercises_during, exercises_after,
    refresh_data, df_whoop_workouts, is_new=False,
):
    """Pop-up form for viewing/editing an existing session, or logging a
    new one when is_new=True
    """
    workout_hint = _lookup_workout_hint(df_whoop_workouts, session_data['date'])
    _render_session_edit_form(
        session_data, df_past, df_dict, exercises_before, exercises_during, exercises_after,
        refresh_data, is_new=is_new, workout_hint=workout_hint,
    )


def _advance_due_carousel():
    """Moves the due-sessions carousel to the next entry"""
    st.session_state.due_carousel_index += 1
    st.rerun()


def _reset_due_carousel():
    """Runs when the overdue-sessions dialog is dismissed via X/backdrop/Esc
    instead of finishing the queue - closes it for good (the header bell
    reseeds the queue fresh on its next click) and clears any pending
    delete confirmation."""
    st.session_state.due_carousel_open = False
    _reset_delete_confirmation()


@st.dialog("Catch up on missed sessions", icon=":material/schedule:", on_dismiss=_reset_due_carousel)
def due_sessions_carousel(df_all_calendar, df_past, df_whoop, df_whoop_workouts, df_dict, exercises_before, exercises_during, exercises_after, refresh_data):
    """Opened by clicking the header notification bell when past sessions
    have no effort logged. Saving or deleting the current entry advances
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

    whoop_hint = None
    if not df_whoop.empty:
        whoop_match = df_whoop[df_whoop['date'] == session_data['date']]
        if not whoop_match.empty:
            whoop_row = whoop_match.iloc[0]
            strain_val = None if pd.isna(whoop_row['strain']) else float(whoop_row['strain'])
            recovery_val = None if pd.isna(whoop_row['recovery_score']) else int(whoop_row['recovery_score'])
            suggested = suggest_effort(strain_val, recovery_val)
            if suggested is not None:
                whoop_hint = {
                    'suggested_effort': suggested,
                    'strain': strain_val,
                    'recovery_score': recovery_val,
                }

    workout_hint = _lookup_workout_hint(df_whoop_workouts, session_data['date'])

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

    st.warning("This session is missing its effort - fill it in or delete it.")

    _render_session_edit_form(
        session_data, df_past, df_dict, exercises_before, exercises_during, exercises_after,
        refresh_data, is_new=False, on_saved=_advance_due_carousel, whoop_hint=whoop_hint, workout_hint=workout_hint,
    )


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
