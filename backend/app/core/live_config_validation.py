"""Validation helpers for config fields consumed by live seed and generation code."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping

from app.generators.club_memberships import ClubMembershipGenerationConfig
from app.generators.matches import MatchGenerationConfig
from app.generators.players import PlayerGenerationConfig
from app.generators.ratings import RatingUpdateConfig
from app.generators.teams import TeamFormationConfig
from app.seed_data_ingest import SUPPORTED_RAW_DATASETS
from app.seed_data_normalize.pickleball_clubs import ClubGenerationConfig


MAX_LIVE_HISTORICAL_BATCH_COUNT = 12


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
            issues.append(_issue_from_module_error(label, str(exc)))

    return tuple(issues)


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


def _issue_from_module_error(label: str, message: str) -> ConfigValidationIssue:
    path = _field_path_for_module_error(label, message)
    return ConfigValidationIssue(path=path, message=message)


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
        (
            "monthly_team_dissolution_rate",
            "team_formation.monthly_team_dissolution_rate",
        ),
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
        ("rating_band_width.", "matchmaking.rating_band_width"),
        ("matchmaking_noise_factor", "matchmaking.matchmaking_noise_factor"),
        (
            "rematch_penalty_window_days",
            "matchmaking.rematch_penalty_window_days",
        ),
        ("locality_weight", "matchmaking.locality_weight"),
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
