"""Tests for live config validation helpers."""
from copy import deepcopy
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.default_configuration import DEFAULT_CONFIG_PAYLOAD  # noqa: E402
from app.core.live_config_validation import validate_live_config_payload  # noqa: E402


def test_validate_live_config_payload_rejects_invalid_club_size_distribution_total():
    payload = deepcopy(DEFAULT_CONFIG_PAYLOAD)
    payload["club_generation"]["club_size_distribution"] = {
        "tiny": 0.40,
        "small": 0.30,
        "medium": 0.20,
        "large": 0.10,
        "mega": 0.10,
    }

    issues = validate_live_config_payload(payload)

    assert len(issues) == 1
    assert issues[0].path == "club_generation.capacity_ranges"
    assert issues[0].message == "club_size_distribution weights must sum to 1.0"
