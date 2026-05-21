"""Metadata scaffold for a future schema-driven configuration editor."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Mapping

from .default_configuration import default_config_payload


ConfigEditorScope = Literal["seed", "synthetic"]
ConfigEditorControlType = Literal[
    "text",
    "integer",
    "decimal",
    "checkbox",
    "select",
    "slider",
    "string_list",
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
        path="raw_seed_data.raw_data_root",
        label="Raw seed data root",
        control_type="text",
        scope="seed",
        description="Base directory containing raw seed data files.",
        default_value=_path_default("raw_seed_data.raw_data_root"),
        required=True,
    ),
    ConfigEditorFieldDefinition(
        path="raw_seed_data.supported_datasets",
        label="Supported raw seed datasets",
        control_type="string_list",
        scope="seed",
        description="Datasets eligible for ingest and refresh workflows.",
        default_value=_path_default("raw_seed_data.supported_datasets"),
        required=True,
    ),
    ConfigEditorFieldDefinition(
        path="raw_seed_data.replace_production",
        label="Replace production reference tables",
        control_type="checkbox",
        scope="seed",
        description="Whether seed ingest should replace production seed records.",
        default_value=_path_default("raw_seed_data.replace_production"),
        basic_or_advanced="advanced",
    ),
    ConfigEditorFieldDefinition(
        path="name_assignment.name_region_fallback_order",
        label="Name region fallback order",
        control_type="string_list",
        scope="seed",
        description="Priority order for resolving regional name lookups.",
        default_value=_path_default("name_assignment.name_region_fallback_order"),
    ),
    ConfigEditorFieldDefinition(
        path="name_assignment.name_year_bucket_size",
        label="Name year bucket size",
        control_type="integer",
        scope="seed",
        description="Birth-year bucket size for name sampling.",
        default_value=_path_default("name_assignment.name_year_bucket_size"),
        min_value=1,
        step=1,
    ),
    ConfigEditorFieldDefinition(
        path="name_assignment.name_assignment_noise_rate",
        label="Name assignment noise rate",
        control_type="slider",
        scope="seed",
        description="Probability of applying noise during name assignment.",
        default_value=_path_default("name_assignment.name_assignment_noise_rate"),
        min_value=0.0,
        max_value=1.0,
        step=0.01,
    ),
    ConfigEditorFieldDefinition(
        path="regional.regional_allocation_strategy",
        label="Regional allocation strategy",
        control_type="select",
        scope="seed",
        description="How target players are allocated across regions.",
        default_value=_path_default("regional.regional_allocation_strategy"),
        options=(
            ConfigEditorOption(
                value="selection_probability",
                label="Selection probability",
                description="Allocate using region selection probabilities.",
            ),
        ),
    ),
    ConfigEditorFieldDefinition(
        path="regional.region_population_weight",
        label="Region population weight",
        control_type="decimal",
        scope="seed",
        description="Relative importance of raw population in regional allocation.",
        default_value=_path_default("regional.region_population_weight"),
        min_value=0.0,
        step=0.01,
    ),
    ConfigEditorFieldDefinition(
        path="regional.min_players_per_region",
        label="Minimum players per region",
        control_type="integer",
        scope="seed",
        description="Lower bound on player allocation for an active region.",
        default_value=_path_default("regional.min_players_per_region"),
        min_value=0,
        step=1,
    ),
    ConfigEditorFieldDefinition(
        path="regional.regional_competitiveness_multipliers",
        label="Regional competitiveness multipliers",
        control_type="json",
        scope="seed",
        description="Per-region competitiveness overrides keyed by region label.",
        default_value=_path_default("regional.regional_competitiveness_multipliers"),
        basic_or_advanced="advanced",
    ),
    ConfigEditorFieldDefinition(
        path="club_generation.target_club_count",
        label="Target club count",
        control_type="integer",
        scope="seed",
        description="Target number of clubs to generate for the seed baseline.",
        default_value=_path_default("club_generation.target_club_count"),
        min_value=1,
        step=1,
    ),
    ConfigEditorFieldDefinition(
        path="club_generation.monthly_club_growth_rate",
        label="Monthly club growth rate",
        control_type="slider",
        scope="seed",
        description="Growth rate applied to club counts over time.",
        default_value=_path_default("club_generation.monthly_club_growth_rate"),
        min_value=0.0,
        max_value=1.0,
        step=0.001,
    ),
    ConfigEditorFieldDefinition(
        path="club_generation.club_size_distribution",
        label="Club size distribution",
        control_type="weight_table",
        scope="seed",
        description="Weight distribution over club size buckets.",
        default_value=_path_default("club_generation.club_size_distribution"),
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
        path="runtime.environment_name",
        label="Runtime environment name",
        control_type="text",
        scope="synthetic",
        description="Named environment shown in operational surfaces.",
        default_value=_path_default("runtime.environment_name"),
        basic_or_advanced="advanced",
    ),
    ConfigEditorFieldDefinition(
        path="runtime.database_echo",
        label="Enable SQL echo logging",
        control_type="checkbox",
        scope="synthetic",
        description="Whether SQLAlchemy should emit SQL statements in logs.",
        default_value=_path_default("runtime.database_echo"),
        basic_or_advanced="advanced",
    ),
    ConfigEditorFieldDefinition(
        path="simulation.simulation_name",
        label="Simulation name",
        control_type="text",
        scope="synthetic",
        description="Human-readable name for the current simulation profile.",
        default_value=_path_default("simulation.simulation_name"),
        required=True,
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
        control_type="text",
        scope="synthetic",
        description="First generated month in ISO date format.",
        default_value=_path_default("simulation.first_batch_month"),
        required=True,
    ),
    ConfigEditorFieldDefinition(
        path="simulation.generation_run_mode",
        label="Generation run mode",
        control_type="select",
        scope="synthetic",
        description="Execution mode for the generation run.",
        default_value=_path_default("simulation.generation_run_mode"),
        options=(
            ConfigEditorOption(value="full", label="Full"),
        ),
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
        path="player_generation.monthly_player_growth_rate",
        label="Monthly player growth rate",
        control_type="slider",
        scope="synthetic",
        description="Growth rate applied when adding players across months.",
        default_value=_path_default("player_generation.monthly_player_growth_rate"),
        min_value=0.0,
        max_value=1.0,
        step=0.001,
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
        path="team_formation.team_type_weights",
        label="Team type weights",
        control_type="weight_table",
        scope="synthetic",
        description="Sampling weights for team types.",
        default_value=_path_default("team_formation.team_type_weights"),
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
        path="match_scheduling.monthly_matches_per_active_player_mean",
        label="Monthly matches per active player mean",
        control_type="decimal",
        scope="synthetic",
        description="Average monthly matches for an active player.",
        default_value=_path_default("match_scheduling.monthly_matches_per_active_player_mean"),
        min_value=0.0,
        step=0.1,
    ),
    ConfigEditorFieldDefinition(
        path="match_scheduling.weekend_concentration_bias",
        label="Weekend concentration bias",
        control_type="decimal",
        scope="synthetic",
        description="Relative weighting applied to weekend match scheduling.",
        default_value=_path_default("match_scheduling.weekend_concentration_bias"),
        min_value=0.0,
        step=0.05,
    ),
    ConfigEditorFieldDefinition(
        path="match_scheduling.holiday_modifier_enabled",
        label="Holiday modifier enabled",
        control_type="checkbox",
        scope="synthetic",
        description="Whether holiday adjustments are applied to scheduling.",
        default_value=_path_default("match_scheduling.holiday_modifier_enabled"),
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
        path="availability_and_injury.base_injury_rate",
        label="Base injury rate",
        control_type="slider",
        scope="synthetic",
        description="Baseline probability of injury per month.",
        default_value=_path_default("availability_and_injury.base_injury_rate"),
        min_value=0.0,
        max_value=1.0,
        step=0.001,
    ),
    ConfigEditorFieldDefinition(
        path="seasonality_weather_travel.seasonality_enabled",
        label="Seasonality enabled",
        control_type="checkbox",
        scope="synthetic",
        description="Whether seasonality modifiers are applied.",
        default_value=_path_default("seasonality_weather_travel.seasonality_enabled"),
        basic_or_advanced="advanced",
    ),
    ConfigEditorFieldDefinition(
        path="validation.validation_strictness",
        label="Validation strictness",
        control_type="select",
        scope="synthetic",
        description="Validation rule strictness level applied after generation.",
        default_value=_path_default("validation.validation_strictness"),
        options=(
            ConfigEditorOption(value="standard", label="Standard"),
        ),
    ),
    ConfigEditorFieldDefinition(
        path="validation.distribution_tolerance",
        label="Distribution tolerance",
        control_type="decimal",
        scope="synthetic",
        description="Tolerance for distribution checks in validation.",
        default_value=_path_default("validation.distribution_tolerance"),
        min_value=0.0,
        step=0.001,
    ),
    ConfigEditorFieldDefinition(
        path="export.export_directory",
        label="Export directory",
        control_type="text",
        scope="synthetic",
        description="Base directory for generated exports.",
        default_value=_path_default("export.export_directory"),
        basic_or_advanced="advanced",
    ),
    ConfigEditorFieldDefinition(
        path="export.export_format_primary",
        label="Primary export format",
        control_type="select",
        scope="synthetic",
        description="Primary on-disk export format.",
        default_value=_path_default("export.export_format_primary"),
        options=(
            ConfigEditorOption(value="parquet", label="Parquet"),
        ),
    ),
    ConfigEditorFieldDefinition(
        path="export.export_batch_on_completion",
        label="Export batch on completion",
        control_type="checkbox",
        scope="synthetic",
        description="Whether exports should run automatically after generation.",
        default_value=_path_default("export.export_batch_on_completion"),
        basic_or_advanced="advanced",
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
            "raw_seed_data.raw_data_root",
            "raw_seed_data.supported_datasets",
            "raw_seed_data.replace_production",
        ),
    ),
    ConfigEditorSectionDefinition(
        id="seed_name_assignment",
        scope="seed",
        title="Name Assignment",
        description="Controls for assigning names from regional seed datasets.",
        field_paths=(
            "name_assignment.name_region_fallback_order",
            "name_assignment.name_year_bucket_size",
            "name_assignment.name_assignment_noise_rate",
        ),
    ),
    ConfigEditorSectionDefinition(
        id="seed_regional_distribution",
        scope="seed",
        title="Regional Distribution",
        description="Regional allocation and competitiveness controls.",
        field_paths=(
            "regional.regional_allocation_strategy",
            "regional.region_population_weight",
            "regional.min_players_per_region",
            "regional.regional_competitiveness_multipliers",
        ),
    ),
    ConfigEditorSectionDefinition(
        id="seed_club_generation",
        scope="seed",
        title="Club Generation and Memberships",
        description="Club counts, distributions, and membership assignment settings.",
        field_paths=(
            "club_generation.target_club_count",
            "club_generation.monthly_club_growth_rate",
            "club_generation.club_size_distribution",
            "club_generation.capacity_ranges",
            "club_generation.unaffiliated_player_rate",
            "club_generation.cross_region_assignment_enabled",
        ),
    ),
    ConfigEditorSectionDefinition(
        id="synthetic_runtime",
        scope="synthetic",
        title="Runtime Settings",
        description="Environment and execution behavior used by the control plane.",
        field_paths=(
            "runtime.environment_name",
            "runtime.database_echo",
        ),
    ),
    ConfigEditorSectionDefinition(
        id="synthetic_simulation_identity",
        scope="synthetic",
        title="Simulation Identity and Target Scale",
        description="Top-level simulation identity, determinism, and run scale.",
        field_paths=(
            "simulation.simulation_name",
            "simulation.simulation_version",
            "simulation.master_seed",
            "simulation.target_total_players",
            "simulation.historical_batch_count",
            "simulation.first_batch_month",
            "simulation.generation_run_mode",
        ),
    ),
    ConfigEditorSectionDefinition(
        id="synthetic_player_generation",
        scope="synthetic",
        title="Player Generation",
        description="Player population size, growth, and demographic distributions.",
        field_paths=(
            "player_generation.player_count",
            "player_generation.monthly_player_growth_rate",
            "player_generation.age_min",
            "player_generation.age_max",
            "player_generation.age_distribution",
            "player_generation.gender_weights",
        ),
    ),
    ConfigEditorSectionDefinition(
        id="synthetic_team_formation",
        scope="synthetic",
        title="Team Formation",
        description="Participation, team-type mix, and active-team constraints.",
        field_paths=(
            "team_formation.player_team_participation_rate",
            "team_formation.team_type_weights",
            "team_formation.allow_multiple_active_teams_per_scope",
        ),
    ),
    ConfigEditorSectionDefinition(
        id="synthetic_match_scheduling",
        scope="synthetic",
        title="Match Scheduling",
        description="Monthly workload volume and date-allocation behavior.",
        field_paths=(
            "match_scheduling.monthly_matches_per_active_player_mean",
            "match_scheduling.weekend_concentration_bias",
            "match_scheduling.holiday_modifier_enabled",
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
        id="synthetic_injury_travel",
        scope="synthetic",
        title="Availability, Injury, and Travel",
        description="Seasonality and injury behavior for ongoing simulation months.",
        field_paths=(
            "availability_and_injury.base_injury_rate",
            "seasonality_weather_travel.seasonality_enabled",
        ),
    ),
    ConfigEditorSectionDefinition(
        id="synthetic_validation_export",
        scope="synthetic",
        title="Validation and Export",
        description="Post-generation validation and export controls.",
        field_paths=(
            "validation.validation_strictness",
            "validation.distribution_tolerance",
            "export.export_directory",
            "export.export_format_primary",
            "export.export_batch_on_completion",
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
