"""Tests for metadata scaffolding behind the future config editor."""
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core import (  # noqa: E402
    CONFIG_EDITOR_FIELDS,
    CONFIG_EDITOR_SECTIONS,
    build_config_editor_sections,
    default_config_payload,
    get_payload_value,
)


def test_config_editor_field_paths_are_unique():
    paths = [field.path for field in CONFIG_EDITOR_FIELDS]
    assert len(paths) == len(set(paths))


def test_config_editor_sections_only_reference_declared_fields():
    declared_paths = {field.path for field in CONFIG_EDITOR_FIELDS}

    for section in CONFIG_EDITOR_SECTIONS:
        assert section.field_paths
        for path in section.field_paths:
            assert path in declared_paths


def test_default_payload_provides_values_for_scaffolded_fields():
    payload = default_config_payload()

    missing = [
        field.path
        for field in CONFIG_EDITOR_FIELDS
        if (
            get_payload_value(payload, field.path) is None
            and field.default_value is not None
        )
    ]

    assert missing == []


def test_build_config_editor_sections_attaches_current_values():
    payload = default_config_payload()
    payload["simulation"]["master_seed"] = 123
    payload["team_formation"]["rating_gap_max"] = 1750.0
    payload["team_formation"]["team_persistence_probability_competitive"] = 0.91
    payload["club_generation"]["cross_region_assignment_enabled"] = True
    payload["club_generation"]["multi_club_membership_rate"] = 0.12
    payload["club_generation"]["club_size_distribution"]["tiny"] = 0.5
    payload["club_generation"]["capacity_ranges"]["tiny"] = [12, 24]
    payload["match_scheduling"]["match_volume_noise_factor"] = 0.33
    payload["match_scheduling"]["monthly_matches_per_active_player_std_dev"] = 6.5
    payload["match_scheduling"]["matches_per_team_per_month"] = 5.5
    payload["matchmaking"]["rematch_penalty_window_days"] = 14
    payload["player_generation"]["monthly_player_inactivation_rate"] = 0.07
    payload["player_generation"]["initial_skill_seed"]["mean"] = 1650
    payload["ratings"]["k_factor_new_player"] = 52.0
    payload["games_and_scores"]["win_by_two_extension_rate"] = 0.2
    payload["hidden_performance_bias"]["enabled"] = True
    payload["hidden_performance_bias"]["age_advantage"]["max_rating_points"] = 42

    sections = build_config_editor_sections(payload)
    field_states = {
        field.definition.path: field
        for section in sections
        for field in section.fields
    }

    assert field_states["simulation.master_seed"].value == 123
    assert field_states["simulation.master_seed"].is_default_value is False
    assert field_states["team_formation.rating_gap_max"].value == 1750.0
    assert field_states["team_formation.rating_gap_max"].is_default_value is False
    assert (
        field_states["team_formation.team_persistence_probability_competitive"].value
        == 0.91
    )
    assert (
        field_states["team_formation.team_persistence_probability_competitive"].is_default_value
        is False
    )
    assert field_states["match_scheduling.match_volume_noise_factor"].value == 0.33
    assert (
        field_states["match_scheduling.match_volume_noise_factor"].is_default_value
        is False
    )
    assert (
        field_states["match_scheduling.monthly_matches_per_active_player_std_dev"].value
        == 6.5
    )
    assert (
        field_states[
            "match_scheduling.monthly_matches_per_active_player_std_dev"
        ].is_default_value
        is False
    )
    assert field_states["matchmaking.rematch_penalty_window_days"].value == 14
    assert (
        field_states["matchmaking.rematch_penalty_window_days"].is_default_value
        is False
    )
    assert field_states["match_scheduling.matches_per_team_per_month"].value == 5.5
    assert (
        field_states["match_scheduling.matches_per_team_per_month"].is_default_value
        is False
    )
    assert field_states["player_generation.monthly_player_inactivation_rate"].value == 0.07
    assert (
        field_states["player_generation.monthly_player_inactivation_rate"].is_default_value
        is False
    )
    assert field_states["player_generation.initial_skill_seed.mean"].value == 1650
    assert (
        field_states["player_generation.initial_skill_seed.mean"].is_default_value
        is False
    )
    assert field_states["ratings.k_factor_new_player"].value == 52.0
    assert field_states["ratings.k_factor_new_player"].is_default_value is False
    assert field_states["games_and_scores.win_by_two_extension_rate"].value == 0.2
    assert (
        field_states["games_and_scores.win_by_two_extension_rate"].is_default_value
        is False
    )
    assert field_states["hidden_performance_bias.enabled"].value is True
    assert field_states["hidden_performance_bias.enabled"].is_default_value is False
    assert (
        field_states["hidden_performance_bias.age_advantage.max_rating_points"].value
        == 42
    )
    assert (
        field_states[
            "hidden_performance_bias.age_advantage.max_rating_points"
        ].is_default_value
        is False
    )
    assert field_states["club_generation.multi_club_membership_rate"].value == 0.12
    assert (
        field_states["club_generation.multi_club_membership_rate"].is_default_value
        is False
    )
    assert (
        field_states["club_generation.cross_region_assignment_enabled"].value
        is True
    )
    assert field_states["club_generation.cross_region_assignment_enabled"].is_present_in_payload is True
    assert field_states["club_generation.capacity_ranges"].value["tiny"] == [12, 24]
    assert field_states["club_generation.capacity_ranges"].linked_value["tiny"] == 0.5


def test_get_payload_value_returns_none_for_missing_path():
    payload = default_config_payload()

    assert get_payload_value(payload, "simulation.not_real") is None
    assert get_payload_value(payload, "not_real") is None


def test_hidden_performance_bias_defaults_are_editor_scaffolded():
    payload = default_config_payload()
    hidden_bias = payload["hidden_performance_bias"]

    assert hidden_bias["enabled"] is False
    assert hidden_bias["debug_enabled"] is False
    assert hidden_bias["total_max_rating_points"] == 50
    assert hidden_bias["age_advantage"]["enabled"] is True
    assert hidden_bias["fatigue"]["enabled"] is True
    assert hidden_bias["regional_strength"]["enabled"] is True
    assert hidden_bias["partnership_affinity"]["enabled"] is True
    assert hidden_bias["experience"]["enabled"] is True

    sections = build_config_editor_sections(payload)
    hidden_section = next(
        section
        for section in sections
        if section.definition.id == "synthetic_hidden_performance_bias"
    )
    paths = {field.definition.path for field in hidden_section.fields}

    assert "hidden_performance_bias.enabled" in paths
    assert "hidden_performance_bias.regional_strength.map" in paths
    assert "hidden_performance_bias.experience.close_match_multiplier" in paths


def test_runtime_instrumentation_fields_are_checkbox_scaffolded():
    payload = default_config_payload()
    sections = build_config_editor_sections(payload)
    instrumentation_section = next(
        section
        for section in sections
        if section.definition.id == "synthetic_runtime_instrumentation"
    )

    fields = {field.definition.path: field for field in instrumentation_section.fields}
    assert set(fields) == {
        "instrumentation.players_enabled",
        "instrumentation.club_memberships_enabled",
        "instrumentation.teams_enabled",
        "instrumentation.matches_enabled",
        "instrumentation.ratings_enabled",
    }
    assert all(field.definition.control_type == "checkbox" for field in fields.values())
    assert all(field.value is True for field in fields.values())


def test_missing_runtime_instrumentation_checkboxes_display_defaults():
    payload = default_config_payload()
    payload.pop("instrumentation")

    sections = build_config_editor_sections(payload)
    instrumentation_section = next(
        section
        for section in sections
        if section.definition.id == "synthetic_runtime_instrumentation"
    )

    for field in instrumentation_section.fields:
        assert field.value is True
        assert field.is_present_in_payload is False
        assert field.is_default_value is True


def test_hidden_performance_bias_bounded_tuning_fields_render_as_sliders():
    fields = {field.path: field for field in CONFIG_EDITOR_FIELDS}
    slider_paths = {
        "hidden_performance_bias.total_max_rating_points",
        "hidden_performance_bias.age_advantage.max_rating_points",
        "hidden_performance_bias.age_advantage.points_per_year_gap",
        "hidden_performance_bias.age_advantage.close_match_multiplier",
        "hidden_performance_bias.age_advantage.close_match_competitiveness_threshold",
        "hidden_performance_bias.fatigue.points_per_recent_game",
        "hidden_performance_bias.fatigue.max_rating_penalty",
        "hidden_performance_bias.regional_strength.max_rating_points",
        "hidden_performance_bias.partnership_affinity.same_club_bonus",
        "hidden_performance_bias.partnership_affinity.matches_together_bonus_1",
        "hidden_performance_bias.partnership_affinity.matches_together_bonus_2",
        "hidden_performance_bias.partnership_affinity.recent_matches_bonus",
        "hidden_performance_bias.partnership_affinity.max_rating_points",
        "hidden_performance_bias.experience.max_rating_points",
        "hidden_performance_bias.experience.log_multiplier",
        "hidden_performance_bias.experience.close_match_multiplier",
        "hidden_performance_bias.experience.close_match_competitiveness_threshold",
    }

    for path in slider_paths:
        assert fields[path].control_type == "slider"
        assert fields[path].min_value is not None
        assert fields[path].max_value is not None
        assert fields[path].step is not None

    assert fields["hidden_performance_bias.fatigue.window_days"].control_type == "integer"
    assert (
        fields["hidden_performance_bias.fatigue.recovery_days_threshold"].control_type
        == "integer"
    )
    assert (
        fields[
            "hidden_performance_bias.partnership_affinity.matches_together_threshold_1"
        ].control_type
        == "integer"
    )
    assert fields["hidden_performance_bias.regional_strength.map"].control_type == "json"
