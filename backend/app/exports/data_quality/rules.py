"""Rule registry for export-layer data quality injection."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import math
import random
from typing import Any, Mapping

from .config import (
    ISSUE_TYPE_CATEGORICAL_VARIANTS,
    ISSUE_TYPE_DELAYED_RATING_UPDATES,
    ISSUE_TYPE_DUPLICATE_LIKE_ROWS,
    ISSUE_TYPE_FORMATTING_VARIANTS,
    ISSUE_TYPE_MISSING_OPTIONAL_VALUES,
    ISSUE_TYPE_NAME_CASE_VARIANTS,
    ISSUE_TYPE_NUMERIC_OUTLIERS,
    ISSUE_TYPE_ROUNDING_VARIANTS,
    ISSUE_TYPE_SOFT_JOIN_AMBIGUITY,
    ISSUE_TYPE_TIMESTAMP_JITTER,
)


FIELD_RATE_ISSUES: frozenset[str] = frozenset(
    {
        ISSUE_TYPE_MISSING_OPTIONAL_VALUES,
        ISSUE_TYPE_NUMERIC_OUTLIERS,
        ISSUE_TYPE_ROUNDING_VARIANTS,
        ISSUE_TYPE_TIMESTAMP_JITTER,
        ISSUE_TYPE_DELAYED_RATING_UPDATES,
    }
)

CATEGORICAL_RATE_ISSUES: frozenset[str] = frozenset(
    {
        ISSUE_TYPE_CATEGORICAL_VARIANTS,
        ISSUE_TYPE_FORMATTING_VARIANTS,
        ISSUE_TYPE_NAME_CASE_VARIANTS,
        ISSUE_TYPE_SOFT_JOIN_AMBIGUITY,
    }
)

ROW_RATE_ISSUES: frozenset[str] = frozenset({ISSUE_TYPE_DUPLICATE_LIKE_ROWS})


TABLE_PRIMARY_KEY: Mapping[str, str] = {
    "player_master": "player_id",
}

PROTECTED_DATE_COLUMNS: frozenset[str] = frozenset(
    {
        "assessment_date",
        "batch_month",
        "birth_date",
        "completed_at",
        "dissolution_date",
        "end_date",
        "formation_date",
        "founding_date",
        "joined_date",
        "left_date",
        "match_date",
        "rating_date",
        "registration_date",
        "registration_month",
        "snapshot_month",
        "start_date",
    }
)

TABLE_REQUIRED_COLUMNS: Mapping[str, tuple[str, ...]] = {
    "clubs": ("id", "club_name", "region_id"),
    "club_memberships": ("id", "player_id", "club_id", "start_date", "is_primary"),
    "match_games": (
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
    "match_team_players": (
        "id",
        "match_team_id",
        "player_id",
        "player_position",
        "player_rating_at_match",
    ),
    "match_teams": ("id", "match_id", "team_number", "team_score", "average_team_rating"),
    "matches": (
        "id",
        "match_date",
        "match_type",
        "match_format",
        "total_points_played",
        "batch_id",
    ),
    "monthly_batches": (
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
    "player_assessment_history": (
        "id",
        "player_id",
        "assessment_date",
        "assessment_type",
        "assessment_value",
        "batch_id",
    ),
    "player_master": (
        "player_id",
        "external_player_key",
        "first_name",
        "last_name",
        "gender",
        "birth_date",
        "home_region_id",
        "registration_date",
        "player_status",
        "snapshot_month",
    ),
    "player_registrations": (
        "id",
        "player_id",
        "batch_id",
        "registration_month",
        "initial_rating_value",
        "initial_confidence_score",
    ),
    "regions": ("id", "country_code", "region_type", "region_name", "population"),
    "team_memberships": ("id", "team_id", "player_id", "player_position", "joined_date"),
    "teams": ("id", "team_type", "team_status", "country_code", "formation_date"),
}

MISSING_VALUE_ELIGIBILITY: Mapping[str, tuple[str, ...]] = {
    "clubs": ("club_type", "competitiveness_level"),
    "club_memberships": ("membership_type",),
    "matches": ("court_type", "match_format"),
    "player_assessment_history": ("confidence_score",),
    "player_master": ("dominant_hand",),
    "player_registrations": ("registration_source",),
    "regions": ("state_province_code",),
}

CATEGORICAL_VARIANT_ELIGIBILITY: Mapping[str, tuple[str, ...]] = {
    "clubs": ("club_type", "competitiveness_level"),
    "club_memberships": ("membership_type",),
    "matches": ("match_type", "court_type", "match_format"),
    "player_master": ("gender", "dominant_hand", "player_status"),
    "player_registrations": ("registration_source",),
    "regions": ("region_type",),
    "teams": ("team_type", "team_status"),
}

FORMATTING_VARIANT_ELIGIBILITY: Mapping[str, tuple[str, ...]] = {
    "clubs": ("club_name",),
    "player_master": ("first_name", "last_name"),
    "regions": ("region_name",),
}

ROUNDING_VARIANT_ELIGIBILITY: Mapping[str, tuple[str, ...]] = {
    "match_team_players": ("player_rating_at_match",),
    "match_teams": ("average_team_rating",),
    "player_assessment_history": ("assessment_value", "confidence_score"),
    "player_master": (
        "rating_value",
        "confidence_score",
        "volatility_score",
        "global_percentile",
    ),
    "player_registrations": ("initial_rating_value", "initial_confidence_score"),
}

NUMERIC_OUTLIER_BOUNDS: Mapping[str, Mapping[str, tuple[float, float]]] = {
    "match_games": {
        "actual_team_one_score_share": (0.0, 1.0),
    },
    "match_teams": {
        "average_team_rating": (0.0, 5000.0),
    },
    "matches": {
        "total_points_played": (0.0, 200.0),
    },
    "monthly_batches": {
        "active_player_count_start": (0.0, 1_000_000.0),
        "new_player_count": (0.0, 1_000_000.0),
        "active_player_count_end": (0.0, 1_000_000.0),
        "match_count_generated": (0.0, 1_000_000.0),
        "rating_update_count": (0.0, 1_000_000.0),
        "assessment_update_count": (0.0, 1_000_000.0),
    },
    "player_assessment_history": {
        "assessment_value": (0.0, 5000.0),
        "confidence_score": (0.0, 1.0),
    },
    "player_master": {
        "rating_value": (0.0, 5000.0),
        "confidence_score": (0.0, 1.0),
        "volatility_score": (0.0, 1.0),
        "global_percentile": (0.0, 1.0),
        "match_count_used": (0.0, 1_000_000.0),
    },
    "player_registrations": {
        "initial_rating_value": (0.0, 5000.0),
        "initial_confidence_score": (0.0, 1.0),
    },
}

TIMESTAMP_JITTER_ELIGIBILITY: Mapping[str, tuple[str, ...]] = {
    "player_assessment_history": ("assessment_date",),
    "player_master": ("rating_date",),
}


def primary_key_column(table_name: str) -> str:
    """Return the primary key column for one exported table."""

    return TABLE_PRIMARY_KEY.get(table_name, "id")


def protected_columns(table_name: str) -> frozenset[str]:
    """Return columns that must never be mutated for the given table."""

    projection = _projection_by_table()[table_name]
    protected = {primary_key_column(table_name)}
    protected.update(
        relationship.child_column
        for relationship in projection.relationship_validations
    )
    protected.update(
        column_name
        for column_name in projection.included_columns
        if column_name.endswith("_id")
    )
    protected.update(
        column_name
        for column_name in projection.included_columns
        if column_name in PROTECTED_DATE_COLUMNS
    )
    return frozenset(protected)


def required_columns(table_name: str) -> frozenset[str]:
    """Return required non-null columns for the exported table."""

    return frozenset(TABLE_REQUIRED_COLUMNS.get(table_name, (primary_key_column(table_name),)))


def eligible_columns(table_name: str, issue_type: str) -> tuple[str, ...]:
    """Return the eligible columns for a rule on one table."""

    registry = {
        ISSUE_TYPE_MISSING_OPTIONAL_VALUES: MISSING_VALUE_ELIGIBILITY,
        ISSUE_TYPE_CATEGORICAL_VARIANTS: CATEGORICAL_VARIANT_ELIGIBILITY,
        ISSUE_TYPE_FORMATTING_VARIANTS: FORMATTING_VARIANT_ELIGIBILITY,
        ISSUE_TYPE_NAME_CASE_VARIANTS: FORMATTING_VARIANT_ELIGIBILITY,
        ISSUE_TYPE_SOFT_JOIN_AMBIGUITY: FORMATTING_VARIANT_ELIGIBILITY,
        ISSUE_TYPE_ROUNDING_VARIANTS: ROUNDING_VARIANT_ELIGIBILITY,
        ISSUE_TYPE_NUMERIC_OUTLIERS: {
            name: tuple(bounds.keys()) for name, bounds in NUMERIC_OUTLIER_BOUNDS.items()
        },
        ISSUE_TYPE_TIMESTAMP_JITTER: TIMESTAMP_JITTER_ELIGIBILITY,
        ISSUE_TYPE_DELAYED_RATING_UPDATES: {},
        ISSUE_TYPE_DUPLICATE_LIKE_ROWS: {},
    }
    columns = registry.get(issue_type, {})
    return tuple(
        column_name
        for column_name in columns.get(table_name, ())
        if column_name in _projection_by_table()[table_name].included_columns
        and column_name not in protected_columns(table_name)
    )


def categorical_variant(value: Any, rng: random.Random) -> str | None:
    """Return a controlled categorical/string variant."""

    if value is None:
        return None
    text = str(value)
    candidates = {
        text.lower(),
        text.upper(),
        text.title(),
        text.replace("_", " "),
        text.replace("_", "-"),
    }
    candidates.discard(text)
    return _sample_variant(sorted(candidates), rng)


def formatting_variant(value: Any, rng: random.Random) -> str | None:
    """Return a realistic formatting variant for a descriptive string."""

    if value is None:
        return None
    text = str(value)
    candidates = {
        f"{text} ",
        f" {text}",
        text.replace("&", "and"),
        text.replace("and", "&"),
        text.replace("-", " "),
        text.replace(".", ""),
    }
    candidates.discard(text)
    candidates.discard("")
    return _sample_variant(sorted(candidates), rng)


def name_case_variant(value: Any, rng: random.Random) -> str | None:
    """Return a controlled case/spacing variant for a person name."""

    if value is None:
        return None
    text = str(value)
    candidates = {
        text.upper(),
        text.lower(),
        text.title(),
        f"{text} ",
    }
    candidates.discard(text)
    return _sample_variant(sorted(candidates), rng)


def rounding_variant(value: Any, rng: random.Random) -> float | int | None:
    """Return a float rounded to an inconsistent precision."""

    if value is None or isinstance(value, bool):
        return value
    if not isinstance(value, (int, float)):
        return value
    decimals = rng.choice((1, 2, 3))
    rounded = round(float(value), decimals)
    if isinstance(value, int):
        return int(round(rounded))
    return rounded


def numeric_outlier(
    table_name: str,
    column_name: str,
    value: Any,
    rng: random.Random,
) -> float | int | None:
    """Return a bounded but suspicious numeric variant."""

    if value is None or isinstance(value, bool):
        return value
    if not isinstance(value, (int, float)):
        return value
    lower, upper = NUMERIC_OUTLIER_BOUNDS[table_name][column_name]
    if math.isclose(lower, upper):
        return value
    scale = rng.uniform(1.15, 1.65)
    candidate = float(value) * scale
    candidate = min(max(candidate, lower), upper)
    if isinstance(value, int):
        return int(round(candidate))
    return round(candidate, 3)


def timestamp_jitter(value: Any, rng: random.Random) -> date | datetime | str | None:
    """Return a date/datetime shifted within a very small bounded window."""

    if value is None:
        return None
    shift_days = rng.choice((-1, 1))
    if isinstance(value, datetime):
        return value + timedelta(days=shift_days)
    if isinstance(value, date):
        return value + timedelta(days=shift_days)
    return value


def delayed_rating_update(row: Mapping[str, Any]) -> Mapping[str, Any]:
    """Placeholder for tables that expose rating-history records."""

    return row


def next_primary_key(rows: list[dict[str, Any]], table_name: str) -> int:
    """Return the next integer primary key value for the table."""

    column_name = primary_key_column(table_name)
    current_values = [
        int(row[column_name])
        for row in rows
        if row.get(column_name) is not None
    ]
    return (max(current_values) if current_values else 0) + 1


def _sample_variant(candidates: list[str], rng: random.Random) -> str | None:
    if not candidates:
        return None
    return candidates[rng.randrange(len(candidates))]


def _projection_by_table():
    from app.exports.student_dataset.projection import PROJECTION_BY_TABLE

    return PROJECTION_BY_TABLE
