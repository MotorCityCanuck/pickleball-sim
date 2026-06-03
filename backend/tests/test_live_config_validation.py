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


def test_validate_live_config_payload_accepts_default_hidden_performance_bias():
    payload = deepcopy(DEFAULT_CONFIG_PAYLOAD)

    issues = validate_live_config_payload(payload)

    assert [
        issue
        for issue in issues
        if issue.path and issue.path.startswith("hidden_performance_bias")
    ] == []


def test_validate_live_config_payload_rejects_invalid_instrumentation_flag():
    payload = deepcopy(DEFAULT_CONFIG_PAYLOAD)
    payload["instrumentation"]["players_enabled"] = "yes"

    issues = validate_live_config_payload(payload)

    assert len(issues) == 1
    assert issues[0].path == "instrumentation.players_enabled"
    assert issues[0].message == "must be a boolean."


def test_validate_live_config_payload_rejects_invalid_hidden_bias_range():
    payload = deepcopy(DEFAULT_CONFIG_PAYLOAD)
    payload["hidden_performance_bias"]["age_advantage"][
        "close_match_competitiveness_threshold"
    ] = 1.2

    issues = validate_live_config_payload(payload)

    assert len(issues) == 1
    assert (
        issues[0].path
        == "hidden_performance_bias.age_advantage.close_match_competitiveness_threshold"
    )
    assert issues[0].message == "must be between 0 and 1."


def test_validate_live_config_payload_rejects_invalid_regional_strength_map():
    payload = deepcopy(DEFAULT_CONFIG_PAYLOAD)
    payload["hidden_performance_bias"]["regional_strength"]["map"] = {
        "Florida": "strong",
    }

    issues = validate_live_config_payload(payload)

    assert len(issues) == 1
    assert issues[0].path == "hidden_performance_bias.regional_strength.map"
    assert issues[0].message == "must contain only numeric rating-point values."


def test_validate_live_config_payload_rejects_descending_partnership_thresholds():
    payload = deepcopy(DEFAULT_CONFIG_PAYLOAD)
    payload["hidden_performance_bias"]["partnership_affinity"][
        "matches_together_threshold_1"
    ] = 20
    payload["hidden_performance_bias"]["partnership_affinity"][
        "matches_together_threshold_2"
    ] = 10

    issues = validate_live_config_payload(payload)

    assert len(issues) == 1
    assert (
        issues[0].path
        == "hidden_performance_bias.partnership_affinity.matches_together_threshold_2"
    )
    assert issues[0].message == (
        "must be greater than or equal to matches_together_threshold_1."
    )
