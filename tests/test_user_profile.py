"""
Tests for the pure validation/guard logic in user_profile.py. These never
touch Supabase - they exercise the pydantic models and resolve_injury's
date guard directly with hand-built inputs.

Run with: pytest
"""
from datetime import date

import pytest
from pydantic import ValidationError

from user_profile import ProfileRecord, InjuryRecord, resolve_injury


class TestProfileRecord:

    def test_valid_profile_parses(self):
        profile = ProfileRecord.model_validate({
            'id': 'abc-123', 'role': 'user', 'display_name': 'Alex',
            'weight_kg': 68.5, 'height_cm': 175, 'current_gym_grade': 'Blue',
            'current_moonboard_grade': 'V4',
        })
        assert profile.display_name == 'Alex'
        assert profile.current_gym_grade == 'Blue'

    def test_missing_optional_fields_default_to_none(self):
        profile = ProfileRecord.model_validate({'id': 'abc-123', 'role': 'user'})
        assert profile.display_name is None
        assert profile.weight_kg is None
        assert profile.current_gym_grade is None
        assert profile.current_moonboard_grade is None

    def test_unknown_gym_grade_raises(self):
        with pytest.raises(ValidationError):
            ProfileRecord.model_validate({'id': 'abc-123', 'role': 'user', 'current_gym_grade': 'Turquoise'})

    def test_unknown_moonboard_grade_raises(self):
        with pytest.raises(ValidationError):
            ProfileRecord.model_validate({'id': 'abc-123', 'role': 'user', 'current_moonboard_grade': 'V99'})

    def test_blank_grade_string_becomes_none(self):
        profile = ProfileRecord.model_validate({'id': 'abc-123', 'role': 'user', 'current_gym_grade': '  '})
        assert profile.current_gym_grade is None


class TestInjuryRecord:

    def test_valid_active_injury_parses(self):
        injury = InjuryRecord.model_validate({
            'id': 1, 'body_part': 'Finger (A2 pulley)', 'description': 'Popped on a crimp',
            'started_at': '2026-08-01', 'resolved_at': None,
        })
        assert injury.body_part == 'Finger (A2 pulley)'
        assert injury.resolved_at is None

    def test_resolved_injury_parses_resolved_at(self):
        injury = InjuryRecord.model_validate({
            'id': 1, 'body_part': 'Shoulder', 'description': None,
            'started_at': '2026-07-01', 'resolved_at': '2026-07-20',
        })
        assert injury.resolved_at == date(2026, 7, 20)

    def test_missing_body_part_raises(self):
        with pytest.raises(ValidationError):
            InjuryRecord.model_validate({'id': 1, 'body_part': '', 'started_at': '2026-08-01'})

    def test_unparseable_started_at_raises(self):
        with pytest.raises(ValidationError):
            InjuryRecord.model_validate({'id': 1, 'body_part': 'Elbow', 'started_at': 'not-a-date'})


class TestResolveInjuryDateGuard:

    def test_rejects_resolution_before_start(self):
        # The guard runs before any Supabase call, so passing client=None
        # proves it short-circuits rather than touching the network.
        assert resolve_injury(None, injury_id=1, started_at=date(2099, 1, 1)) is False
