"""
The Goals tab: set a grade goal and generate a training plan, or track
progress on/regenerate/abandon the currently active one.
"""

import pandas as pd
import streamlit as st

from data_pipeline import PipelineConfig
from training_plan import PlanConfig, preview_plan, create_goal_and_plan, regenerate_plan, abandon_goal
import theme
from . import components


def render(active_goal, df_past, df_future, df_dict, refresh_data, refresh_all):
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
                    st.caption(f"{most_neglected} is trained least relative to your other categories - weighted up in this plan")

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
                        refresh_all()
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
        st.write(f"Week {current_week} of {active_goal['total_weeks']} - {current_phase} phase")
        st.html(theme.phase_timeline_html(active_goal['phase_breakdown'], active_goal['total_weeks'], elapsed_weeks))

        col_regen, col_abandon = st.columns(2)
        with col_regen:
            if st.button("Regenerate plan", icon=":material/refresh:", width="stretch"):
                st.session_state.confirm_regenerate_goal = True
        with col_abandon:
            if st.button("Abandon goal", icon=":material/delete:", width="stretch", key="danger_abandon_goal"):
                st.session_state.confirm_abandon_goal = True

        components.confirm_action(
            'confirm_regenerate_goal',
            "Re-roll the remaining weeks of this plan? Future, not-yet-logged sessions from this goal will be replaced.",
            "Yes, regenerate",
            on_confirm=lambda: regenerate_plan(active_goal, df_past, df_future, df_dict),
            on_success=refresh_data,
            spinner_text="Regenerating…",
            key_prefix='regenerate_goal',
        )

        components.confirm_action(
            'confirm_abandon_goal',
            "Abandon this goal? Future, not-yet-logged sessions from it will be deleted. Already-logged sessions stay as real history.",
            "Yes, abandon",
            on_confirm=lambda: abandon_goal(active_goal['id'], df_future),
            on_success=refresh_all,
            spinner_text="Abandoning…",
            key_prefix='abandon_goal',
        )
