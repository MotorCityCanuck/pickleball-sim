"""Configuration objects for export-layer data quality injection."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Mapping


ISSUE_TYPE_MISSING_OPTIONAL_VALUES = "missing_optional_values"
ISSUE_TYPE_CATEGORICAL_VARIANTS = "categorical_variants"
ISSUE_TYPE_FORMATTING_VARIANTS = "formatting_variants"
ISSUE_TYPE_NAME_CASE_VARIANTS = "name_case_variants"
ISSUE_TYPE_NUMERIC_OUTLIERS = "numeric_outliers"
ISSUE_TYPE_ROUNDING_VARIANTS = "rounding_variants"
ISSUE_TYPE_TIMESTAMP_JITTER = "timestamp_jitter"
ISSUE_TYPE_DUPLICATE_LIKE_ROWS = "duplicate_like_rows"
ISSUE_TYPE_DELAYED_RATING_UPDATES = "delayed_rating_updates"
ISSUE_TYPE_SOFT_JOIN_AMBIGUITY = "soft_join_ambiguity"
HISTORICAL_BASELINE_RELEASE_TYPE = "historical_baseline"
MONTHLY_INCREMENTAL_RELEASE_TYPE = "monthly_incremental"

SUPPORTED_DATA_QUALITY_LEVELS: tuple[str, ...] = (
    "none",
    "low",
    "medium",
    "high",
    "very_high",
)

LEVEL_ALIASES: Mapping[str, str] = {
    "clean": "none",
}

SUPPORTED_ISSUE_TYPES: frozenset[str] = frozenset(
    {
        ISSUE_TYPE_MISSING_OPTIONAL_VALUES,
        ISSUE_TYPE_CATEGORICAL_VARIANTS,
        ISSUE_TYPE_FORMATTING_VARIANTS,
        ISSUE_TYPE_NAME_CASE_VARIANTS,
        ISSUE_TYPE_NUMERIC_OUTLIERS,
        ISSUE_TYPE_ROUNDING_VARIANTS,
        ISSUE_TYPE_TIMESTAMP_JITTER,
        ISSUE_TYPE_DUPLICATE_LIKE_ROWS,
        ISSUE_TYPE_DELAYED_RATING_UPDATES,
        ISSUE_TYPE_SOFT_JOIN_AMBIGUITY,
    }
)

STUDENT_RELEASE_TYPES: tuple[str, ...] = (
    HISTORICAL_BASELINE_RELEASE_TYPE,
    MONTHLY_INCREMENTAL_RELEASE_TYPE,
)

HISTORICAL_RELEASE_LABEL = "historical"
MONTHLY_RELEASE_LABEL = "monthly"


@dataclass(frozen=True)
class DataQualityRateBand:
    """Default percentage range for one issue family."""

    min_pct: float
    max_pct: float

    @property
    def midpoint_ratio(self) -> float:
        return ((self.min_pct + self.max_pct) / 2.0) / 100.0

    @property
    def max_ratio(self) -> float:
        return self.max_pct / 100.0


@dataclass(frozen=True)
class DataQualityLevelProfile:
    """Default issue-rate bands for one named severity level."""

    field_level_issue_rate: DataQualityRateBand
    row_level_issue_rate: DataQualityRateBand
    categorical_variant_rate: DataQualityRateBand
    duplicate_like_row_rate: DataQualityRateBand


@dataclass(frozen=True)
class DataQualityGlobalLimits:
    """Global safety limits enforced across one export release."""

    max_total_affected_rows_pct: float = 5.0
    max_affected_fields_per_row: int = 2
    prevent_primary_key_mutation: bool = True
    prevent_foreign_key_mutation: bool = True
    preserve_required_join_keys: bool = True


@dataclass(frozen=True)
class DataQualityTableRule:
    """One table's enabled issue types and optional severity override."""

    enabled: bool = True
    issue_profile: str | None = None
    allowed_issue_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class DataQualityInjectionConfig:
    """Complete export-layer injection configuration."""

    enabled: bool
    level: str
    random_seed: int
    apply_to_release_types: tuple[str, ...]
    write_instructor_manifest: bool
    write_student_visible_quality_summary: bool
    monthly_release_level_offset: int
    global_limits: DataQualityGlobalLimits
    table_rules: Mapping[str, DataQualityTableRule]

    def effective_level_for_release(self, release_type: str) -> str:
        normalized_level = normalize_data_quality_level(self.level)
        if release_type == MONTHLY_INCREMENTAL_RELEASE_TYPE:
            return adjust_data_quality_level(
                normalized_level,
                self.monthly_release_level_offset,
            )
        return normalized_level

    def applies_to_release_type(self, release_type: str) -> bool:
        return release_type in self.apply_to_release_types

    def seed_for(self, *parts: object) -> int:
        payload = "|".join(str(part) for part in (self.random_seed, *parts))
        digest = sha256(payload.encode("utf-8")).hexdigest()
        return int(digest[:16], 16)


def normalize_data_quality_level(value: str | None) -> str:
    """Normalize a caller-provided data quality level."""

    normalized = (value or "none").strip().lower()
    normalized = LEVEL_ALIASES.get(normalized, normalized)
    if normalized not in SUPPORTED_DATA_QUALITY_LEVELS:
        raise ValueError(
            "Unsupported data quality level "
            f"{value!r}. Expected one of {', '.join(SUPPORTED_DATA_QUALITY_LEVELS)}."
        )
    return normalized


def adjust_data_quality_level(level: str, offset: int) -> str:
    """Shift a named level up or down within the supported range."""

    normalized = normalize_data_quality_level(level)
    index = SUPPORTED_DATA_QUALITY_LEVELS.index(normalized)
    adjusted_index = max(
        0,
        min(len(SUPPORTED_DATA_QUALITY_LEVELS) - 1, index + offset),
    )
    return SUPPORTED_DATA_QUALITY_LEVELS[adjusted_index]


DEFAULT_LEVEL_PROFILES: Mapping[str, DataQualityLevelProfile] = {
    "none": DataQualityLevelProfile(
        field_level_issue_rate=DataQualityRateBand(0.00, 0.00),
        row_level_issue_rate=DataQualityRateBand(0.00, 0.00),
        categorical_variant_rate=DataQualityRateBand(0.00, 0.00),
        duplicate_like_row_rate=DataQualityRateBand(0.00, 0.00),
    ),
    "low": DataQualityLevelProfile(
        field_level_issue_rate=DataQualityRateBand(0.10, 0.50),
        row_level_issue_rate=DataQualityRateBand(0.05, 0.25),
        categorical_variant_rate=DataQualityRateBand(0.10, 0.30),
        duplicate_like_row_rate=DataQualityRateBand(0.01, 0.05),
    ),
    "medium": DataQualityLevelProfile(
        field_level_issue_rate=DataQualityRateBand(0.50, 2.00),
        row_level_issue_rate=DataQualityRateBand(0.25, 1.00),
        categorical_variant_rate=DataQualityRateBand(0.30, 1.00),
        duplicate_like_row_rate=DataQualityRateBand(0.05, 0.20),
    ),
    "high": DataQualityLevelProfile(
        field_level_issue_rate=DataQualityRateBand(2.00, 5.00),
        row_level_issue_rate=DataQualityRateBand(1.00, 3.00),
        categorical_variant_rate=DataQualityRateBand(1.00, 3.00),
        duplicate_like_row_rate=DataQualityRateBand(0.20, 0.75),
    ),
    "very_high": DataQualityLevelProfile(
        field_level_issue_rate=DataQualityRateBand(5.00, 10.00),
        row_level_issue_rate=DataQualityRateBand(3.00, 6.00),
        categorical_variant_rate=DataQualityRateBand(3.00, 6.00),
        duplicate_like_row_rate=DataQualityRateBand(0.75, 1.50),
    ),
}


DEFAULT_TABLE_RULES: Mapping[str, DataQualityTableRule] = {
    "clubs": DataQualityTableRule(
        issue_profile="medium",
        allowed_issue_types=(
            ISSUE_TYPE_MISSING_OPTIONAL_VALUES,
            ISSUE_TYPE_CATEGORICAL_VARIANTS,
            ISSUE_TYPE_SOFT_JOIN_AMBIGUITY,
            ISSUE_TYPE_DUPLICATE_LIKE_ROWS,
        ),
    ),
    "club_memberships": DataQualityTableRule(
        issue_profile="low",
        allowed_issue_types=(
            ISSUE_TYPE_MISSING_OPTIONAL_VALUES,
            ISSUE_TYPE_CATEGORICAL_VARIANTS,
        ),
    ),
    "match_games": DataQualityTableRule(
        issue_profile="low",
        allowed_issue_types=(
            ISSUE_TYPE_NUMERIC_OUTLIERS,
        ),
    ),
    "match_team_players": DataQualityTableRule(
        issue_profile="low",
        allowed_issue_types=(
            ISSUE_TYPE_ROUNDING_VARIANTS,
        ),
    ),
    "match_teams": DataQualityTableRule(
        issue_profile="low",
        allowed_issue_types=(
            ISSUE_TYPE_ROUNDING_VARIANTS,
            ISSUE_TYPE_NUMERIC_OUTLIERS,
        ),
    ),
    "matches": DataQualityTableRule(
        issue_profile="medium",
        allowed_issue_types=(
            ISSUE_TYPE_CATEGORICAL_VARIANTS,
            ISSUE_TYPE_MISSING_OPTIONAL_VALUES,
            ISSUE_TYPE_DUPLICATE_LIKE_ROWS,
        ),
    ),
    "monthly_batches": DataQualityTableRule(
        issue_profile="low",
        allowed_issue_types=(
            ISSUE_TYPE_NUMERIC_OUTLIERS,
        ),
    ),
    "player_assessment_history": DataQualityTableRule(
        issue_profile="low",
        allowed_issue_types=(
            ISSUE_TYPE_MISSING_OPTIONAL_VALUES,
            ISSUE_TYPE_NUMERIC_OUTLIERS,
            ISSUE_TYPE_ROUNDING_VARIANTS,
            ISSUE_TYPE_TIMESTAMP_JITTER,
        ),
    ),
    "player_master": DataQualityTableRule(
        issue_profile="medium",
        allowed_issue_types=(
            ISSUE_TYPE_NAME_CASE_VARIANTS,
            ISSUE_TYPE_MISSING_OPTIONAL_VALUES,
            ISSUE_TYPE_CATEGORICAL_VARIANTS,
            ISSUE_TYPE_ROUNDING_VARIANTS,
            ISSUE_TYPE_TIMESTAMP_JITTER,
        ),
    ),
    "player_registrations": DataQualityTableRule(
        issue_profile="low",
        allowed_issue_types=(
            ISSUE_TYPE_CATEGORICAL_VARIANTS,
            ISSUE_TYPE_MISSING_OPTIONAL_VALUES,
            ISSUE_TYPE_ROUNDING_VARIANTS,
        ),
    ),
    "regions": DataQualityTableRule(
        issue_profile="low",
        allowed_issue_types=(
            ISSUE_TYPE_CATEGORICAL_VARIANTS,
            ISSUE_TYPE_SOFT_JOIN_AMBIGUITY,
        ),
    ),
    "team_memberships": DataQualityTableRule(
        issue_profile="none",
        allowed_issue_types=(),
    ),
    "teams": DataQualityTableRule(
        issue_profile="low",
        allowed_issue_types=(
            ISSUE_TYPE_CATEGORICAL_VARIANTS,
            ISSUE_TYPE_SOFT_JOIN_AMBIGUITY,
            ISSUE_TYPE_DUPLICATE_LIKE_ROWS,
        ),
    ),
}


def build_default_data_quality_config(
    *,
    level: str,
    random_seed: int = 12345,
) -> DataQualityInjectionConfig:
    """Return the default injection configuration for one export request."""

    normalized_level = normalize_data_quality_level(level)
    return DataQualityInjectionConfig(
        enabled=normalized_level != "none",
        level=normalized_level,
        random_seed=int(random_seed),
        apply_to_release_types=STUDENT_RELEASE_TYPES,
        write_instructor_manifest=True,
        write_student_visible_quality_summary=False,
        monthly_release_level_offset=-1,
        global_limits=DataQualityGlobalLimits(),
        table_rules=DEFAULT_TABLE_RULES,
    )


def level_profile(level: str) -> DataQualityLevelProfile:
    """Return the configured frequency profile for one normalized level."""

    return DEFAULT_LEVEL_PROFILES[normalize_data_quality_level(level)]
HISTORICAL_BASELINE_RELEASE_TYPE = "historical_baseline"
MONTHLY_INCREMENTAL_RELEASE_TYPE = "monthly_incremental"
