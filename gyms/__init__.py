"""
Gym entities and per-gym membership/roles: joining a gym, listing your
memberships, and (for gym admins) managing a gym's member roster. Kept
separate from user_profile/, which is about personal athlete data, not
multi-tenant identity/permissions.
"""

from .models import GymRecord, GymMembershipRecord, GymMemberRecord, is_elevated, ALL_ROLES
from .store import (
    list_gyms, get_user_memberships, join_gym, list_gym_members, update_member_role,
    GYMS_TABLE, GYM_MEMBERSHIPS_TABLE,
)
