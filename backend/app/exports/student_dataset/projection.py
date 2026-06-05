"""Explicit student-facing dataset projection contract.

This module is intentionally declarative. Export code should consume these
definitions rather than deriving student-facing columns from ORM models.
Dynamic ORM inspection is limited to fail-closed drift checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from app.models import (
    Base,
    Club,
    ClubMembership,
    Match,
    MatchGame,
    MatchTeam,
    MatchTeamPlayer,
    MonthlyBatch,
    Player,
    PlayerAssessmentHistory,
    PlayerRatingHistory,
    PlayerRegistration,
    Region,
    Team,
    TeamMembership,
)


STUDENT_DATASET_SCHEMA_VERSION = "1.1"

STUDENT_TABLE_ORDER: tuple[str, ...] = (
    "clubs",
    "club_memberships",
    "match_games",
    "match_team_players",
    "match_teams",
    "matches",
    "monthly_batches",
    "player_assessment_history",
    "player_rating_history",
    "player_registrations",
    "players",
    "regions",
    "team_memberships",
    "teams",
)

EXCLUDED_SOURCE_TABLES: frozenset[str] = frozenset(
    {
        "batch_runs",
        "configuration_profile_versions",
        "configuration_profiles",
        "export_runs",
        "first_names",
        "generation_runtime_metrics",
        "generation_runs",
        "job_stage_progress",
        "job_status",
        "last_names",
        "ratings_update_log",
        "raw_first_names",
        "raw_last_names",
        "raw_metro_areas",
        "raw_pickleball_club_distributions",
        "raw_pickleball_club_names",
        "raw_seed_load_errors",
        "raw_seed_load_runs",
        "raw_state_prov_biases",
        "student_dataset_release_files",
        "student_dataset_releases",
        "team_lifecycle_events",
        "tournaments",
        "uploaded_files",
        "validation_results",
    }
)


@dataclass(frozen=True)
class SourceFilterSpec:
    """Named source-filter contract to be implemented by the exporter."""

    key: str
    description: str


@dataclass(frozen=True)
class RelationshipValidation:
    """Required relationship validation for an exported table."""

    child_table: str
    child_column: str
    parent_table: str
    parent_column: str = "id"
    nullable: bool = False


@dataclass(frozen=True)
class TemporalValidation:
    """Required as-of temporal validation for an exported table."""

    table_name: str
    expression: str
    description: str


@dataclass(frozen=True)
class StudentTableProjection:
    """Explicit table projection for one student-facing Parquet file."""

    source_table: str
    model: type
    output_file: str
    source_columns: tuple[str, ...]
    included_columns: tuple[str, ...]
    excluded_columns: tuple[str, ...]
    source_filter: SourceFilterSpec
    relationship_validations: tuple[RelationshipValidation, ...] = ()
    temporal_validations: tuple[TemporalValidation, ...] = ()

    @property
    def output_table(self) -> str:
        """Return the output table name implied by the Parquet file."""

        return self.output_file.removesuffix(".parquet")


class ProjectionDriftError(ValueError):
    """Raised when the explicit projection no longer matches ORM metadata."""


def _projection(
    *,
    model: type,
    source_table: str,
    source_columns: tuple[str, ...],
    included_columns: tuple[str, ...],
    excluded_columns: tuple[str, ...],
    source_filter_key: str,
    source_filter_description: str,
    relationship_validations: tuple[RelationshipValidation, ...] = (),
    temporal_validations: tuple[TemporalValidation, ...] = (),
) -> StudentTableProjection:
    return StudentTableProjection(
        source_table=source_table,
        model=model,
        output_file=f"{source_table}.parquet",
        source_columns=source_columns,
        included_columns=included_columns,
        excluded_columns=excluded_columns,
        source_filter=SourceFilterSpec(
            key=source_filter_key,
            description=source_filter_description,
        ),
        relationship_validations=relationship_validations,
        temporal_validations=temporal_validations,
    )


PROJECTIONS: tuple[StudentTableProjection, ...] = (
    _projection(
        model=Club,
        source_table="clubs",
        source_columns=(
            "id",
            "club_name",
            "region_id",
            "club_type",
            "competitiveness_level",
            "member_capacity",
            "founding_date",
            "indoor_court_count",
            "outdoor_court_count",
            "generation_run_id",
            "created_at",
            "updated_at",
        ),
        included_columns=(
            "id",
            "club_name",
            "region_id",
            "club_type",
            "competitiveness_level",
            "member_capacity",
            "founding_date",
            "indoor_court_count",
            "outdoor_court_count",
        ),
        excluded_columns=("generation_run_id", "created_at", "updated_at"),
        source_filter_key="clubs_as_of_snapshot",
        source_filter_description=(
            "Clubs for the selected run founded before snapshot end, plus clubs "
            "referenced by included memberships."
        ),
        relationship_validations=(
            RelationshipValidation("clubs", "region_id", "regions"),
        ),
        temporal_validations=(
            TemporalValidation(
                "clubs",
                "founding_date IS NULL OR founding_date < snapshot_end_exclusive",
                "Clubs must not be founded after the release snapshot month.",
            ),
        ),
    ),
    _projection(
        model=ClubMembership,
        source_table="club_memberships",
        source_columns=(
            "id",
            "player_id",
            "club_id",
            "membership_type",
            "start_date",
            "end_date",
            "is_primary",
            "generation_run_id",
            "created_at",
            "updated_at",
        ),
        included_columns=(
            "id",
            "player_id",
            "club_id",
            "membership_type",
            "start_date",
            "end_date",
            "is_primary",
        ),
        excluded_columns=("generation_run_id", "created_at", "updated_at"),
        source_filter_key="club_memberships_as_of_snapshot",
        source_filter_description=(
            "Memberships for the selected run or included players with "
            "start_date before snapshot end; future end_date values are "
            "projected as null."
        ),
        relationship_validations=(
            RelationshipValidation("club_memberships", "player_id", "players"),
            RelationshipValidation("club_memberships", "club_id", "clubs"),
        ),
        temporal_validations=(
            TemporalValidation(
                "club_memberships",
                "start_date < snapshot_end_exclusive",
                "Club memberships must start before the release snapshot end.",
            ),
            TemporalValidation(
                "club_memberships",
                "end_date IS NULL OR end_date < snapshot_end_exclusive",
                "Future club membership end dates must be suppressed.",
            ),
        ),
    ),
    _projection(
        model=MatchGame,
        source_table="match_games",
        source_columns=(
            "id",
            "match_id",
            "game_number",
            "team_one_score",
            "team_two_score",
            "winning_team_number",
            "target_score",
            "win_by",
            "expected_team_one_score_share",
            "actual_team_one_score_share",
            "expected_team_one_score",
            "expected_team_two_score",
            "score_noise_factor",
            "created_at",
            "updated_at",
        ),
        included_columns=(
            "id",
            "match_id",
            "game_number",
            "team_one_score",
            "team_two_score",
            "winning_team_number",
            "target_score",
            "win_by",
            "actual_team_one_score_share",
        ),
        excluded_columns=(
            "expected_team_one_score_share",
            "expected_team_one_score",
            "expected_team_two_score",
            "score_noise_factor",
            "created_at",
            "updated_at",
        ),
        source_filter_key="match_games_for_included_matches",
        source_filter_description="Games whose match_id belongs to included matches.",
        relationship_validations=(
            RelationshipValidation("match_games", "match_id", "matches"),
        ),
    ),
    _projection(
        model=MatchTeamPlayer,
        source_table="match_team_players",
        source_columns=(
            "id",
            "match_team_id",
            "player_id",
            "player_position",
            "player_rating_at_match",
            "created_at",
            "updated_at",
        ),
        included_columns=(
            "id",
            "match_team_id",
            "player_id",
            "player_position",
            "player_rating_at_match",
        ),
        excluded_columns=("created_at", "updated_at"),
        source_filter_key="match_team_players_for_included_match_teams",
        source_filter_description=(
            "Match-team player rows whose match_team_id belongs to included "
            "match teams."
        ),
        relationship_validations=(
            RelationshipValidation(
                "match_team_players",
                "match_team_id",
                "match_teams",
            ),
            RelationshipValidation("match_team_players", "player_id", "players"),
        ),
    ),
    _projection(
        model=MatchTeam,
        source_table="match_teams",
        source_columns=(
            "id",
            "match_id",
            "team_number",
            "team_score",
            "expected_win_probability",
            "average_team_rating",
            "created_at",
            "updated_at",
        ),
        included_columns=(
            "id",
            "match_id",
            "team_number",
            "team_score",
            "average_team_rating",
        ),
        excluded_columns=(
            "expected_win_probability",
            "created_at",
            "updated_at",
        ),
        source_filter_key="match_teams_for_included_matches",
        source_filter_description="Match teams whose match_id belongs to included matches.",
        relationship_validations=(
            RelationshipValidation("match_teams", "match_id", "matches"),
        ),
    ),
    _projection(
        model=Match,
        source_table="matches",
        source_columns=(
            "id",
            "tournament_id",
            "match_date",
            "region_id",
            "match_type",
            "court_type",
            "match_format",
            "winning_team_id",
            "predicted_winning_team_number",
            "predicted_win_probability",
            "total_points_played",
            "expected_competitiveness",
            "simulation_noise_factor",
            "batch_id",
            "created_at",
            "updated_at",
        ),
        included_columns=(
            "id",
            "match_date",
            "region_id",
            "match_type",
            "court_type",
            "match_format",
            "winning_team_id",
            "total_points_played",
            "batch_id",
        ),
        excluded_columns=(
            "tournament_id",
            "predicted_winning_team_number",
            "predicted_win_probability",
            "expected_competitiveness",
            "simulation_noise_factor",
            "created_at",
            "updated_at",
        ),
        source_filter_key="matches_for_included_batches",
        source_filter_description="Matches whose batch_id belongs to included monthly batches.",
        relationship_validations=(
            RelationshipValidation("matches", "region_id", "regions", nullable=True),
            RelationshipValidation("matches", "batch_id", "monthly_batches"),
            RelationshipValidation(
                "matches",
                "winning_team_id",
                "match_teams",
                nullable=True,
            ),
        ),
    ),
    _projection(
        model=MonthlyBatch,
        source_table="monthly_batches",
        source_columns=(
            "id",
            "generation_run_id",
            "batch_month",
            "batch_sequence",
            "batch_type",
            "active_player_count_start",
            "new_player_count",
            "active_player_count_end",
            "match_count_generated",
            "rating_update_count",
            "assessment_update_count",
            "processing_status",
            "started_at",
            "completed_at",
            "error_message",
            "created_at",
            "updated_at",
        ),
        included_columns=(
            "id",
            "batch_month",
            "batch_sequence",
            "batch_type",
            "active_player_count_start",
            "new_player_count",
            "active_player_count_end",
            "match_count_generated",
            "rating_update_count",
            "assessment_update_count",
        ),
        excluded_columns=(
            "generation_run_id",
            "processing_status",
            "started_at",
            "completed_at",
            "error_message",
            "created_at",
            "updated_at",
        ),
        source_filter_key="monthly_batches_for_release_window",
        source_filter_description=(
            "Completed monthly batches for the selected generation run and "
            "release batch-sequence window."
        ),
    ),
    _projection(
        model=PlayerAssessmentHistory,
        source_table="player_assessment_history",
        source_columns=(
            "id",
            "player_id",
            "assessment_date",
            "assessment_type",
            "assessment_value",
            "confidence_score",
            "derived_from_matches",
            "batch_id",
            "created_at",
        ),
        included_columns=(
            "id",
            "player_id",
            "assessment_date",
            "assessment_type",
            "assessment_value",
            "confidence_score",
            "derived_from_matches",
            "batch_id",
        ),
        excluded_columns=("created_at",),
        source_filter_key="player_assessments_for_included_batches",
        source_filter_description=(
            "Assessment rows tied to included monthly batches and included players."
        ),
        relationship_validations=(
            RelationshipValidation(
                "player_assessment_history",
                "player_id",
                "players",
            ),
            RelationshipValidation(
                "player_assessment_history",
                "batch_id",
                "monthly_batches",
            ),
        ),
    ),
    _projection(
        model=PlayerRatingHistory,
        source_table="player_rating_history",
        source_columns=(
            "id",
            "player_id",
            "rating_date",
            "rating_type",
            "rating_value",
            "confidence_score",
            "volatility_score",
            "expected_performance",
            "regional_adjustment_factor",
            "global_percentile",
            "match_count_used",
            "calculation_version",
            "batch_id",
            "created_at",
            "updated_at",
        ),
        included_columns=(
            "id",
            "player_id",
            "rating_date",
            "rating_type",
            "rating_value",
            "confidence_score",
            "volatility_score",
            "regional_adjustment_factor",
            "global_percentile",
            "match_count_used",
            "batch_id",
        ),
        excluded_columns=(
            "expected_performance",
            "calculation_version",
            "created_at",
            "updated_at",
        ),
        source_filter_key="player_ratings_for_included_batches",
        source_filter_description=(
            "Rating rows tied to included monthly batches and included players."
        ),
        relationship_validations=(
            RelationshipValidation("player_rating_history", "player_id", "players"),
            RelationshipValidation(
                "player_rating_history",
                "batch_id",
                "monthly_batches",
            ),
        ),
    ),
    _projection(
        model=PlayerRegistration,
        source_table="player_registrations",
        source_columns=(
            "id",
            "player_id",
            "batch_id",
            "registration_month",
            "registration_source",
            "assigned_region_id",
            "initial_rating_value",
            "initial_confidence_score",
            "created_at",
        ),
        included_columns=(
            "id",
            "player_id",
            "batch_id",
            "registration_month",
            "registration_source",
            "assigned_region_id",
            "initial_rating_value",
            "initial_confidence_score",
        ),
        excluded_columns=("created_at",),
        source_filter_key="player_registrations_for_included_batches",
        source_filter_description=(
            "Registration rows tied to included monthly batches and included players."
        ),
        relationship_validations=(
            RelationshipValidation("player_registrations", "player_id", "players"),
            RelationshipValidation(
                "player_registrations",
                "batch_id",
                "monthly_batches",
            ),
            RelationshipValidation(
                "player_registrations",
                "assigned_region_id",
                "regions",
                nullable=True,
            ),
        ),
    ),
    _projection(
        model=Player,
        source_table="players",
        source_columns=(
            "id",
            "external_player_key",
            "first_name",
            "last_name",
            "gender",
            "birth_date",
            "dominant_hand",
            "home_region_id",
            "registration_date",
            "initial_skill_seed",
            "player_status",
            "generation_run_id",
            "created_at",
            "updated_at",
        ),
        included_columns=(
            "id",
            "external_player_key",
            "first_name",
            "last_name",
            "gender",
            "birth_date",
            "dominant_hand",
            "home_region_id",
            "registration_date",
            "player_status",
        ),
        excluded_columns=(
            "initial_skill_seed",
            "generation_run_id",
            "created_at",
            "updated_at",
        ),
        source_filter_key="players_as_of_snapshot",
        source_filter_description=(
            "Players for the selected run with registration_date before snapshot end."
        ),
        relationship_validations=(
            RelationshipValidation(
                "players",
                "home_region_id",
                "regions",
                nullable=True,
            ),
        ),
        temporal_validations=(
            TemporalValidation(
                "players",
                "registration_date < snapshot_end_exclusive",
                "Players must be registered before the release snapshot end.",
            ),
        ),
    ),
    _projection(
        model=Region,
        source_table="regions",
        source_columns=(
            "id",
            "country_code",
            "region_type",
            "region_name",
            "state_province_code",
            "population",
            "selection_probability",
            "competitiveness_multiplier",
            "latitude",
            "longitude",
            "created_at",
            "updated_at",
        ),
        included_columns=(
            "id",
            "country_code",
            "region_type",
            "region_name",
            "state_province_code",
            "population",
            "latitude",
            "longitude",
        ),
        excluded_columns=(
            "selection_probability",
            "competitiveness_multiplier",
            "created_at",
            "updated_at",
        ),
        source_filter_key="regions_referenced_by_release",
        source_filter_description=(
            "Regions referenced by included players, clubs, registrations, or matches."
        ),
    ),
    _projection(
        model=TeamMembership,
        source_table="team_memberships",
        source_columns=(
            "id",
            "team_id",
            "player_id",
            "player_position",
            "joined_date",
            "left_date",
            "created_at",
            "updated_at",
        ),
        included_columns=(
            "id",
            "team_id",
            "player_id",
            "player_position",
            "joined_date",
            "left_date",
        ),
        excluded_columns=("created_at", "updated_at"),
        source_filter_key="team_memberships_as_of_snapshot",
        source_filter_description=(
            "Team memberships for included teams and players joined before "
            "snapshot end; future left_date values are projected as null."
        ),
        relationship_validations=(
            RelationshipValidation("team_memberships", "team_id", "teams"),
            RelationshipValidation("team_memberships", "player_id", "players"),
        ),
        temporal_validations=(
            TemporalValidation(
                "team_memberships",
                "joined_date < snapshot_end_exclusive",
                "Team memberships must start before the release snapshot end.",
            ),
            TemporalValidation(
                "team_memberships",
                "left_date IS NULL OR left_date < snapshot_end_exclusive",
                "Future team membership left dates must be suppressed.",
            ),
        ),
    ),
    _projection(
        model=Team,
        source_table="teams",
        source_columns=(
            "id",
            "team_type",
            "team_status",
            "country_code",
            "formation_date",
            "dissolution_date",
            "chemistry_score",
            "persistence_probability",
            "generation_run_id",
            "created_at",
            "updated_at",
        ),
        included_columns=(
            "id",
            "team_type",
            "team_status",
            "country_code",
            "formation_date",
            "dissolution_date",
        ),
        excluded_columns=(
            "chemistry_score",
            "persistence_probability",
            "generation_run_id",
            "created_at",
            "updated_at",
        ),
        source_filter_key="teams_as_of_snapshot",
        source_filter_description=(
            "Teams for the selected run formed before snapshot end; future "
            "dissolution_date and dissolved status values are projected to the "
            "as-of state."
        ),
        temporal_validations=(
            TemporalValidation(
                "teams",
                "formation_date < snapshot_end_exclusive",
                "Teams must be formed before the release snapshot end.",
            ),
            TemporalValidation(
                "teams",
                "dissolution_date IS NULL OR dissolution_date < snapshot_end_exclusive",
                "Future team dissolution dates must be suppressed.",
            ),
        ),
    ),
)

PROJECTION_BY_TABLE: Mapping[str, StudentTableProjection] = {
    projection.source_table: projection for projection in PROJECTIONS
}


def get_projection(table_name: str) -> StudentTableProjection:
    """Return the projection for a student-facing source table."""

    try:
        return PROJECTION_BY_TABLE[table_name]
    except KeyError as exc:
        raise KeyError(f"No student dataset projection for table: {table_name}") from exc


def validate_projection_contract(metadata=Base.metadata) -> None:
    """Fail if the explicit projection contract drifts from ORM metadata."""

    expected_tables = set(STUDENT_TABLE_ORDER)
    projection_tables = set(PROJECTION_BY_TABLE)
    if projection_tables != expected_tables:
        missing = sorted(expected_tables - projection_tables)
        unexpected = sorted(projection_tables - expected_tables)
        raise ProjectionDriftError(
            "Student projection table mismatch: "
            f"missing={missing}, unexpected={unexpected}"
        )

    included_and_excluded = expected_tables | EXCLUDED_SOURCE_TABLES
    orm_tables = set(metadata.tables)
    uncovered_tables = sorted(orm_tables - included_and_excluded)
    missing_orm_tables = sorted(included_and_excluded - orm_tables)
    if uncovered_tables or missing_orm_tables:
        raise ProjectionDriftError(
            "Student projection source-table coverage mismatch: "
            f"uncovered={uncovered_tables}, missing_orm={missing_orm_tables}"
        )

    for table_name in STUDENT_TABLE_ORDER:
        projection = PROJECTION_BY_TABLE[table_name]
        orm_table = metadata.tables.get(table_name)
        if orm_table is None:
            raise ProjectionDriftError(f"Missing ORM table for {table_name}")

        orm_columns = tuple(column.name for column in orm_table.columns)
        if projection.source_columns != orm_columns:
            raise ProjectionDriftError(
                f"Source columns drifted for {table_name}: "
                f"projection={projection.source_columns}, orm={orm_columns}"
            )

        included = set(projection.included_columns)
        excluded = set(projection.excluded_columns)
        source = set(projection.source_columns)
        overlap = sorted(included & excluded)
        missing = sorted(source - (included | excluded))
        unexpected = sorted((included | excluded) - source)
        if overlap or missing or unexpected:
            raise ProjectionDriftError(
                f"Included/excluded columns do not partition {table_name}: "
                f"overlap={overlap}, missing={missing}, unexpected={unexpected}"
            )

        if projection.output_table != projection.source_table:
            raise ProjectionDriftError(
                f"Output file does not match source table for {table_name}: "
                f"{projection.output_file}"
            )
