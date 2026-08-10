"""
Athlete profile (body metrics, current grades, avatar) and injury log,
backed by Supabase. Named user_profile, not profile, so it doesn't shadow
Python's own stdlib profile module.
"""

from .models import ProfileRecord, InjuryRecord
from .store import (
    current_grade_for, get_profile, update_profile, upload_avatar, list_injuries, add_injury, resolve_injury,
    PROFILES_TABLE, INJURIES_TABLE, AVATARS_BUCKET,
)
