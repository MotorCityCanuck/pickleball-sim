"""Validation helpers for config fields consumed by live seed and generation code."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping

from app.exports.data_quality.config import (
    SUPPORTED_DATA_QUALITY_LEVELS,
    SUPPORTED_ISSUE_TYPES,
)
from app.generators.club_memberships import ClubMembershipGenerationConfig
from app.generators.matches import MatchGenerationConfig
from app.generators.players import PlayerGenerationConfig
from app.generators.ratings import RatingUpdateConfig
from app.generators.teams import TeamFormationConfig
from app.seed_data_ingest import SUPPORTED_RAW_DATASETS
from app.seed_data_normalize.pickleball_clubs import ClubGenerationConfig


MAX_LIVE_HISTORICAL_BATCH_COUNT = 36


@dataclass(frozen=True)
class ConfigValidationIssue:
    """One validation issue that may optionally map back to a config field path."""

    path: str | None
    message: str

    @property
    def error_text(self) -> str:
        """Return a human-readable error string."""
        if self.path is None:
            return self.message
        if self.message.startswith(self.path):
            return self.message
        leaf_name = self.path.rsplit(".", 1)[-1]
        if self.message.startswith(f"{leaf_name}.") and "." in self.path:
            return f"{self.path.rsplit('.', 1)[0]}.{self.message}"
        return f"{self.path} {self.message}"


def validate_live_config_payload(
    payload: Mapping[str, Any],
) -> tuple[ConfigValidationIssue, ...]:
    """Validate config values against the modules that consume them today."""
    issues: list[ConfigValidationIssue] = []
    issues.extend(_validate_supported_datasets(payload))
    issues.extend(_validate_first_batch_month(payload))
    issues.extend(_validate_historical_batch_count(payload))
    issues.extend(_validate_instrumentation(payload))
    issues.extend(_validate_data_quality_injection(payload))
    issues.extend(_validate_hidden_performance_bias(payload))

    module_validators = (
        ("club_generation", ClubGenerationConfig.from_payload),
        ("player_generation", PlayerGenerationConfig.from_payload),
        ("club_memberships", ClubMembershipGenerationConfig.from_payload),
        ("team_formation", TeamFormationConfig.from_payload),
        ("matches", MatchGenerationConfig.from_payload),
        ("ratings", RatingUpdateConfig.from_payload),
    )
    for label, validator in module_validators:
        try:
            validator(dict(payload))
        except (ArithmeticError, KeyError, TypeError, ValueError) as exc:
            issue = _issue_from_module_error(label, str(exc))
            if _is_duplicate_hidden_bias_match_issue(label, issue, issues):
                continue
            issues.append(issue)

    return tuple(issues)


def _validate_instrumentation(
    payload: Mapping[str, Any],
) -> list[ConfigValidationIssue]:
    instrumentation = payload.get("instrumentation")
    if not isinstance(instrumentation, Mapping):
        return []

    issues: list[ConfigValidationIssue] = []
    for key in (
        "players_enabled",
        "club_memberships_enabled",
        "teams_enabled",
        "matches_enabled",
        "ratings_enabled",
    ):
        issues.extend(
            _validate_bool(
                instrumentation,
                key,
                f"instrumentation.{key}",
            )
        )
    return issues


def _validate_supported_datasets(
    payload: Mapping[str, Any],
) -> list[ConfigValidationIssue]:
    raw_seed_data = payload.get("raw_seed_data")
    if not isinstance(raw_seed_data, Mapping):
        return []

    configured = raw_seed_data.get("supported_datasets")
    if configured is None:
        return []
    if not isinstance(configured, (list, tuple)):
        return [
            ConfigValidationIssue(
                path="raw_seed_data.supported_datasets",
                message="must be a list of dataset names.",
            )
        ]

    issues: list[ConfigValidationIssue] = []
    invalid_types = [item for item in configured if not isinstance(item, str)]
    if invalid_types:
        issues.append(
            ConfigValidationIssue(
                path="raw_seed_data.supported_datasets",
                message="must contain only strings.",
            )
        )

    dataset_names = [item for item in configured if isinstance(item, str)]
    duplicates = sorted({name for name in dataset_names if dataset_names.count(name) > 1})
    if duplicates:
        issues.append(
            ConfigValidationIssue(
                path="raw_seed_data.supported_datasets",
                message="contains duplicates: " + ", ".join(duplicates) + ".",
            )
        )

    unknown = sorted(set(dataset_names) - SUPPORTED_RAW_DATASETS)
    if unknown:
        issues.append(
            ConfigValidationIssue(
                path="raw_seed_data.supported_datasets",
                message="contains unsupported datasets: " + ", ".join(unknown) + ".",
            )
        )

    return issues


def _validate_first_batch_month(payload: Mapping[str, Any]) -> list[ConfigValidationIssue]:
    simulation = payload.get("simulation")
    if not isinstance(simulation, Mapping):
        return []

    value = simulation.get("first_batch_month")
    if value in (None, ""):
        return []
    if isinstance(value, date):
        return []
    if not isinstance(value, str):
        return [
            ConfigValidationIssue(
                path="simulation.first_batch_month",
                message="must be an ISO date string.",
            )
        ]

    try:
        date.fromisoformat(value)
    except ValueError:
        return [
            ConfigValidationIssue(
                path="simulation.first_batch_month",
                message="must be a valid ISO date string.",
            )
        ]
    return []


def _validate_historical_batch_count(
    payload: Mapping[str, Any],
) -> list[ConfigValidationIssue]:
    simulation = payload.get("simulation")
    if not isinstance(simulation, Mapping):
        return []

    value = simulation.get("historical_batch_count")
    if isinstance(value, bool) or not isinstance(value, int):
        return []
    if value > MAX_LIVE_HISTORICAL_BATCH_COUNT:
        return [
            ConfigValidationIssue(
                path="simulation.historical_batch_count",
                message=(
                    "must be <= "
                    f"{MAX_LIVE_HISTORICAL_BATCH_COUNT} for the live monthly pipeline."
                ),
            )
        ]
    return []


def _validate_hidden_performance_bias(
    payload: Mapping[str, Any],
) -> list[ConfigValidationIssue]:
    section = payload.get("hidden_performance_bias")
    if section is None:
        return []
    if not isinstance(section, Mapping):
        return [
            ConfigValidationIssue(
                path="hidden_performance_bias",
                message="must be an object.",
            )
        ]

    issues: list[ConfigValidationIssue] = []
    issues.extend(_validate_bool(section, "enabled", "hidden_performance_bias.enabled"))
    issues.extend(
        _validate_bool(
            section,
            "debug_enabled",
            "hidden_performance_bias.debug_enabled",
        )
    )
    issues.extend(
        _validate_nonnegative_number(
            section,
            "total_max_rating_points",
            "hidden_performance_bias.total_max_rating_points",
        )
    )

    issues.extend(
        _validate_hidden_factor(
            section,
            "age_advantage",
            numeric_fields=(
                "max_rating_points",
                "points_per_year_gap",
                "close_match_multiplier",
            ),
            probability_fields=("close_match_competitiveness_threshold",),
        )
    )
    issues.extend(
        _validate_hidden_factor(
            section,
            "fatigue",
            numeric_fields=("points_per_recent_game", "max_rating_penalty"),
            integer_fields=("window_days", "recovery_days_threshold"),
        )
    )
    issues.extend(
        _validate_hidden_factor(
            section,
            "regional_strength",
            numeric_fields=("max_rating_points",),
        )
    )
    issues.extend(_validate_regional_strength_map(section))
    issues.extend(
        _validate_hidden_factor(
            section,
            "partnership_affinity",
            numeric_fields=(
                "same_club_bonus",
                "matches_together_bonus_1",
                "matches_together_bonus_2",
                "recent_matches_bonus",
                "new_team_penalty",
                "max_rating_points",
            ),
            integer_fields=(
                "matches_together_threshold_1",
                "matches_together_threshold_2",
            ),
            signed_numeric_fields=(
                "same_club_bonus",
                "matches_together_bonus_1",
                "matches_together_bonus_2",
                "recent_matches_bonus",
                "new_team_penalty",
            ),
        )
    )
    issues.extend(_validate_partnership_threshold_order(section))
    issues.extend(
        _validate_hidden_factor(
            section,
            "experience",
            numeric_fields=(
                "max_rating_points",
                "log_multiplier",
                "close_match_multiplier",
            ),
            probability_fields=("close_match_competitiveness_threshold",),
        )
    )

    return issues


def _validate_data_quality_injection(
    payload: Mapping[str, Any],
) -> list[ConfigValidationIssue]:
    section = payload.get("data_quality_injection")
    if section is None:
        return []
    if not isinstance(section, Mapping):
        return [
            ConfigValidationIssue(
                path="data_quality_injection",
                message="must be an object.",
            )
        ]

    issues: list[ConfigValidationIssue] = []
    issues.extend(
        _validate_bool(
            section,
            "enabled",
            "data_quality_injection.enabled",
        )
    )
    issues.extend(
        _validate_bool(
            section,
            "write_instructor_manifest",
            "data_quality_injection.write_instructor_manifest",
        )
    )
    issues.extend(
        _validate_bool(
            section,
            "write_student_visible_quality_summary",
            "data_quality_injection.write_student_visible_quality_summary",
        )
    )

    level = section.get("level")
    if level is not None and level not in SUPPORTED_DATA_QUALITY_LEVELS:
        issues.append(
            ConfigValidationIssue(
                path="data_quality_injection.level",
                message=(
                    "must be one of: "
                    + ", ".join(SUPPORTED_DATA_QUALITY_LEVELS)
                    + "."
                ),
            )
        )

    table_rules = section.get("table_rules")
    if table_rules is not None and not isinstance(table_rules, Mapping):
        issues.append(
            ConfigValidationIssue(
                path="data_quality_injection.table_rules",
                message="must be an object mapping table names to rules.",
            )
        )
    elif isinstance(table_rules, Mapping):
        for table_name, rule in table_rules.items():
            if not isinstance(rule, Mapping):
                issues.append(
                    ConfigValidationIssue(
                        path=f"data_quality_injection.table_rules.{table_name}",
                        message="must be an object.",
                    )
                )
                continue
            issue_types = rule.get("allowed_issue_types")
            if issue_types is None:
                continue
            if not isinstance(issue_types, (list, tuple)):
                issues.append(
                    ConfigValidationIssue(
                        path=(
                            "data_quality_injection.table_rules."
                            f"{table_name}.allowed_issue_types"
                        ),
                        message="must be a list of strings.",
                    )
                )
                continue
            unknown = sorted(
                {
                    str(issue_type)
                    for issue_type in issue_types
                    if issue_type not in SUPPORTED_ISSUE_TYPES
                }
            )
            if unknown:
                issues.append(
                    ConfigValidationIssue(
                        path=(
                            "data_quality_injection.table_rules."
                            f"{table_name}.allowed_issue_types"
                        ),
                        message="contains unsupported issue types: " + ", ".join(unknown) + ".",
                    )
                )

    return issues


def _validate_hidden_factor(
    parent: Mapping[str, Any],
    factor_name: str,
    *,
    numeric_fields: tuple[str, ...] = (),
    integer_fields: tuple[str, ...] = (),
    probability_fields: tuple[str, ...] = (),
    signed_numeric_fields: tuple[str, ...] = (),
) -> list[ConfigValidationIssue]:
    value = parent.get(factor_name)
    path_prefix = f"hidden_performance_bias.{factor_name}"
    if value is None:
        return []
    if not isinstance(value, Mapping):
        return [
            ConfigValidationIssue(
                path=path_prefix,
                message="must be an object.",
            )
        ]

    issues: list[ConfigValidationIssue] = []
    issues.extend(_validate_bool(value, "enabled", f"{path_prefix}.enabled"))
    signed_fields = set(signed_numeric_fields)
    for field in numeric_fields:
        if field in signed_fields:
            issues.extend(_validate_number(value, field, f"{path_prefix}.{field}"))
        else:
            issues.extend(
                _validate_nonnegative_number(value, field, f"{path_prefix}.{field}")
            )
    for field in integer_fields:
        issues.extend(
            _validate_nonnegative_integer(value, field, f"{path_prefix}.{field}")
        )
    for field in probability_fields:
        issues.extend(_validate_probability(value, field, f"{path_prefix}.{field}"))
    return issues


def _validate_regional_strength_map(
    section: Mapping[str, Any],
) -> list[ConfigValidationIssue]:
    regional_strength = section.get("regional_strength")
    if not isinstance(regional_strength, Mapping) or "map" not in regional_strength:
        return []

    strength_map = regional_strength.get("map")
    path = "hidden_performance_bias.regional_strength.map"
    if not isinstance(strength_map, Mapping):
        return [ConfigValidationIssue(path=path, message="must be an object.")]

    invalid_keys = [key for key in strength_map if not isinstance(key, str)]
    if invalid_keys:
        return [
            ConfigValidationIssue(
                path=path,
                message="must use string region names.",
            )
        ]

    invalid_values = [
        key
        for key, value in strength_map.items()
        if isinstance(value, bool) or not isinstance(value, (int, float))
    ]
    if invalid_values:
        return [
            ConfigValidationIssue(
                path=path,
                message="must contain only numeric rating-point values.",
            )
        ]
    return []


def _validate_partnership_threshold_order(
    section: Mapping[str, Any],
) -> list[ConfigValidationIssue]:
    partnership = section.get("partnership_affinity")
    if not isinstance(partnership, Mapping):
        return []

    threshold_1 = partnership.get("matches_together_threshold_1")
    threshold_2 = partnership.get("matches_together_threshold_2")
    if (
        isinstance(threshold_1, int)
        and not isinstance(threshold_1, bool)
        and isinstance(threshold_2, int)
        and not isinstance(threshold_2, bool)
        and threshold_2 < threshold_1
    ):
        return [
            ConfigValidationIssue(
                path=(
                    "hidden_performance_bias.partnership_affinity."
                    "matches_together_threshold_2"
                ),
                message="must be greater than or equal to matches_together_threshold_1.",
            )
        ]
    return []


def _validate_bool(
    mapping: Mapping[str, Any],
    key: str,
    path: str,
) -> list[ConfigValidationIssue]:
    if key not in mapping or isinstance(mapping.get(key), bool):
        return []
    return [ConfigValidationIssue(path=path, message="must be a boolean.")]


def _validate_number(
    mapping: Mapping[str, Any],
    key: str,
    path: str,
) -> list[ConfigValidationIssue]:
    value = mapping.get(key)
    if key not in mapping or (
        not isinstance(value, bool) and isinstance(value, (int, float))
    ):
        return []
    return [ConfigValidationIssue(path=path, message="must be a number.")]


def _validate_nonnegative_number(
    mapping: Mapping[str, Any],
    key: str,
    path: str,
) -> list[ConfigValidationIssue]:
    issues = _validate_number(mapping, key, path)
    if issues or key not in mapping:
        return issues
    if mapping[key] < 0:
        return [ConfigValidationIssue(path=path, message="must be non-negative.")]
    return []


def _validate_nonnegative_integer(
    mapping: Mapping[str, Any],
    key: str,
    path: str,
) -> list[ConfigValidationIssue]:
    value = mapping.get(key)
    if key not in mapping:
        return []
    if isinstance(value, bool) or not isinstance(value, int):
        return [ConfigValidationIssue(path=path, message="must be an integer.")]
    if value < 0:
        return [ConfigValidationIssue(path=path, message="must be non-negative.")]
    return []


def _validate_probability(
    mapping: Mapping[str, Any],
    key: str,
    path: str,
) -> list[ConfigValidationIssue]:
    value = mapping.get(key)
    if key not in mapping:
        return []
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return [ConfigValidationIssue(path=path, message="must be a number.")]
    if value < 0 or value > 1:
        return [ConfigValidationIssue(path=path, message="must be between 0 and 1.")]
    return []


def _issue_from_module_error(label: str, message: str) -> ConfigValidationIssue:
    path = _field_path_for_module_error(label, message)
    return ConfigValidationIssue(path=path, message=message)


def _is_duplicate_hidden_bias_match_issue(
    label: str,
    issue: ConfigValidationIssue,
    existing_issues: list[ConfigValidationIssue],
) -> bool:
    if label != "matches":
        return False
    has_hidden_issue = any(
        existing.path is not None
        and existing.path.startswith("hidden_performance_bias")
        for existing in existing_issues
    )
    if not has_hidden_issue:
        return False
    return issue.path is None or issue.path.startswith("hidden_performance_bias")


def _field_path_for_module_error(label: str, message: str) -> str | None:
    mapping = MODULE_ERROR_PATH_MAP.get(label, ())
    for needle, path in mapping:
        if needle in message:
            return path
    return None


MODULE_ERROR_PATH_MAP: dict[str, tuple[tuple[str, str], ...]] = {
    "club_generation": (
        ("club_size_distribution", "club_generation.capacity_ranges"),
        ("ratio", "club_generation.indoor_court_ratios"),
        ("capacity", "club_generation.capacity_ranges"),
        ("court", "club_generation.court_ranges"),
        ("range", "club_generation.capacity_ranges"),
    ),
    "player_generation": (
        ("player_count", "player_generation.player_count"),
        (
            "monthly_player_growth_rate",
            "player_generation.monthly_player_growth_rate",
        ),
        (
            "monthly_player_inactivation_rate",
            "player_generation.monthly_player_inactivation_rate",
        ),
        ("age bounds", "player_generation.age_min"),
        (
            "minimum_registration_age",
            "player_generation.minimum_registration_age",
        ),
        ("elite_tail_rate", "ratings.initial_rating_elite_tail_rate"),
        ("elite rating bounds", "ratings.initial_rating_elite_min"),
        ("initial_confidence_score", "confidence.initial_confidence_score"),
        ("gender_weights", "player_generation.gender_weights"),
        ("dominant_hand_weights", "player_generation.dominant_hand_weights"),
        ("player_status_weights", "player_generation.player_status_weights"),
        ("probability weights", "player_generation.age_distribution"),
    ),
    "club_memberships": (
        ("unaffiliated_player_rate", "club_generation.unaffiliated_player_rate"),
        ("multi_club_membership_rate", "club_generation.multi_club_membership_rate"),
        (
            "secondary_membership_same_region_rate",
            "club_generation.secondary_membership_same_region_rate",
        ),
        (
            "min_club_memberships_per_affiliated_player",
            "club_generation.min_club_memberships_per_affiliated_player",
        ),
        (
            "max_club_memberships_per_player",
            "club_generation.max_club_memberships_per_player",
        ),
    ),
    "team_formation": (
        ("target_team_count", "team_formation.target_team_count"),
        ("player_team_participation_rate", "team_formation.player_team_participation_rate"),
        ("multi_team_player_rate", "team_formation.multi_team_player_rate"),
        ("max_active_teams_per_player", "team_formation.max_active_teams_per_player"),
        ("same_club_team_rate", "team_formation.same_club_team_rate"),
        ("same_region_team_rate", "team_formation.same_region_team_rate"),
        ("rating gap settings", "team_formation.rating_gap_mean"),
        ("team_type_weights", "team_formation.team_type_weights"),
        ("competitive_team_rate", "team_formation.competitive_team_rate"),
        (
            "team_persistence_probability_recreational",
            "team_formation.team_persistence_probability_recreational",
        ),
        (
            "team_persistence_probability_competitive",
            "team_formation.team_persistence_probability_competitive",
        ),
        ("team_chemistry_weight", "team_formation.team_chemistry_weight"),
        ("team_skill_balance_weight", "team_formation.team_skill_balance_weight"),
        ("team_club_proximity_weight", "team_formation.team_club_proximity_weight"),
        ("team_region_proximity_weight", "team_formation.team_region_proximity_weight"),
        (
            "team_prior_partnership_weight",
            "team_formation.team_prior_partnership_weight",
        ),
        ("team_noise_factor", "team_formation.team_noise_factor"),
    ),
    "matches": (
        (
            "monthly_matches_per_active_player_mean",
            "match_scheduling.monthly_matches_per_active_player_mean",
        ),
        (
            "monthly_matches_per_active_player_std_dev",
            "match_scheduling.monthly_matches_per_active_player_std_dev",
        ),
        (
            "match_volume_noise_factor",
            "match_scheduling.match_volume_noise_factor",
        ),
        ("max_daily_matches_per_team", "match_scheduling.max_daily_matches_per_team"),
        ("match_types.weights", "match_types.weights"),
        ("match_types.class_by_type", "match_types.class_by_type"),
        ("rating_band_width.", "matchmaking.rating_band_width"),
        ("matchmaking_noise_factor", "matchmaking.matchmaking_noise_factor"),
        (
            "rematch_penalty_window_days",
            "matchmaking.rematch_penalty_window_days",
        ),
        ("locality_weight", "matchmaking.locality_weight"),
        (
            "pairing_source_weights_by_class",
            "matchmaking.pairing_source_weights_by_class",
        ),
        (
            "pairing_source_overrides_by_type",
            "matchmaking.pairing_source_overrides_by_type",
        ),
        ("games_per_match.", "games_and_scores.games_per_match"),
        ("game_target_score", "games_and_scores.game_target_score"),
        ("win_by_two_extension_rate", "games_and_scores.win_by_two_extension_rate"),
        ("score_noise_std_dev", "games_and_scores.score_noise_std_dev"),
        ("upset_probability_boost", "games_and_scores.upset_probability_boost"),
        ("saturday_weight", "match_scheduling.saturday_weight"),
        ("sunday_weight", "match_scheduling.sunday_weight"),
        ("friday_weight", "match_scheduling.friday_weight"),
        ("weekday_evening_weight", "match_scheduling.weekday_evening_weight"),
        ("matches_per_team_per_month", "match_scheduling.matches_per_team_per_month"),
    ),
    "ratings": (
        ("rating bounds are invalid", "ratings.rating_min"),
        ("k_factor_new_player", "ratings.k_factor_new_player"),
        ("k_factor_established", "ratings.k_factor_established"),
        ("k_factor_elite", "ratings.k_factor_elite"),
        ("confidence_max", "confidence.confidence_max"),
        ("probability must be between 0 and 1", "confidence.confidence_increment_per_match"),
    ),
}
