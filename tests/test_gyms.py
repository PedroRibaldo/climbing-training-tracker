"""
Tests for the pure validation/guard logic in gyms/. These never touch
Supabase - they exercise the pydantic models and is_elevated() directly
with hand-built inputs.

Run with: pytest
"""
import pytest
from pydantic import ValidationError

from gyms import GymRecord, GymMembershipRecord, GymMemberRecord, is_elevated


class TestGymRecord:

    def test_valid_gym_parses(self):
        gym = GymRecord.model_validate({'id': 1, 'name': 'Boulder Peak', 'location': 'Lisbon'})
        assert gym.name == 'Boulder Peak'

    def test_missing_location_defaults_to_none(self):
        gym = GymRecord.model_validate({'id': 1, 'name': 'Boulder Peak'})
        assert gym.location is None


class TestGymMembershipRecord:

    def test_valid_membership_parses(self):
        membership = GymMembershipRecord.model_validate({
            'id': 1, 'gym_id': 1, 'gym_name': 'Boulder Peak', 'role': 'climber', 'joined_at': '2026-08-01T12:00:00',
        })
        assert membership.role == 'climber'
        assert membership.gym_name == 'Boulder Peak'

    def test_unknown_role_raises(self):
        with pytest.raises(ValidationError):
            GymMembershipRecord.model_validate({
                'id': 1, 'gym_id': 1, 'gym_name': 'Boulder Peak', 'role': 'owner', 'joined_at': '2026-08-01T12:00:00',
            })

    def test_missing_joined_at_defaults_to_none(self):
        membership = GymMembershipRecord.model_validate({
            'id': 1, 'gym_id': 1, 'gym_name': 'Boulder Peak', 'role': 'admin',
        })
        assert membership.joined_at is None


class TestGymMemberRecord:

    def test_valid_member_parses(self):
        member = GymMemberRecord.model_validate({
            'id': 1, 'gym_id': 1, 'user_id': 'abc-123', 'display_name': 'Alex', 'role': 'setter', 'joined_at': '2026-08-01T12:00:00',
        })
        assert member.display_name == 'Alex'
        assert member.role == 'setter'

    def test_missing_display_name_defaults_to_none(self):
        member = GymMemberRecord.model_validate({
            'id': 1, 'gym_id': 1, 'user_id': 'abc-123', 'role': 'climber',
        })
        assert member.display_name is None


class TestIsElevated:

    def test_climber_is_not_elevated(self):
        assert is_elevated('climber') is False

    @pytest.mark.parametrize('role', ['worker', 'setter', 'trainer', 'competitor', 'admin'])
    def test_other_roles_are_elevated(self, role):
        assert is_elevated(role) is True
