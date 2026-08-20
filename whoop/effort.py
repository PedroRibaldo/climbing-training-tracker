"""
Pure computation of a suggested training effort (1-10) from a day's WHOOP
metrics, used to pre-fill the due-sessions carousel's Effort field.
"""

from typing import Optional


def suggest_effort(strain: Optional[float], recovery_score: Optional[int]) -> Optional[int]:
    """Suggested effort (1-10) from WHOOP strain (0-21), adjusted by that
    morning's recovery band. Returns None when strain is unavailable -
    strain is the only same-day exertion signal WHOOP provides; recovery
    score alone (a pre-day readiness reading) can't stand in for it."""
    if strain is None:
        return None

    base = round(strain / 21 * 10)
    base = max(1, min(10, base))

    if recovery_score is not None:
        if recovery_score < 33:
            base += 1
        elif recovery_score > 66:
            base -= 1

    return max(1, min(10, base))
