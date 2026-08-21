"""
The Exercise Library tab: browse exercises by phase, add new ones, click
to edit or delete.
"""

import streamlit as st

from data_pipeline import PipelineConfig
from . import exercise_modals


def render(df_dict, refresh_data):

    if st.button("Add new exercise", icon=":material/add:", type="primary"):
        exercise_modals.add_exercise_modal(df_dict, refresh_data)

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
                exercise_modals.edit_exercise_modal(phase_df.iloc[selected_rows[0]], refresh_data)
