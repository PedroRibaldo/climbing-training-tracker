"""
WHOOP integration for the Climbing Training Tracker.

Handles Supabase persistence of daily WHOOP metrics (recovery, HRV,
strain, resting heart rate) and the app-wide on/off toggle. Split into
models/store internally; this file re-exports the full public surface so
`from whoop import X` keeps working regardless of internal file layout.
"""

from .effort import suggest_effort
from .models import WhoopConfig, WhoopMetricsRecord
from .store import get_daily_metrics, get_latest_metrics, is_enabled, set_enabled
