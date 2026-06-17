"""Tests for durable job progress liveness policies."""
from datetime import datetime, timedelta
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.generation.progress_liveness import liveness_state_for_stage


def test_destructive_reset_is_likely_stalled_after_fifteen_quiet_minutes():
    now = datetime(2026, 6, 17, 19, 32, 0)

    state = liveness_state_for_stage(
        stage_name="destructive_reset",
        status="running",
        last_heartbeat_at=now - timedelta(minutes=17),
        now=now,
    )

    assert state == "likely_stalled"


def test_destructive_reset_is_quiet_before_stalled_threshold():
    now = datetime(2026, 6, 17, 19, 32, 0)

    state = liveness_state_for_stage(
        stage_name="destructive_reset",
        status="running",
        last_heartbeat_at=now - timedelta(minutes=10),
        now=now,
    )

    assert state == "quiet"
