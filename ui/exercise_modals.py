"""
Add/edit modals for the Exercise Library.
"""

import pandas as pd
import streamlit as st

from data_pipeline import PipelineConfig, add_exercise, update_exercise, delete_exercise
from . import components


def _render_exercise_fields(existing=None):
    """Renders every exercise field except Name, pre-filled from `existing`
    (a df_dict row) when editing, or blank when existing=None (adding).
    Returns the collected values as a dict with the same keys `add_exercise`
    /`update_exercise` expect (minus 'Name')."""
    type_opts = PipelineConfig.ALLOWED_EXERCISE_TYPES
    if existing is not None and pd.notna(existing['type']) and existing['type'] in type_opts:
        type_index = type_opts.index(existing['type'])
    else:
        type_index = 0
    new_type = st.selectbox("Type", type_opts, index=type_index)

    current_sets = None if existing is None or pd.isna(existing['sets']) else int(existing['sets'])
    new_sets = st.number_input("Sets", min_value=0, value=current_sets, step=1)

    if new_type == 'Reps':
        current_reps = None if existing is None or pd.isna(existing['reps']) else int(existing['reps'])
        new_reps = st.number_input("Reps", min_value=0, value=current_reps, step=1)
        new_time = None
    else:
        current_time = "" if existing is None or pd.isna(existing['time']) else str(existing['time'])
        new_time = st.text_input("Time (e.g. 00:15)", value=current_time)
        new_reps = None

    current_rest = None if existing is None or pd.isna(existing['rest']) else int(existing['rest'])
    new_rest = st.number_input("Rest", min_value=0, value=current_rest, step=1)

    current_comments = "" if existing is None or pd.isna(existing['comments']) else str(existing['comments'])
    new_comments = st.text_area("Comments", value=current_comments)

    phase_opts = PipelineConfig.ALLOWED_PHASES
    if existing is not None and pd.notna(existing['phase']) and existing['phase'] in phase_opts:
        phase_index = phase_opts.index(existing['phase'])
    else:
        phase_index = 0
    new_phase = st.selectbox("Phase", phase_opts, index=phase_index)

    category_opts = PipelineConfig.ALLOWED_EXERCISE_CATEGORIES
    current_categories = [] if existing is None else [c for c in (existing.get('categories') or []) if c in category_opts]
    new_categories = st.multiselect("Categories", category_opts, default=current_categories)

    inclusion_opts = ["Normal", "Always include", "Exclude from plan"]
    if existing is not None and bool(existing.get('mandatory', False)):
        inclusion_index = 1
    elif existing is not None and bool(existing.get('exclude_from_plan', False)):
        inclusion_index = 2
    else:
        inclusion_index = 0
    plan_inclusion = st.radio("Plan inclusion", inclusion_opts, index=inclusion_index)
    new_mandatory = plan_inclusion == "Always include"
    new_exclude_from_plan = plan_inclusion == "Exclude from plan"

    return {
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


@st.dialog("New exercise", icon=":material/add:")
def add_exercise_modal(df_dict, refresh_data):
    new_name = st.text_input("Name")
    fields = _render_exercise_fields()

    if st.button("Create exercise", icon=":material/save:", type="primary", width="stretch"):
        name_clean = new_name.strip()
        existing_names_lower = df_dict['name'].dropna().str.lower().tolist() if 'name' in df_dict.columns else []

        if not name_clean:
            st.error("Name is required.")
        elif name_clean.lower() in existing_names_lower:
            st.error(f"An exercise named '{name_clean}' already exists.")
        else:
            payload = {'Name': name_clean, **fields}
            with st.spinner("Saving…"):
                success = add_exercise(payload)
            if success:
                refresh_data()
                st.rerun()


@st.dialog("Edit exercise", icon=":material/edit:")
def edit_exercise_modal(exercise_data, refresh_data):
    st.write(f"**Name:** {exercise_data['name']}")
    exercise_id = int(exercise_data['id'])

    fields = _render_exercise_fields(existing=exercise_data)

    col_save, col_del = st.columns(2)

    with col_save:
        if st.button("Save changes", icon=":material/save:", type="primary", width="stretch"):
            with st.spinner("Saving…"):
                success = update_exercise(exercise_id, fields)
            if success:
                refresh_data()
                st.session_state.pop('confirm_delete_exercise_id', None)
                st.rerun()

    with col_del:
        if st.button("Delete exercise", icon=":material/delete:", width="stretch", key="danger_delete_exercise"):
            st.session_state.confirm_delete_exercise_id = exercise_id

    components.confirm_action(
        'confirm_delete_exercise_id' if st.session_state.get('confirm_delete_exercise_id') == exercise_id else '__no_match__',
        f"Delete **{exercise_data['name']}** permanently? This also removes it from any sessions it's linked to.",
        "Yes, delete",
        on_confirm=lambda: delete_exercise(exercise_id),
        on_success=refresh_data,
        spinner_text="Deleting…",
        key_prefix='delete_exercise',
    )
