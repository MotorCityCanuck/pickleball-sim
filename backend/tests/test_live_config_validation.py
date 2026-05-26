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


def test_validate_live_config_payload_maps_match_volume_noise_factor_errors():
    payload = deepcopy(DEFAULT_CONFIG_PAYLOAD)
    payload["match_scheduling"]["match_volume_noise_factor"] = -0.1

    issues = validate_live_config_payload(payload)

    assert len(issues) == 1
    assert issues[0].path == "match_scheduling.match_volume_noise_factor"
    assert issues[0].message == "match_volume_noise_factor must be between 0 and 1"


def test_validate_live_config_payload_maps_rematch_penalty_window_errors():
    payload = deepcopy(DEFAULT_CONFIG_PAYLOAD)
    payload["matchmaking"]["rematch_penalty_window_days"] = -1

    issues = validate_live_config_payload(payload)

    assert len(issues) == 1
    assert issues[0].path == "matchmaking.rematch_penalty_window_days"
    assert issues[0].message == "rematch_penalty_window_days must be a non-negative integer"
