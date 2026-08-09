"""
Add/edit modals for the Exercise Library.
"""

import pandas as pd
import streamlit as st

from data_pipeline import PipelineConfig, add_exercise, update_exercise, delete_exercise


@st.dialog("New exercise", icon=":material/add:")
def add_exercise_modal(client, df_dict, refresh_data):
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
                success = add_exercise(client, payload)
            if success:
                refresh_data()
                st.rerun()


@st.dialog("Edit exercise", icon=":material/edit:")
def edit_exercise_modal(client, exercise_data, refresh_data):
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
                success = update_exercise(client, exercise_id, payload)
            if success:
                refresh_data()
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
                    success = delete_exercise(client, exercise_id)
                if success:
                    refresh_data()
                    st.session_state.pop('confirm_delete_exercise_id', None)
                    st.rerun()
        with col_no:
            if st.button("Cancel", icon=":material/close:", width="stretch"):
                st.session_state.pop('confirm_delete_exercise_id', None)
                st.rerun()
