"""
Sidebar "Profile & settings" panel: athlete profile (display name,
avatar, current grades, body metrics, injury log) and account management
(change password/email, delete account).
"""

import streamlit as st

from data_pipeline import PipelineConfig
from user_profile import update_profile, upload_avatar, add_injury, resolve_injury
from gyms import list_gyms, get_user_memberships, join_gym, list_gym_members, update_member_role, ALL_ROLES
from auth import change_password, change_email, delete_account
from ui.auth_gate import end_session
import theme


def _grade_selectbox(label, options, current_value, key):
    return st.selectbox(
        label, [None] + options,
        index=(options.index(current_value) + 1) if current_value in options else 0,
        format_func=lambda g: "Not set" if g is None else g,
        key=key,
    )


def _render_athlete_fields(client, user_id, profile, refresh_athlete_profile):
    st.markdown("**Athlete profile**")

    if profile.get('avatar_url'):
        st.image(profile['avatar_url'], width=60)
    display_name = st.text_input("Display name", value=profile.get('display_name') or "", key="profile_display_name")

    avatar_file = st.file_uploader("Avatar", type=["png", "jpg", "jpeg"], key="profile_avatar_uploader")
    if avatar_file is not None and st.button("Upload avatar", icon=":material/upload:", width="stretch", key="profile_avatar_upload_button"):
        with st.spinner("Uploading…"):
            avatar_url = upload_avatar(client, user_id, avatar_file)
        if avatar_url:
            refresh_athlete_profile()
            st.rerun()

    gym_grade = _grade_selectbox(
        "Current gym grade", list(PipelineConfig.GYM_MAPPING.keys()), profile.get('current_gym_grade'), "profile_gym_grade",
    )
    if gym_grade:
        st.html(theme.grade_swatch_html(gym_grade))
    moonboard_grade = _grade_selectbox(
        "Current moonboard grade", list(PipelineConfig.MOONBOARD_MAPPING.keys()), profile.get('current_moonboard_grade'), "profile_moonboard_grade",
    )

    weight = st.number_input("Weight (kg)", min_value=0.0, value=profile.get('weight_kg'), step=0.5, key="profile_weight")
    height = st.number_input("Height (cm)", min_value=0.0, value=profile.get('height_cm'), step=1.0, key="profile_height")

    if st.button("Save profile", icon=":material/save:", width="stretch", key="profile_save_button"):
        with st.spinner("Saving…"):
            success = update_profile(
                client, user_id,
                display_name=display_name, weight_kg=weight, height_cm=height,
                current_gym_grade=gym_grade, current_moonboard_grade=moonboard_grade,
            )
        if success:
            refresh_athlete_profile()
            st.rerun()


def _render_gyms(client, memberships, gyms_list, refresh_memberships):
    st.markdown("**My gyms**")
    if not memberships:
        st.caption("You haven't joined a gym yet.")
    for membership in memberships:
        st.write(f"{membership['gym_name']} — _{membership['role']}_")

    joined_gym_ids = {m['gym_id'] for m in memberships}
    joinable = [g for g in gyms_list if g['id'] not in joined_gym_ids]
    if joinable:
        gym_to_join = st.selectbox(
            "Join a gym", joinable, format_func=lambda g: g['name'], key="profile_join_gym_select",
        )
        if st.button("Join", icon=":material/add:", width="stretch", key="profile_join_gym_button"):
            with st.spinner("Joining…"):
                success = join_gym(client, gym_to_join['id'])
            if success:
                refresh_memberships()
                st.rerun()
    else:
        st.caption("No more gyms to join.")


def _render_gym_admin(client, memberships):
    admin_memberships = [m for m in memberships if m['role'] == 'admin']
    if not admin_memberships:
        return
    st.markdown("**Manage members**")
    for membership in admin_memberships:
        with st.expander(membership['gym_name']):
            members = list_gym_members(client, membership['gym_id'])
            for member in members:
                col_name, col_role, col_save = st.columns([2, 2, 1])
                with col_name:
                    st.write(member.get('display_name') or member['user_id'])
                with col_role:
                    new_role = st.selectbox(
                        "Role", ALL_ROLES, index=ALL_ROLES.index(member['role']),
                        label_visibility="collapsed", key=f"member_role_{member['id']}",
                    )
                with col_save:
                    if st.button("Save", key=f"save_member_role_{member['id']}", width="stretch"):
                        if new_role != member['role']:
                            with st.spinner("Updating…"):
                                success = update_member_role(client, member['id'], new_role)
                            # No st.rerun() here: it would restart the script
                            # before the browser ever paints this message -
                            # same reason _render_account's "Password
                            # changed." message below doesn't rerun either.
                            if success:
                                st.success(f"Role updated to {new_role}.")


def _render_injuries(client, injuries, refresh_injuries):
    st.markdown("**Injuries**")
    active = [i for i in injuries if i.get('resolved_at') is None]
    if not active:
        st.caption("No active injuries logged.")
    for injury in active:
        col_info, col_action = st.columns([3, 1])
        with col_info:
            st.write(f"{injury['body_part']} — since {injury['started_at']}")
            if injury.get('description'):
                st.caption(injury['description'])
        with col_action:
            if st.button("Resolve", key=f"resolve_injury_{injury['id']}", width="stretch"):
                with st.spinner("Updating…"):
                    success = resolve_injury(client, injury['id'], injury['started_at'])
                if success:
                    refresh_injuries()
                    st.rerun()

    with st.form("add_injury_form", border=False, clear_on_submit=True):
        body_part = st.text_input("Body part")
        description = st.text_input("Description (optional)")
        started_at = st.date_input("Started")
        if st.form_submit_button("Log injury", icon=":material/add:", width="stretch"):
            if not body_part.strip():
                st.error("Body part is required.")
            else:
                with st.spinner("Saving…"):
                    success = add_injury(client, body_part.strip(), description.strip() or None, started_at)
                if success:
                    refresh_injuries()
                    st.rerun()


def _render_account(client, user_id):
    st.markdown("**Account**")

    with st.form("change_password_form", border=False):
        new_password = st.text_input("New password", type="password", key="account_new_password")
        if st.form_submit_button("Change password", width="stretch"):
            if len(new_password) < 6:
                st.error("At least 6 characters.")
            else:
                error = change_password(client, new_password)
                if error:
                    st.error(error)
                else:
                    st.success("Password changed.")

    with st.form("change_email_form", border=False):
        new_email = st.text_input("New email", key="account_new_email")
        if st.form_submit_button("Change email", width="stretch"):
            error = change_email(client, new_email)
            if error:
                st.error(error)
            else:
                st.info("Check your new email to confirm the change.")

    if st.button("Delete account", icon=":material/delete_forever:", width="stretch", key="danger_delete_account"):
        st.session_state.confirm_delete_account = True

    if st.session_state.get('confirm_delete_account'):
        st.warning("Delete your account? This permanently removes your profile, goals, exercises, sessions, and injury log. This can't be undone.")
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.button("Yes, delete", icon=":material/warning:", width="stretch", key="danger_confirm_delete_account_yes"):
                with st.spinner("Deleting your account…"):
                    success = delete_account(user_id)
                if success:
                    st.session_state.pop('confirm_delete_account', None)
                    end_session()
                    st.rerun()
        with col_no:
            if st.button("Cancel", width="stretch", key="cancel_delete_account"):
                st.session_state.pop('confirm_delete_account', None)
                st.rerun()


def render(client, user_id, profile, injuries, gyms_list, memberships, refresh_athlete_profile, refresh_injuries, refresh_memberships):
    with st.sidebar:
        with st.expander("Profile & settings", icon=":material/account_circle:"):
            _render_athlete_fields(client, user_id, profile, refresh_athlete_profile)
            st.divider()
            _render_gyms(client, memberships, gyms_list, refresh_memberships)
            _render_gym_admin(client, memberships)
            st.divider()
            _render_injuries(client, injuries, refresh_injuries)
            st.divider()
            _render_account(client, user_id)
