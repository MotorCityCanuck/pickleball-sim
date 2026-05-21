"""Metadata scaffold for a future schema-driven configuration editor."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

from .default_configuration import default_config_payload


ConfigEditorScope = Literal["seed", "synthetic"]
ConfigEditorControlType = Literal[
    "text",
    "date",
    "integer",
    "decimal",
    "checkbox",
    "select",
    "slider",
    "string_list",
    "multi_select",
    "weight_table",
    "range_table",
    "json",
]
ConfigEditorComplexity = Literal["basic", "advanced"]


@dataclass(frozen=True)
class ConfigEditorOption:
    """One allowed value for a select-style field."""

    value: str
    label: str
    description: str | None = None


@dataclass(frozen=True)
class ConfigEditorFieldDefinition:
    """Metadata for one editable configuration field."""

    path: str
    label: str
    control_type: ConfigEditorControlType
    scope: ConfigEditorScope
    description: str
    default_value: Any
    required: bool = False
    basic_or_advanced: ConfigEditorComplexity = "basic"
    min_value: float | int | None = None
    max_value: float | int | None = None
    step: float | int | None = None
    options: tuple[ConfigEditorOption, ...] = ()


@dataclass(frozen=True)
class ConfigEditorSectionDefinition:
    """One curated form section in the future editor."""

    id: str
    scope: ConfigEditorScope
    title: str
    description: str
    field_paths: tuple[str, ...]


@dataclass(frozen=True)
class ConfigEditorFieldState:
    """Resolved field metadata with the current payload value attached."""

    definition: ConfigEditorFieldDefinition
    value: Any
    is_default_value: bool
    is_present_in_payload: bool


@dataclass(frozen=True)
class ConfigEditorSectionState:
    """Resolved section metadata with attached field states."""

    definition: ConfigEditorSectionDefinition
    fields: tuple[ConfigEditorFieldState, ...]


def get_payload_value(payload: Mapping[str, Any] | None, path: str) -> Any:
    """Resolve a dotted path from a payload mapping."""
    if not isinstance(payload, Mapping):
        return None

    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _path_default(path: str) -> Any:
    return get_payload_value(default_config_payload(), path)


CONFIG_EDITOR_FIELDS: tuple[ConfigEditorFieldDefinition, ...] = (
    ConfigEditorFieldDefinition(
        path="raw_seed_data.supported_datasets",
        label="Supported raw seed datasets",
        control_type="multi_select",
        scope="seed",
        description="Datasets eligible for ingest and refresh workflows.",
        default_value=_path_default("raw_seed_data.supported_datasets"),
        required=True,
        options=tuple(
            ConfigEditorOption(value=value, label=value.replace("_", " "))
            for value in _path_default("raw_seed_data.supported_datasets")
        ),
    ),
    ConfigEditorFieldDefinition(
        path="club_generation.capacity_ranges",
        label="Club capacity ranges",
        control_type="range_table",
        scope="seed",
        description="Min/max member capacity ranges by club size bucket.",
        default_value=_path_default("club_generation.capacity_ranges"),
    ),
    ConfigEditorFieldDefinition(
        path="club_generation.court_ranges",
        label="Club court ranges",
        control_type="range_table",
        scope="seed",
        description="Min/max court-count ranges by club size bucket.",
        default_value=_path_default("club_generation.court_ranges"),
        basic_or_advanced="advanced",
    ),
    ConfigEditorFieldDefinition(
        path="club_generation.indoor_court_ratios",
        label="Indoor court ratios",
        control_type="weight_table",
        scope="seed",
        description="Indoor-court share by club type for generated club facilities.",
        default_value=_path_default("club_generation.indoor_court_ratios"),
        basic_or_advanced="advanced",
    ),
    ConfigEditorFieldDefinition(
        path="club_generation.unaffiliated_player_rate",
        label="Unaffiliated player rate",
        control_type="slider",
        scope="seed",
        description="Share of generated players without a club membership.",
        default_value=_path_default("club_generation.unaffiliated_player_rate"),
        min_value=0.0,
        max_value=1.0,
        step=0.01,
    ),
    ConfigEditorFieldDefinition(
        path="club_generation.cross_region_assignment_enabled",
        label="Allow cross-region club assignment",
        control_type="checkbox",
        scope="seed",
        description="Whether players may join clubs outside their assigned region.",
        default_value=_path_default("club_generation.cross_region_assignment_enabled"),
        basic_or_advanced="advanced",
    ),
    ConfigEditorFieldDefinition(
        path="club_generation.multi_club_membership_rate",
        label="Multi-club membership rate",
        control_type="slider",
        scope="seed",
        description="Share of affiliated players who receive multiple club memberships.",
        default_value=_path_default("club_generation.multi_club_membership_rate"),
        basic_or_advanced="advanced",
        min_value=0.0,
        max_value=1.0,
        step=0.01,
    ),
    ConfigEditorFieldDefinition(
        path="club_generation.min_club_memberships_per_affiliated_player",
        label="Minimum club memberships per affiliated player",
        control_type="integer",
        scope="seed",
        description="Minimum memberships assigned to a player who is not unaffiliated.",
        default_value=_path_default("club_generation.min_club_memberships_per_affiliated_player"),
        basic_or_advanced="advanced",
        min_value=1,
        step=1,
    ),
    ConfigEditorFieldDefinition(
        path="club_generation.max_club_memberships_per_player",
        label="Maximum club memberships per player",
        control_type="integer",
        scope="seed",
        description="Upper bound on club memberships assigned to one player.",
        default_value=_path_default("club_generation.max_club_memberships_per_player"),
        basic_or_advanced="advanced",
        min_value=1,
        step=1,
    ),
    ConfigEditorFieldDefinition(
        path="club_generation.secondary_membership_same_region_rate",
        label="Secondary membership same-region rate",
        control_type="slider",
        scope="seed",
        description="Probability that a secondary club membership stays in the player's home region.",
        default_value=_path_default("club_generation.secondary_membership_same_region_rate"),
        basic_or_advanced="advanced",
        min_value=0.0,
        max_value=1.0,
        step=0.01,
    ),
    ConfigEditorFieldDefinition(
        path="simulation.simulation_version",
        label="Simulation version",
        control_type="text",
        scope="synthetic",
        description="Version label recorded on generation runs.",
        default_value=_path_default("simulation.simulation_version"),
    ),
    ConfigEditorFieldDefinition(
        path="simulation.master_seed",
        label="Master seed",
        control_type="integer",
        scope="synthetic",
        description="Seed used for deterministic generation behavior.",
        default_value=_path_default("simulation.master_seed"),
        required=True,
        min_value=0,
        step=1,
    ),
    ConfigEditorFieldDefinition(
        path="simulation.target_total_players",
        label="Target total players",
        control_type="integer",
        scope="synthetic",
        description="Total player count used for the generated workload.",
        default_value=_path_default("simulation.target_total_players"),
        required=True,
        min_value=1,
        step=1,
    ),
    ConfigEditorFieldDefinition(
        path="simulation.historical_batch_count",
        label="Historical batch count",
        control_type="integer",
        scope="synthetic",
        description="Number of monthly historical batches to generate.",
        default_value=_path_default("simulation.historical_batch_count"),
        required=True,
        min_value=1,
        step=1,
    ),
    ConfigEditorFieldDefinition(
        path="simulation.first_batch_month",
        label="First batch month",
        control_type="date",
        scope="synthetic",
        description="First generated month in ISO date format.",
        default_value=_path_default("simulation.first_batch_month"),
        required=True,
    ),
    ConfigEditorFieldDefinition(
        path="player_generation.player_count",
        label="Initial player count",
        control_type="integer",
        scope="synthetic",
        description="Initial player population loaded into the first batch.",
        default_value=_path_default("player_generation.player_count"),
        min_value=1,
        step=1,
    ),
    ConfigEditorFieldDefinition(
        path="player_generation.age_min",
        label="Minimum player age",
        control_type="integer",
        scope="synthetic",
        description="Lower bound for generated player ages.",
        default_value=_path_default("player_generation.age_min"),
        min_value=0,
        step=1,
    ),
    ConfigEditorFieldDefinition(
        path="player_generation.age_max",
        label="Maximum player age",
        control_type="integer",
        scope="synthetic",
        description="Upper bound for generated player ages.",
        default_value=_path_default("player_generation.age_max"),
        min_value=0,
        step=1,
    ),
    ConfigEditorFieldDefinition(
        path="player_generation.age_distribution",
        label="Age distribution",
        control_type="weight_table",
        scope="synthetic",
        description="Weight distribution across age buckets.",
        default_value=_path_default("player_generation.age_distribution"),
    ),
    ConfigEditorFieldDefinition(
        path="player_generation.gender_weights",
        label="Gender weights",
        control_type="weight_table",
        scope="synthetic",
        description="Sampling weights for generated player genders.",
        default_value=_path_default("player_generation.gender_weights"),
    ),
    ConfigEditorFieldDefinition(
        path="player_generation.dominant_hand_weights",
        label="Dominant hand weights",
        control_type="weight_table",
        scope="synthetic",
        description="Sampling weights for generated dominant-hand values.",
        default_value=_path_default("player_generation.dominant_hand_weights"),
        basic_or_advanced="advanced",
    ),
    ConfigEditorFieldDefinition(
        path="player_generation.player_status_weights",
        label="Player status weights",
        control_type="weight_table",
        scope="synthetic",
        description="Sampling weights for generated initial player-status values.",
        default_value=_path_default("player_generation.player_status_weights"),
        basic_or_advanced="advanced",
    ),
    ConfigEditorFieldDefinition(
        path="player_generation.initial_skill_seed.mean",
        label="Initial skill mean",
        control_type="decimal",
        scope="synthetic",
        description="Mean used when sampling each player's latent initial skill seed.",
        default_value=_path_default("player_generation.initial_skill_seed.mean"),
        basic_or_advanced="advanced",
        step=1.0,
    ),
    ConfigEditorFieldDefinition(
        path="player_generation.initial_skill_seed.std_dev",
        label="Initial skill standard deviation",
        control_type="decimal",
        scope="synthetic",
        description="Standard deviation used when sampling each player's latent initial skill seed.",
        default_value=_path_default("player_generation.initial_skill_seed.std_dev"),
        basic_or_advanced="advanced",
        min_value=0.0,
        step=1.0,
    ),
    ConfigEditorFieldDefinition(
        path="player_generation.initial_skill_seed.lower_bias",
        label="Initial skill lower-tail bias",
        control_type="decimal",
        scope="synthetic",
        description="Downward bias applied to the lower tail of initial skill sampling.",
        default_value=_path_default("player_generation.initial_skill_seed.lower_bias"),
        basic_or_advanced="advanced",
        min_value=0.0,
        step=1.0,
    ),
    ConfigEditorFieldDefinition(
        path="player_generation.initial_skill_seed.min",
        label="Initial skill minimum",
        control_type="decimal",
        scope="synthetic",
        description="Minimum allowed latent initial skill seed value.",
        default_value=_path_default("player_generation.initial_skill_seed.min"),
        basic_or_advanced="advanced",
        step=1.0,
    ),
    ConfigEditorFieldDefinition(
        path="player_generation.initial_skill_seed.max",
        label="Initial skill maximum",
        control_type="decimal",
        scope="synthetic",
        description="Maximum allowed latent initial skill seed value.",
        default_value=_path_default("player_generation.initial_skill_seed.max"),
        basic_or_advanced="advanced",
        step=1.0,
    ),
    ConfigEditorFieldDefinition(
        path="team_formation.player_team_participation_rate",
        label="Player team participation rate",
        control_type="slider",
        scope="synthetic",
        description="Share of players expected to belong to active teams.",
        default_value=_path_default("team_formation.player_team_participation_rate"),
        min_value=0.0,
        max_value=1.0,
        step=0.01,
    ),
    ConfigEditorFieldDefinition(
        path="team_formation.target_team_count",
        label="Target team count",
        control_type="integer",
        scope="synthetic",
        description="Optional explicit target team count; leave blank to derive automatically.",
        default_value=_path_default("team_formation.target_team_count"),
        basic_or_advanced="advanced",
        min_value=1,
        step=1,
    ),
    ConfigEditorFieldDefinition(
        path="team_formation.max_active_teams_per_player",
        label="Max active teams per player",
        control_type="integer",
        scope="synthetic",
        description="Upper bound on active teams for players when multiple-team participation is allowed.",
        default_value=_path_default("team_formation.max_active_teams_per_player"),
        basic_or_advanced="advanced",
        min_value=1,
        max_value=5,
        step=1,
    ),
    ConfigEditorFieldDefinition(
        path="team_formation.same_club_team_rate",
        label="Same-club team rate",
        control_type="slider",
        scope="synthetic",
        description="Share of newly formed teams whose partners should share a club when feasible.",
        default_value=_path_default("team_formation.same_club_team_rate"),
        min_value=0.0,
        max_value=1.0,
        step=0.01,
    ),
    ConfigEditorFieldDefinition(
        path="team_formation.same_region_team_rate",
        label="Same-region team rate",
        control_type="slider",
        scope="synthetic",
        description="Share of newly formed teams whose partners should share a region when feasible.",
        default_value=_path_default("team_formation.same_region_team_rate"),
        min_value=0.0,
        max_value=1.0,
        step=0.01,
    ),
    ConfigEditorFieldDefinition(
        path="team_formation.rating_gap_mean",
        label="Rating gap mean",
        control_type="decimal",
        scope="synthetic",
        description="Target average rating gap between prospective team partners.",
        default_value=_path_default("team_formation.rating_gap_mean"),
        min_value=0.0,
        max_value=1000.0,
        step=1.0,
    ),
    ConfigEditorFieldDefinition(
        path="team_formation.rating_gap_std_dev",
        label="Rating gap standard deviation",
        control_type="decimal",
        scope="synthetic",
        description="Variation allowed around the team-partner rating gap target.",
        default_value=_path_default("team_formation.rating_gap_std_dev"),
        min_value=0.0,
        max_value=1000.0,
        step=1.0,
    ),
    ConfigEditorFieldDefinition(
        path="team_formation.rating_gap_max",
        label="Rating gap max",
        control_type="decimal",
        scope="synthetic",
        description="Maximum allowed rating gap between newly formed team partners.",
        default_value=_path_default("team_formation.rating_gap_max"),
        min_value=0.0,
        max_value=2500.0,
        step=1.0,
    ),
    ConfigEditorFieldDefinition(
        path="team_formation.team_type_weights",
        label="Team type weights",
        control_type="weight_table",
        scope="synthetic",
        description="Sampling weights for team types.",
        default_value=_path_default("team_formation.team_type_weights"),
    ),
    ConfigEditorFieldDefinition(
        path="team_formation.team_persistence_probability_recreational",
        label="Recreational team persistence",
        control_type="slider",
        scope="synthetic",
        description="Retention rate for recreational teams across months.",
        default_value=_path_default("team_formation.team_persistence_probability_recreational"),
        basic_or_advanced="advanced",
        min_value=0.3,
        max_value=0.95,
        step=0.01,
    ),
    ConfigEditorFieldDefinition(
        path="team_formation.team_chemistry_weight",
        label="Team chemistry weight",
        control_type="decimal",
        scope="synthetic",
        description="Weight of chemistry in partner scoring decisions.",
        default_value=_path_default("team_formation.team_chemistry_weight"),
        basic_or_advanced="advanced",
        min_value=0.0,
        max_value=1.0,
        step=0.01,
    ),
    ConfigEditorFieldDefinition(
        path="team_formation.team_skill_balance_weight",
        label="Team skill balance weight",
        control_type="decimal",
        scope="synthetic",
        description="Weight of rating balance in partner scoring decisions.",
        default_value=_path_default("team_formation.team_skill_balance_weight"),
        basic_or_advanced="advanced",
        min_value=0.0,
        max_value=1.0,
        step=0.01,
    ),
    ConfigEditorFieldDefinition(
        path="team_formation.team_club_proximity_weight",
        label="Team club proximity weight",
        control_type="decimal",
        scope="synthetic",
        description="Weight of shared-club proximity in partner scoring decisions.",
        default_value=_path_default("team_formation.team_club_proximity_weight"),
        basic_or_advanced="advanced",
        min_value=0.0,
        max_value=1.0,
        step=0.01,
    ),
    ConfigEditorFieldDefinition(
        path="team_formation.team_region_proximity_weight",
        label="Team region proximity weight",
        control_type="decimal",
        scope="synthetic",
        description="Weight of regional proximity in partner scoring decisions.",
        default_value=_path_default("team_formation.team_region_proximity_weight"),
        basic_or_advanced="advanced",
        min_value=0.0,
        max_value=1.0,
        step=0.01,
    ),
    ConfigEditorFieldDefinition(
        path="team_formation.team_noise_factor",
        label="Team noise factor",
        control_type="slider",
        scope="synthetic",
        description="Random variation applied during team-formation decisions.",
        default_value=_path_default("team_formation.team_noise_factor"),
        basic_or_advanced="advanced",
        min_value=0.0,
        max_value=0.5,
        step=0.01,
    ),
    ConfigEditorFieldDefinition(
        path="team_formation.allow_multiple_active_teams_per_scope",
        label="Allow multiple active teams per scope",
        control_type="checkbox",
        scope="synthetic",
        description="Whether players may keep multiple active teams in one scope.",
        default_value=_path_default("team_formation.allow_multiple_active_teams_per_scope"),
        basic_or_advanced="advanced",
    ),
    ConfigEditorFieldDefinition(
        path="match_scheduling.matches_per_team_per_month",
        label="Matches per team per month",
        control_type="decimal",
        scope="synthetic",
        description="Average monthly match load generated for each active team.",
        default_value=_path_default("match_scheduling.matches_per_team_per_month"),
        min_value=0.1,
        step=0.1,
    ),
    ConfigEditorFieldDefinition(
        path="match_scheduling.saturday_weight",
        label="Saturday scheduling weight",
        control_type="decimal",
        scope="synthetic",
        description="Relative preference for scheduling generated matches on Saturdays.",
        default_value=_path_default("match_scheduling.saturday_weight"),
        min_value=0.0,
        step=0.05,
    ),
    ConfigEditorFieldDefinition(
        path="match_scheduling.sunday_weight",
        label="Sunday scheduling weight",
        control_type="decimal",
        scope="synthetic",
        description="Relative preference for scheduling generated matches on Sundays.",
        default_value=_path_default("match_scheduling.sunday_weight"),
        min_value=0.0,
        step=0.05,
    ),
    ConfigEditorFieldDefinition(
        path="match_scheduling.friday_weight",
        label="Friday scheduling weight",
        control_type="decimal",
        scope="synthetic",
        description="Relative preference for scheduling generated matches on Fridays.",
        default_value=_path_default("match_scheduling.friday_weight"),
        min_value=0.0,
        step=0.05,
    ),
    ConfigEditorFieldDefinition(
        path="match_scheduling.weekday_evening_weight",
        label="Weekday evening weight",
        control_type="decimal",
        scope="synthetic",
        description="Relative preference for scheduling generated matches on weekday evenings.",
        default_value=_path_default("match_scheduling.weekday_evening_weight"),
        min_value=0.0,
        step=0.05,
    ),
    ConfigEditorFieldDefinition(
        path="match_scheduling.max_daily_matches_per_team",
        label="Max daily matches per team",
        control_type="integer",
        scope="synthetic",
        description="Hard cap on matches a team may be assigned on the same date.",
        default_value=_path_default("match_scheduling.max_daily_matches_per_team"),
        min_value=1,
        step=1,
    ),
    ConfigEditorFieldDefinition(
        path="match_types.weights",
        label="Match type weights",
        control_type="weight_table",
        scope="synthetic",
        description="Sampling weights for generated match types.",
        default_value=_path_default("match_types.weights"),
    ),
    ConfigEditorFieldDefinition(
        path="matchmaking.rating_band_width",
        label="Rating band widths",
        control_type="json",
        scope="synthetic",
        description="Rating band widths by match competitiveness mode.",
        default_value=_path_default("matchmaking.rating_band_width"),
        basic_or_advanced="advanced",
    ),
    ConfigEditorFieldDefinition(
        path="matchmaking.matchmaking_noise_factor",
        label="Matchmaking noise factor",
        control_type="slider",
        scope="synthetic",
        description="Noise applied to pairing quality decisions.",
        default_value=_path_default("matchmaking.matchmaking_noise_factor"),
        min_value=0.0,
        max_value=1.0,
        step=0.01,
    ),
    ConfigEditorFieldDefinition(
        path="matchmaking.locality_weight",
        label="Matchmaking locality weight",
        control_type="slider",
        scope="synthetic",
        description="Weight given to regional locality when ranking potential opponents.",
        default_value=_path_default("matchmaking.locality_weight"),
        basic_or_advanced="advanced",
        min_value=0.0,
        max_value=1.0,
        step=0.01,
    ),
    ConfigEditorFieldDefinition(
        path="games_and_scores.game_target_score",
        label="Game target score",
        control_type="integer",
        scope="synthetic",
        description="Target score for a standard game.",
        default_value=_path_default("games_and_scores.game_target_score"),
        min_value=1,
        step=1,
    ),
    ConfigEditorFieldDefinition(
        path="games_and_scores.win_by_two_rule_enabled",
        label="Win by two rule enabled",
        control_type="checkbox",
        scope="synthetic",
        description="Whether games extend until the winner leads by two.",
        default_value=_path_default("games_and_scores.win_by_two_rule_enabled"),
    ),
    ConfigEditorFieldDefinition(
        path="games_and_scores.games_per_match",
        label="Games per match",
        control_type="json",
        scope="synthetic",
        description="Configured game counts by generated match type.",
        default_value=_path_default("games_and_scores.games_per_match"),
        basic_or_advanced="advanced",
    ),
    ConfigEditorFieldDefinition(
        path="games_and_scores.win_by_two_extension_rate",
        label="Win-by-two extension rate",
        control_type="slider",
        scope="synthetic",
        description="Probability that a win-by-two game extends beyond the base target-1 tie.",
        default_value=_path_default("games_and_scores.win_by_two_extension_rate"),
        basic_or_advanced="advanced",
        min_value=0.0,
        max_value=1.0,
        step=0.01,
    ),
    ConfigEditorFieldDefinition(
        path="games_and_scores.score_noise_std_dev",
        label="Score noise standard deviation",
        control_type="decimal",
        scope="synthetic",
        description="Spread used when varying losing-side game scores around the expected center.",
        default_value=_path_default("games_and_scores.score_noise_std_dev"),
        basic_or_advanced="advanced",
        min_value=0.0,
        step=0.1,
    ),
    ConfigEditorFieldDefinition(
        path="games_and_scores.upset_probability_boost",
        label="Upset probability boost",
        control_type="slider",
        scope="synthetic",
        description="Bounded upset noise applied to rating-derived game win probabilities.",
        default_value=_path_default("games_and_scores.upset_probability_boost"),
        basic_or_advanced="advanced",
        min_value=0.0,
        max_value=1.0,
        step=0.01,
    ),
    ConfigEditorFieldDefinition(
        path="ratings.initial_rating_mean",
        label="Initial rating mean",
        control_type="decimal",
        scope="synthetic",
        description="Mean starting rating for new players.",
        default_value=_path_default("ratings.initial_rating_mean"),
        min_value=0.0,
        step=1.0,
    ),
    ConfigEditorFieldDefinition(
        path="ratings.rating_min",
        label="Minimum rating",
        control_type="decimal",
        scope="synthetic",
        description="Lower rating floor for the simulation.",
        default_value=_path_default("ratings.rating_min"),
        min_value=0.0,
        step=1.0,
    ),
    ConfigEditorFieldDefinition(
        path="ratings.rating_max",
        label="Maximum rating",
        control_type="decimal",
        scope="synthetic",
        description="Upper rating ceiling for the simulation.",
        default_value=_path_default("ratings.rating_max"),
        min_value=0.0,
        step=1.0,
    ),
    ConfigEditorFieldDefinition(
        path="confidence.initial_confidence_score",
        label="Initial confidence score",
        control_type="slider",
        scope="synthetic",
        description="Starting confidence score assigned to each player.",
        default_value=_path_default("confidence.initial_confidence_score"),
        min_value=0.0,
        max_value=1.0,
        step=0.01,
    ),
    ConfigEditorFieldDefinition(
        path="ratings.initial_rating_std_dev",
        label="Initial rating standard deviation",
        control_type="decimal",
        scope="synthetic",
        description="Spread used when sampling starting ratings for new players.",
        default_value=_path_default("ratings.initial_rating_std_dev"),
        basic_or_advanced="advanced",
        min_value=0.0,
        step=1.0,
    ),
    ConfigEditorFieldDefinition(
        path="ratings.initial_rating_elite_tail_rate",
        label="Initial elite-tail rate",
        control_type="slider",
        scope="synthetic",
        description="Probability that a new player is sampled from the elite starting-rating tail.",
        default_value=_path_default("ratings.initial_rating_elite_tail_rate"),
        basic_or_advanced="advanced",
        min_value=0.0,
        max_value=1.0,
        step=0.001,
    ),
    ConfigEditorFieldDefinition(
        path="ratings.initial_rating_elite_min",
        label="Initial elite minimum rating",
        control_type="decimal",
        scope="synthetic",
        description="Lower bound for the elite starting-rating tail.",
        default_value=_path_default("ratings.initial_rating_elite_min"),
        basic_or_advanced="advanced",
        min_value=0.0,
        step=1.0,
    ),
    ConfigEditorFieldDefinition(
        path="ratings.initial_rating_elite_max",
        label="Initial elite maximum rating",
        control_type="decimal",
        scope="synthetic",
        description="Upper bound for the elite starting-rating tail.",
        default_value=_path_default("ratings.initial_rating_elite_max"),
        basic_or_advanced="advanced",
        min_value=0.0,
        step=1.0,
    ),
    ConfigEditorFieldDefinition(
        path="ratings.k_factor_new_player",
        label="New-player K factor",
        control_type="decimal",
        scope="synthetic",
        description="K factor applied to early rating updates for new players.",
        default_value=_path_default("ratings.k_factor_new_player"),
        basic_or_advanced="advanced",
        min_value=0.0,
        step=1.0,
    ),
    ConfigEditorFieldDefinition(
        path="ratings.k_factor_established",
        label="Established-player K factor",
        control_type="decimal",
        scope="synthetic",
        description="K factor applied to rating updates for established players.",
        default_value=_path_default("ratings.k_factor_established"),
        basic_or_advanced="advanced",
        min_value=0.0,
        step=1.0,
    ),
    ConfigEditorFieldDefinition(
        path="ratings.k_factor_elite",
        label="Elite-player K factor",
        control_type="decimal",
        scope="synthetic",
        description="K factor applied to rating updates for elite players.",
        default_value=_path_default("ratings.k_factor_elite"),
        basic_or_advanced="advanced",
        min_value=0.0,
        step=1.0,
    ),
    ConfigEditorFieldDefinition(
        path="confidence.confidence_max",
        label="Maximum confidence score",
        control_type="slider",
        scope="synthetic",
        description="Upper cap on player confidence during rating updates.",
        default_value=_path_default("confidence.confidence_max"),
        basic_or_advanced="advanced",
        min_value=0.0,
        max_value=1.0,
        step=0.01,
    ),
    ConfigEditorFieldDefinition(
        path="confidence.confidence_increment_per_match",
        label="Confidence increment per match",
        control_type="slider",
        scope="synthetic",
        description="Confidence increase applied after each rated match.",
        default_value=_path_default("confidence.confidence_increment_per_match"),
        basic_or_advanced="advanced",
        min_value=0.0,
        max_value=1.0,
        step=0.001,
    ),
)


CONFIG_EDITOR_FIELDS_BY_PATH: dict[str, ConfigEditorFieldDefinition] = {
    field.path: field for field in CONFIG_EDITOR_FIELDS
}


CONFIG_EDITOR_SECTIONS: tuple[ConfigEditorSectionDefinition, ...] = (
    ConfigEditorSectionDefinition(
        id="seed_raw_ingest",
        scope="seed",
        title="Seed Data Ingest and Preparation",
        description="Raw seed data sources and ingest behavior.",
        field_paths=(
            "raw_seed_data.supported_datasets",
        ),
    ),
    ConfigEditorSectionDefinition(
        id="seed_club_generation",
        scope="seed",
        title="Club Generation and Memberships",
        description="Club capacity and membership assignment settings used in generation.",
        field_paths=(
            "club_generation.capacity_ranges",
            "club_generation.unaffiliated_player_rate",
            "club_generation.cross_region_assignment_enabled",
        ),
    ),
    ConfigEditorSectionDefinition(
        id="seed_club_facilities_membership_policy",
        scope="seed",
        title="Club Facilities and Membership Policy",
        description="Court-capacity and multi-membership controls used by club normalization and membership assignment.",
        field_paths=(
            "club_generation.court_ranges",
            "club_generation.indoor_court_ratios",
            "club_generation.multi_club_membership_rate",
            "club_generation.min_club_memberships_per_affiliated_player",
            "club_generation.max_club_memberships_per_player",
            "club_generation.secondary_membership_same_region_rate",
        ),
    ),
    ConfigEditorSectionDefinition(
        id="synthetic_simulation_identity",
        scope="synthetic",
        title="Simulation Scale and Determinism",
        description="Run versioning, batch span, seed value, and target scale used by generation.",
        field_paths=(
            "simulation.simulation_version",
            "simulation.master_seed",
            "simulation.target_total_players",
            "simulation.historical_batch_count",
            "simulation.first_batch_month",
        ),
    ),
    ConfigEditorSectionDefinition(
        id="synthetic_player_generation",
        scope="synthetic",
        title="Player Generation",
        description="Starting population size and demographic distributions used by player generation.",
        field_paths=(
            "player_generation.player_count",
            "player_generation.age_min",
            "player_generation.age_max",
            "player_generation.age_distribution",
            "player_generation.gender_weights",
        ),
    ),
    ConfigEditorSectionDefinition(
        id="synthetic_player_traits_skill",
        scope="synthetic",
        title="Player Traits and Skill Seeding",
        description="Handedness, initial status, and latent skill-seeding controls used during player creation.",
        field_paths=(
            "player_generation.dominant_hand_weights",
            "player_generation.player_status_weights",
            "player_generation.initial_skill_seed.mean",
            "player_generation.initial_skill_seed.std_dev",
            "player_generation.initial_skill_seed.lower_bias",
            "player_generation.initial_skill_seed.min",
            "player_generation.initial_skill_seed.max",
        ),
    ),
    ConfigEditorSectionDefinition(
        id="synthetic_team_formation",
        scope="synthetic",
        title="Team Formation",
        description="Participation, team-type mix, and active-team constraints.",
        field_paths=(
            "team_formation.player_team_participation_rate",
            "team_formation.target_team_count",
            "team_formation.max_active_teams_per_player",
            "team_formation.same_club_team_rate",
            "team_formation.same_region_team_rate",
            "team_formation.rating_gap_mean",
            "team_formation.rating_gap_std_dev",
            "team_formation.rating_gap_max",
            "team_formation.team_type_weights",
            "team_formation.team_persistence_probability_recreational",
            "team_formation.team_chemistry_weight",
            "team_formation.team_skill_balance_weight",
            "team_formation.team_club_proximity_weight",
            "team_formation.team_region_proximity_weight",
            "team_formation.team_noise_factor",
            "team_formation.allow_multiple_active_teams_per_scope",
        ),
    ),
    ConfigEditorSectionDefinition(
        id="synthetic_match_scheduling",
        scope="synthetic",
        title="Match Scheduling",
        description="Monthly match volume and day-of-week scheduling preferences used by match generation.",
        field_paths=(
            "match_scheduling.matches_per_team_per_month",
            "match_scheduling.saturday_weight",
            "match_scheduling.sunday_weight",
            "match_scheduling.friday_weight",
            "match_scheduling.weekday_evening_weight",
            "match_scheduling.max_daily_matches_per_team",
        ),
    ),
    ConfigEditorSectionDefinition(
        id="synthetic_match_types",
        scope="synthetic",
        title="Match Types",
        description="Type mix used when generating matches.",
        field_paths=(
            "match_types.weights",
        ),
    ),
    ConfigEditorSectionDefinition(
        id="synthetic_matchmaking",
        scope="synthetic",
        title="Matchmaking",
        description="Match quality and pairing-balance controls.",
        field_paths=(
            "matchmaking.rating_band_width",
            "matchmaking.matchmaking_noise_factor",
            "matchmaking.locality_weight",
        ),
    ),
    ConfigEditorSectionDefinition(
        id="synthetic_games_scores",
        scope="synthetic",
        title="Games and Scores",
        description="Scoring rules and game structure settings.",
        field_paths=(
            "games_and_scores.game_target_score",
            "games_and_scores.win_by_two_rule_enabled",
        ),
    ),
    ConfigEditorSectionDefinition(
        id="synthetic_ratings_confidence",
        scope="synthetic",
        title="Ratings and Confidence",
        description="Rating scale limits, initialization, and confidence behavior.",
        field_paths=(
            "ratings.initial_rating_mean",
            "ratings.rating_min",
            "ratings.rating_max",
            "confidence.initial_confidence_score",
        ),
    ),
    ConfigEditorSectionDefinition(
        id="synthetic_games_dynamics",
        scope="synthetic",
        title="Games and Score Dynamics",
        description="Advanced game-count and score-variance controls used by game generation.",
        field_paths=(
            "games_and_scores.games_per_match",
            "games_and_scores.win_by_two_extension_rate",
            "games_and_scores.score_noise_std_dev",
            "games_and_scores.upset_probability_boost",
        ),
    ),
    ConfigEditorSectionDefinition(
        id="synthetic_rating_updates",
        scope="synthetic",
        title="Rating Initialization and Updates",
        description="Advanced starting-rating and post-match rating-update controls used by player and rating generation.",
        field_paths=(
            "ratings.initial_rating_std_dev",
            "ratings.initial_rating_elite_tail_rate",
            "ratings.initial_rating_elite_min",
            "ratings.initial_rating_elite_max",
            "ratings.k_factor_new_player",
            "ratings.k_factor_established",
            "ratings.k_factor_elite",
            "confidence.confidence_max",
            "confidence.confidence_increment_per_match",
        ),
    ),
)


def build_config_editor_sections(
    payload: Mapping[str, Any] | None,
) -> tuple[ConfigEditorSectionState, ...]:
    """Resolve the current payload into section/field state objects."""
    return tuple(
        ConfigEditorSectionState(
            definition=section,
            fields=tuple(_build_field_state(payload, path) for path in section.field_paths),
        )
        for section in CONFIG_EDITOR_SECTIONS
    )


def _build_field_state(
    payload: Mapping[str, Any] | None,
    path: str,
) -> ConfigEditorFieldState:
    definition = CONFIG_EDITOR_FIELDS_BY_PATH[path]
    value = get_payload_value(payload, path)
    return ConfigEditorFieldState(
        definition=definition,
        value=value,
        is_default_value=value == definition.default_value,
        is_present_in_payload=value is not None,
    )
