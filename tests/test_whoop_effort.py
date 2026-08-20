"""
Tests for suggest_effort() in whoop/effort.py.

Run with: pytest
"""
from whoop import suggest_effort


class TestSuggestEffort:

    def test_mid_strain_yellow_recovery_no_adjustment(self):
        assert suggest_effort(strain=10.5, recovery_score=50) == 5

    def test_mid_strain_red_recovery_adjusts_up(self):
        assert suggest_effort(strain=10.5, recovery_score=20) == 6

    def test_mid_strain_green_recovery_adjusts_down(self):
        assert suggest_effort(strain=10.5, recovery_score=80) == 4

    def test_missing_recovery_uses_strain_only(self):
        assert suggest_effort(strain=10.5, recovery_score=None) == 5

    def test_missing_strain_returns_none_even_with_recovery(self):
        assert suggest_effort(strain=None, recovery_score=20) is None

    def test_missing_strain_and_recovery_returns_none(self):
        assert suggest_effort(strain=None, recovery_score=None) is None

    def test_zero_strain_clamps_base_to_minimum(self):
        assert suggest_effort(strain=0.0, recovery_score=50) == 1

    def test_zero_strain_red_recovery_adjusts_up_from_clamped_base(self):
        assert suggest_effort(strain=0.0, recovery_score=10) == 2

    def test_max_strain_green_recovery_clamps_after_adjustment(self):
        assert suggest_effort(strain=21.0, recovery_score=90) == 9

    def test_max_strain_red_recovery_clamps_at_maximum(self):
        assert suggest_effort(strain=21.0, recovery_score=10) == 10
