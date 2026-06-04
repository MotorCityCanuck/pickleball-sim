"""Reusable SQL-backed realism audit queries for generated data."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import json
from typing import Any, Callable, Literal, Mapping, Sequence

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.default_configuration import DEFAULT_CONFIG_PAYLOAD
from app.models import GenerationRun, MonthlyBatch


AuditScope = Literal["generation_run", "batch"]
RowPostProcessor = Callable[
    [tuple[dict[str, Any], ...], Mapping[str, Any]],
    tuple[dict[str, Any], ...],
]


@dataclass(frozen=True)
class RealismAuditQuery:
    """One named audit query with scope and parameter requirements."""

    name: str
    scope: AuditScope
    description: str
    sql: str | Mapping[str, str]
    required_params: tuple[str, ...]
    tags: tuple[str, ...] = ()
    category: str = "general"
    related_config_keys: tuple[str, ...] = ()
    post_process: RowPostProcessor | None = None

    def sql_for_dialect(self, dialect_name: str) -> str:
        """Return SQL compatible with the current database dialect."""
        if isinstance(self.sql, str):
            return self.sql
        if dialect_name in self.sql:
            return self.sql[dialect_name]
        if "default" in self.sql:
            return self.sql["default"]
        supported = ", ".join(sorted(self.sql))
        raise ValueError(
            f"Audit query {self.name!r} does not support dialect {dialect_name!r}. "
            f"Supported dialects: {supported}."
        )


@dataclass(frozen=True)
class RealismAuditResult:
    """Rows returned by one realism audit query."""

    query: RealismAuditQuery
    rows: tuple[dict[str, Any], ...]


def _distribution_with_targets(
    rows: tuple[dict[str, Any], ...],
    params: Mapping[str, Any],
    *,
    key_field: str,
    pct_field: str,
    target_map_param: str,
    count_field: str,
) -> tuple[dict[str, Any], ...]:
    target_map = params.get(target_map_param)
    if not isinstance(target_map, Mapping):
        return rows

    row_map = {str(row.get(key_field)): row for row in rows}
    ordered_keys = [str(key) for key in target_map]
    ordered_keys.extend(
        key for key in row_map if key not in set(ordered_keys)
    )

    processed: list[dict[str, Any]] = []
    for key in ordered_keys:
        row = dict(row_map.get(key, {key_field: key, count_field: 0, pct_field: 0.0}))
        configured_pct = _float_or_none(target_map.get(key))
        observed_pct = _float_or_none(row.get(pct_field))
        row["configured_pct"] = configured_pct
        row["pct_point_drift"] = (
            round(observed_pct - configured_pct, 2)
            if observed_pct is not None and configured_pct is not None
            else None
        )
        processed.append(row)
    return tuple(processed)


def _post_process_player_status_distribution(
    rows: tuple[dict[str, Any], ...],
    params: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    return _distribution_with_targets(
        rows,
        params,
        key_field="player_status",
        pct_field="player_pct",
        target_map_param="player_status_target_pcts",
        count_field="player_count",
    )


def _post_process_player_gender_distribution(
    rows: tuple[dict[str, Any], ...],
    params: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    return _distribution_with_targets(
        rows,
        params,
        key_field="gender",
        pct_field="player_pct",
        target_map_param="gender_target_pcts",
        count_field="player_count",
    )


def _post_process_player_age_distribution(
    rows: tuple[dict[str, Any], ...],
    params: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    return _distribution_with_targets(
        rows,
        params,
        key_field="age_bucket",
        pct_field="player_pct",
        target_map_param="age_bucket_target_pcts",
        count_field="player_count",
    )


def _post_process_match_type_distribution(
    rows: tuple[dict[str, Any], ...],
    params: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    return _distribution_with_targets(
        rows,
        params,
        key_field="match_type",
        pct_field="match_pct",
        target_map_param="match_type_target_pcts",
        count_field="match_count",
    )


PLAYER_AGE_DISTRIBUTION_SQL = {
    "sqlite": """
        WITH player_ages AS (
            SELECT
                CASE
                    WHEN CAST((julianday(pr.registration_month) - julianday(p.birth_date)) / 365.2425 AS INTEGER) < 18
                        THEN 'under_18'
                    WHEN CAST((julianday(pr.registration_month) - julianday(p.birth_date)) / 365.2425 AS INTEGER) < 30
                        THEN '18_29'
                    WHEN CAST((julianday(pr.registration_month) - julianday(p.birth_date)) / 365.2425 AS INTEGER) < 45
                        THEN '30_44'
                    WHEN CAST((julianday(pr.registration_month) - julianday(p.birth_date)) / 365.2425 AS INTEGER) < 60
                        THEN '45_59'
                    WHEN CAST((julianday(pr.registration_month) - julianday(p.birth_date)) / 365.2425 AS INTEGER) < 75
                        THEN '60_74'
                    ELSE '75_plus'
                END AS age_bucket
            FROM players p
            JOIN player_registrations pr ON pr.player_id = p.id
            WHERE p.generation_run_id = :generation_run_id
        )
        SELECT
            age_bucket,
            COUNT(*) AS player_count,
            ROUND(
                100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0),
                2
            ) AS player_pct
        FROM player_ages
        GROUP BY age_bucket
        ORDER BY
            CASE age_bucket
                WHEN 'under_18' THEN 0
                WHEN '18_29' THEN 1
                WHEN '30_44' THEN 2
                WHEN '45_59' THEN 3
                WHEN '60_74' THEN 4
                ELSE 5
            END
    """,
    "postgresql": """
        WITH player_ages AS (
            SELECT
                CASE
                    WHEN CAST(EXTRACT(YEAR FROM age(pr.registration_month, p.birth_date)) AS INTEGER) < 18
                        THEN 'under_18'
                    WHEN CAST(EXTRACT(YEAR FROM age(pr.registration_month, p.birth_date)) AS INTEGER) < 30
                        THEN '18_29'
                    WHEN CAST(EXTRACT(YEAR FROM age(pr.registration_month, p.birth_date)) AS INTEGER) < 45
                        THEN '30_44'
                    WHEN CAST(EXTRACT(YEAR FROM age(pr.registration_month, p.birth_date)) AS INTEGER) < 60
                        THEN '45_59'
                    WHEN CAST(EXTRACT(YEAR FROM age(pr.registration_month, p.birth_date)) AS INTEGER) < 75
                        THEN '60_74'
                    ELSE '75_plus'
                END AS age_bucket
            FROM players p
            JOIN player_registrations pr ON pr.player_id = p.id
            WHERE p.generation_run_id = :generation_run_id
        )
        SELECT
            age_bucket,
            COUNT(*) AS player_count,
            ROUND(
                100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0),
                2
            ) AS player_pct
        FROM player_ages
        GROUP BY age_bucket
        ORDER BY
            CASE age_bucket
                WHEN 'under_18' THEN 0
                WHEN '18_29' THEN 1
                WHEN '30_44' THEN 2
                WHEN '45_59' THEN 3
                WHEN '60_74' THEN 4
                ELSE 5
            END
    """,
}


PLAYER_REGISTRATION_AGE_DISTRIBUTION_SQL = {
    "sqlite": """
        WITH player_ages AS (
            SELECT
                CASE
                    WHEN CAST((julianday(p.registration_date) - julianday(p.birth_date)) / 365.2425 AS INTEGER) < 12
                        THEN 'under_12'
                    WHEN CAST((julianday(p.registration_date) - julianday(p.birth_date)) / 365.2425 AS INTEGER) < 18
                        THEN '12_17'
                    WHEN CAST((julianday(p.registration_date) - julianday(p.birth_date)) / 365.2425 AS INTEGER) < 30
                        THEN '18_29'
                    WHEN CAST((julianday(p.registration_date) - julianday(p.birth_date)) / 365.2425 AS INTEGER) < 45
                        THEN '30_44'
                    WHEN CAST((julianday(p.registration_date) - julianday(p.birth_date)) / 365.2425 AS INTEGER) < 60
                        THEN '45_59'
                    WHEN CAST((julianday(p.registration_date) - julianday(p.birth_date)) / 365.2425 AS INTEGER) < 75
                        THEN '60_74'
                    ELSE '75_plus'
                END AS age_bucket
            FROM players p
            WHERE p.generation_run_id = :generation_run_id
        )
        SELECT
            age_bucket,
            COUNT(*) AS player_count,
            ROUND(
                100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0),
                2
            ) AS player_pct
        FROM player_ages
        GROUP BY age_bucket
        ORDER BY
            CASE age_bucket
                WHEN 'under_12' THEN 0
                WHEN '12_17' THEN 1
                WHEN '18_29' THEN 2
                WHEN '30_44' THEN 3
                WHEN '45_59' THEN 4
                WHEN '60_74' THEN 5
                ELSE 6
            END
    """,
    "postgresql": """
        WITH player_ages AS (
            SELECT
                CASE
                    WHEN CAST(EXTRACT(YEAR FROM age(p.registration_date, p.birth_date)) AS INTEGER) < 12
                        THEN 'under_12'
                    WHEN CAST(EXTRACT(YEAR FROM age(p.registration_date, p.birth_date)) AS INTEGER) < 18
                        THEN '12_17'
                    WHEN CAST(EXTRACT(YEAR FROM age(p.registration_date, p.birth_date)) AS INTEGER) < 30
                        THEN '18_29'
                    WHEN CAST(EXTRACT(YEAR FROM age(p.registration_date, p.birth_date)) AS INTEGER) < 45
                        THEN '30_44'
                    WHEN CAST(EXTRACT(YEAR FROM age(p.registration_date, p.birth_date)) AS INTEGER) < 60
                        THEN '45_59'
                    WHEN CAST(EXTRACT(YEAR FROM age(p.registration_date, p.birth_date)) AS INTEGER) < 75
                        THEN '60_74'
                    ELSE '75_plus'
                END AS age_bucket
            FROM players p
            WHERE p.generation_run_id = :generation_run_id
        )
        SELECT
            age_bucket,
            COUNT(*) AS player_count,
            ROUND(
                100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0),
                2
            ) AS player_pct
        FROM player_ages
        GROUP BY age_bucket
        ORDER BY
            CASE age_bucket
                WHEN 'under_12' THEN 0
                WHEN '12_17' THEN 1
                WHEN '18_29' THEN 2
                WHEN '30_44' THEN 3
                WHEN '45_59' THEN 4
                WHEN '60_74' THEN 5
                ELSE 6
            END
    """,
}


MATCH_DAY_OF_WEEK_SQL = {
    "sqlite": """
        WITH dated_matches AS (
            SELECT
                CAST(strftime('%w', m.match_date) AS INTEGER) AS day_number
            FROM matches m
            WHERE m.batch_id = :batch_id
        )
        SELECT
            day_number,
            CASE day_number
                WHEN 0 THEN 'Sunday'
                WHEN 1 THEN 'Monday'
                WHEN 2 THEN 'Tuesday'
                WHEN 3 THEN 'Wednesday'
                WHEN 4 THEN 'Thursday'
                WHEN 5 THEN 'Friday'
                ELSE 'Saturday'
            END AS day_name,
            COUNT(*) AS match_count,
            ROUND(
                100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0),
                2
            ) AS match_pct
        FROM dated_matches
        GROUP BY day_number
        ORDER BY day_number
    """,
    "postgresql": """
        WITH dated_matches AS (
            SELECT
                CAST(EXTRACT(DOW FROM m.match_date) AS INTEGER) AS day_number
            FROM matches m
            WHERE m.batch_id = :batch_id
        )
        SELECT
            day_number,
            CASE day_number
                WHEN 0 THEN 'Sunday'
                WHEN 1 THEN 'Monday'
                WHEN 2 THEN 'Tuesday'
                WHEN 3 THEN 'Wednesday'
                WHEN 4 THEN 'Thursday'
                WHEN 5 THEN 'Friday'
                ELSE 'Saturday'
            END AS day_name,
            COUNT(*) AS match_count,
            ROUND(
                100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0),
                2
            ) AS match_pct
        FROM dated_matches
        GROUP BY day_number
        ORDER BY day_number
    """,
}


FIRST_NAME_ALIGNMENT_SQL = {
    "sqlite": """
        WITH player_context AS (
            SELECT
                p.id AS player_id,
                p.first_name,
                p.gender,
                CAST(strftime('%Y', p.birth_date) AS INTEGER) AS birth_year,
                r.country_code,
                r.state_province_code
            FROM players p
            LEFT JOIN regions r
                ON r.id = p.home_region_id
            WHERE p.generation_run_id = :generation_run_id
        ),
        exact_reference AS (
            SELECT DISTINCT
                fn.country_code,
                fn.state_province_code,
                fn.birth_year,
                fn.gender,
                fn.first_name
            FROM first_names fn
        ),
        state_gender_reference AS (
            SELECT DISTINCT
                fn.country_code,
                fn.state_province_code,
                fn.gender,
                fn.first_name
            FROM first_names fn
        ),
        country_year_reference AS (
            SELECT DISTINCT
                fn.country_code,
                fn.birth_year,
                fn.gender,
                fn.first_name
            FROM first_names fn
        ),
        country_gender_reference AS (
            SELECT DISTINCT
                fn.country_code,
                fn.gender,
                fn.first_name
            FROM first_names fn
        ),
        aligned AS (
            SELECT
                CASE
                    WHEN pc.country_code IS NULL OR pc.gender IS NULL THEN 'missing_reference'
                    WHEN exact_ref.first_name IS NOT NULL THEN 'exact_state_year'
                    WHEN state_ref.first_name IS NOT NULL THEN 'state_gender_other_year'
                    WHEN country_year_ref.first_name IS NOT NULL THEN 'country_year_other_state'
                    WHEN country_ref.first_name IS NOT NULL THEN 'country_gender_other_state_year'
                    ELSE 'missing_reference'
                END AS alignment_bucket
            FROM player_context pc
            LEFT JOIN exact_reference exact_ref
                ON exact_ref.country_code = pc.country_code
                AND exact_ref.state_province_code = pc.state_province_code
                AND exact_ref.birth_year = pc.birth_year
                AND exact_ref.gender = pc.gender
                AND exact_ref.first_name = pc.first_name
            LEFT JOIN state_gender_reference state_ref
                ON state_ref.country_code = pc.country_code
                AND state_ref.state_province_code = pc.state_province_code
                AND state_ref.gender = pc.gender
                AND state_ref.first_name = pc.first_name
            LEFT JOIN country_year_reference country_year_ref
                ON country_year_ref.country_code = pc.country_code
                AND country_year_ref.birth_year = pc.birth_year
                AND country_year_ref.gender = pc.gender
                AND country_year_ref.first_name = pc.first_name
            LEFT JOIN country_gender_reference country_ref
                ON country_ref.country_code = pc.country_code
                AND country_ref.gender = pc.gender
                AND country_ref.first_name = pc.first_name
        )
        SELECT
            alignment_bucket,
            COUNT(*) AS player_count,
            ROUND(
                100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0),
                2
            ) AS player_pct
        FROM aligned
        GROUP BY alignment_bucket
        ORDER BY
            CASE alignment_bucket
                WHEN 'exact_state_year' THEN 0
                WHEN 'state_gender_other_year' THEN 1
                WHEN 'country_year_other_state' THEN 2
                WHEN 'country_gender_other_state_year' THEN 3
                ELSE 4
            END
    """,
    "postgresql": """
        WITH player_context AS (
            SELECT
                p.id AS player_id,
                p.first_name,
                p.gender,
                CAST(EXTRACT(YEAR FROM p.birth_date) AS INTEGER) AS birth_year,
                r.country_code,
                r.state_province_code
            FROM players p
            LEFT JOIN regions r
                ON r.id = p.home_region_id
            WHERE p.generation_run_id = :generation_run_id
        ),
        exact_reference AS (
            SELECT DISTINCT
                fn.country_code,
                fn.state_province_code,
                fn.birth_year,
                fn.gender,
                fn.first_name
            FROM first_names fn
        ),
        state_gender_reference AS (
            SELECT DISTINCT
                fn.country_code,
                fn.state_province_code,
                fn.gender,
                fn.first_name
            FROM first_names fn
        ),
        country_year_reference AS (
            SELECT DISTINCT
                fn.country_code,
                fn.birth_year,
                fn.gender,
                fn.first_name
            FROM first_names fn
        ),
        country_gender_reference AS (
            SELECT DISTINCT
                fn.country_code,
                fn.gender,
                fn.first_name
            FROM first_names fn
        ),
        aligned AS (
            SELECT
                CASE
                    WHEN pc.country_code IS NULL OR pc.gender IS NULL THEN 'missing_reference'
                    WHEN exact_ref.first_name IS NOT NULL THEN 'exact_state_year'
                    WHEN state_ref.first_name IS NOT NULL THEN 'state_gender_other_year'
                    WHEN country_year_ref.first_name IS NOT NULL THEN 'country_year_other_state'
                    WHEN country_ref.first_name IS NOT NULL THEN 'country_gender_other_state_year'
                    ELSE 'missing_reference'
                END AS alignment_bucket
            FROM player_context pc
            LEFT JOIN exact_reference exact_ref
                ON exact_ref.country_code = pc.country_code
                AND exact_ref.state_province_code = pc.state_province_code
                AND exact_ref.birth_year = pc.birth_year
                AND exact_ref.gender = pc.gender
                AND exact_ref.first_name = pc.first_name
            LEFT JOIN state_gender_reference state_ref
                ON state_ref.country_code = pc.country_code
                AND state_ref.state_province_code = pc.state_province_code
                AND state_ref.gender = pc.gender
                AND state_ref.first_name = pc.first_name
            LEFT JOIN country_year_reference country_year_ref
                ON country_year_ref.country_code = pc.country_code
                AND country_year_ref.birth_year = pc.birth_year
                AND country_year_ref.gender = pc.gender
                AND country_year_ref.first_name = pc.first_name
            LEFT JOIN country_gender_reference country_ref
                ON country_ref.country_code = pc.country_code
                AND country_ref.gender = pc.gender
                AND country_ref.first_name = pc.first_name
        )
        SELECT
            alignment_bucket,
            COUNT(*) AS player_count,
            ROUND(
                100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0),
                2
            ) AS player_pct
        FROM aligned
        GROUP BY alignment_bucket
        ORDER BY
            CASE alignment_bucket
                WHEN 'exact_state_year' THEN 0
                WHEN 'state_gender_other_year' THEN 1
                WHEN 'country_year_other_state' THEN 2
                WHEN 'country_gender_other_state_year' THEN 3
                ELSE 4
            END
    """,
}


REALISM_AUDIT_QUERIES: tuple[RealismAuditQuery, ...] = (
    RealismAuditQuery(
        name="player_roster_summary",
        scope="generation_run",
        category="players",
        description="Top-line player, status, and club-affiliation counts for one generation run.",
        sql="""
            WITH membership_counts AS (
                SELECT
                    cm.player_id,
                    SUM(CASE WHEN cm.is_primary THEN 1 ELSE 0 END) AS primary_membership_count,
                    COUNT(*) AS total_membership_count
                FROM club_memberships cm
                WHERE cm.generation_run_id = :generation_run_id
                GROUP BY cm.player_id
            )
            SELECT
                p.generation_run_id,
                COUNT(*) AS player_count,
                SUM(CASE WHEN p.player_status = 'ACTIVE' THEN 1 ELSE 0 END) AS active_player_count,
                SUM(CASE WHEN COALESCE(mc.primary_membership_count, 0) = 0 THEN 1 ELSE 0 END) AS unaffiliated_player_count,
                SUM(CASE WHEN COALESCE(mc.total_membership_count, 0) > 1 THEN 1 ELSE 0 END) AS multi_club_player_count,
                ROUND(
                    100.0 * SUM(CASE WHEN COALESCE(mc.primary_membership_count, 0) = 0 THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(*), 0),
                    2
                ) AS unaffiliated_player_pct
            FROM players p
            LEFT JOIN membership_counts mc
                ON mc.player_id = p.id
            WHERE p.generation_run_id = :generation_run_id
            GROUP BY p.generation_run_id
        """,
        required_params=("generation_run_id",),
        tags=("players", "clubs"),
    ),
    RealismAuditQuery(
        name="player_status_distribution",
        scope="generation_run",
        category="players",
        description="Observed player-status distribution versus configured weights.",
        sql="""
            SELECT
                COALESCE(p.player_status, 'UNKNOWN') AS player_status,
                COUNT(*) AS player_count,
                ROUND(
                    100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0),
                    2
                ) AS player_pct
            FROM players p
            WHERE p.generation_run_id = :generation_run_id
            GROUP BY COALESCE(p.player_status, 'UNKNOWN')
            ORDER BY player_count DESC, player_status ASC
        """,
        required_params=("generation_run_id",),
        tags=("players", "distribution"),
        related_config_keys=("player_generation.player_status_weights",),
        post_process=_post_process_player_status_distribution,
    ),
    RealismAuditQuery(
        name="player_gender_distribution",
        scope="generation_run",
        category="players",
        description="Observed player gender distribution versus configured weights.",
        sql="""
            SELECT
                COALESCE(p.gender, 'UNKNOWN') AS gender,
                COUNT(*) AS player_count,
                ROUND(
                    100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0),
                    2
                ) AS player_pct
            FROM players p
            WHERE p.generation_run_id = :generation_run_id
            GROUP BY COALESCE(p.gender, 'UNKNOWN')
            ORDER BY player_count DESC, gender ASC
        """,
        required_params=("generation_run_id",),
        tags=("players", "distribution"),
        related_config_keys=("player_generation.gender_weights",),
        post_process=_post_process_player_gender_distribution,
    ),
    RealismAuditQuery(
        name="player_age_distribution",
        scope="generation_run",
        category="players",
        description="Observed player age-bucket distribution at player creation versus configured weights.",
        sql=PLAYER_AGE_DISTRIBUTION_SQL,
        required_params=("generation_run_id",),
        tags=("players", "distribution", "age"),
        related_config_keys=("player_generation.age_distribution",),
        post_process=_post_process_player_age_distribution,
    ),
    RealismAuditQuery(
        name="player_registration_age_distribution",
        scope="generation_run",
        category="players",
        description="Observed player age-bucket distribution at stored registration date.",
        sql=PLAYER_REGISTRATION_AGE_DISTRIBUTION_SQL,
        required_params=("generation_run_id",),
        tags=("players", "distribution", "age", "registration"),
    ),
    RealismAuditQuery(
        name="player_region_distribution",
        scope="generation_run",
        category="players",
        description="Observed home-region allocation versus configured region selection weights.",
        sql="""
            WITH run_players AS (
                SELECT
                    p.home_region_id,
                    COUNT(*) AS player_count
                FROM players p
                WHERE p.generation_run_id = :generation_run_id
                GROUP BY p.home_region_id
            ),
            production_regions AS (
                SELECT
                    r.id,
                    r.country_code,
                    r.state_province_code,
                    r.region_name,
                    COALESCE(r.selection_probability, 0) AS selection_probability,
                    SUM(COALESCE(r.selection_probability, 0)) OVER () AS total_selection_probability
                FROM regions r
                WHERE r.country_code IN ('US', 'CA')
            )
            SELECT
                pr.id AS region_id,
                pr.country_code,
                pr.state_province_code,
                pr.region_name,
                COALESCE(rp.player_count, 0) AS player_count,
                ROUND(
                    100.0 * COALESCE(rp.player_count, 0)
                    / NULLIF(
                        (SELECT COUNT(*) FROM players WHERE generation_run_id = :generation_run_id),
                        0
                    ),
                    2
                ) AS player_pct,
                ROUND(
                    100.0 * pr.selection_probability
                    / NULLIF(pr.total_selection_probability, 0),
                    2
                ) AS configured_pct,
                ROUND(
                    (
                        100.0 * COALESCE(rp.player_count, 0)
                        / NULLIF(
                            (SELECT COUNT(*) FROM players WHERE generation_run_id = :generation_run_id),
                            0
                        )
                    ) - (
                        100.0 * pr.selection_probability
                        / NULLIF(pr.total_selection_probability, 0)
                    ),
                    2
                ) AS pct_point_drift
            FROM production_regions pr
            LEFT JOIN run_players rp
                ON rp.home_region_id = pr.id
            WHERE COALESCE(rp.player_count, 0) > 0
            ORDER BY player_count DESC, pr.region_name ASC
        """,
        required_params=("generation_run_id",),
        tags=("players", "distribution", "regions"),
        related_config_keys=("regional.regional_allocation_strategy",),
    ),
    RealismAuditQuery(
        name="player_registration_by_batch",
        scope="generation_run",
        category="players",
        description="Player-registration counts by monthly batch for one generation run.",
        sql="""
            SELECT
                b.id AS batch_id,
                b.batch_month,
                COUNT(pr.id) AS registration_count,
                ROUND(
                    100.0 * COUNT(pr.id)
                    / NULLIF(
                        (SELECT COUNT(*) FROM players WHERE generation_run_id = :generation_run_id),
                        0
                    ),
                    2
                ) AS player_pct
            FROM monthly_batches b
            LEFT JOIN player_registrations pr
                ON pr.batch_id = b.id
            WHERE b.generation_run_id = :generation_run_id
            GROUP BY b.id, b.batch_month
            ORDER BY b.batch_month ASC, b.id ASC
        """,
        required_params=("generation_run_id",),
        tags=("players", "registrations", "batches"),
    ),
    RealismAuditQuery(
        name="player_name_uniqueness_summary",
        scope="generation_run",
        category="players",
        description="Distinct-name and duplicate full-name summary for one generation run.",
        sql="""
            WITH full_name_counts AS (
                SELECT
                    p.first_name,
                    p.last_name,
                    COUNT(*) AS player_count
                FROM players p
                WHERE p.generation_run_id = :generation_run_id
                GROUP BY p.first_name, p.last_name
            )
            SELECT
                :generation_run_id AS generation_run_id,
                COUNT(*) AS player_count,
                COUNT(DISTINCT p.first_name) AS distinct_first_name_count,
                COUNT(DISTINCT p.last_name) AS distinct_last_name_count,
                COUNT(DISTINCT p.first_name || '|' || p.last_name) AS distinct_full_name_count,
                COALESCE((SELECT MAX(player_count) FROM full_name_counts), 0) AS max_players_sharing_full_name,
                ROUND(
                    100.0 * COALESCE((SELECT MAX(player_count) FROM full_name_counts), 0)
                    / NULLIF(COUNT(*), 0),
                    2
                ) AS max_full_name_player_pct
            FROM players p
            WHERE p.generation_run_id = :generation_run_id
        """,
        required_params=("generation_run_id",),
        tags=("players", "names", "distribution"),
    ),
    RealismAuditQuery(
        name="player_first_name_alignment",
        scope="generation_run",
        category="players",
        description="Generated first-name alignment to state/year/gender reference cohorts.",
        sql=FIRST_NAME_ALIGNMENT_SQL,
        required_params=("generation_run_id",),
        tags=("players", "names", "distribution"),
    ),
    RealismAuditQuery(
        name="player_last_name_alignment",
        scope="generation_run",
        category="players",
        description="Generated last-name alignment to state/province versus country reference cohorts.",
        sql="""
            WITH player_context AS (
                SELECT
                    p.id AS player_id,
                    p.last_name,
                    r.country_code,
                    r.state_province_code
                FROM players p
                LEFT JOIN regions r
                    ON r.id = p.home_region_id
                WHERE p.generation_run_id = :generation_run_id
            ),
            exact_reference AS (
                SELECT DISTINCT
                    ln.country_code,
                    ln.state_province_code,
                    ln.last_name
                FROM last_names ln
            ),
            country_reference AS (
                SELECT DISTINCT
                    ln.country_code,
                    ln.last_name
                FROM last_names ln
            ),
            aligned AS (
                SELECT
                    CASE
                        WHEN pc.country_code IS NULL THEN 'missing_reference'
                        WHEN exact_ref.last_name IS NOT NULL THEN 'exact_state'
                        WHEN country_ref.last_name IS NOT NULL THEN 'country_other_state'
                        ELSE 'missing_reference'
                    END AS alignment_bucket
                FROM player_context pc
                LEFT JOIN exact_reference exact_ref
                    ON exact_ref.country_code = pc.country_code
                    AND exact_ref.state_province_code = pc.state_province_code
                    AND exact_ref.last_name = pc.last_name
                LEFT JOIN country_reference country_ref
                    ON country_ref.country_code = pc.country_code
                    AND country_ref.last_name = pc.last_name
            )
            SELECT
                alignment_bucket,
                COUNT(*) AS player_count,
                ROUND(
                    100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0),
                    2
                ) AS player_pct
            FROM aligned
            GROUP BY alignment_bucket
            ORDER BY
                CASE alignment_bucket
                    WHEN 'exact_state' THEN 0
                    WHEN 'country_other_state' THEN 1
                    ELSE 2
                END
        """,
        required_params=("generation_run_id",),
        tags=("players", "names", "distribution"),
    ),
    RealismAuditQuery(
        name="initial_rating_distribution_summary",
        scope="generation_run",
        category="ratings",
        description="Summary of initial player ratings for one generation run.",
        sql="""
            SELECT
                :generation_run_id AS generation_run_id,
                COUNT(*) AS player_count,
                ROUND(AVG(prh.rating_value), 3) AS avg_initial_rating,
                MIN(prh.rating_value) AS min_initial_rating,
                MAX(prh.rating_value) AS max_initial_rating,
                SUM(CASE WHEN prh.rating_value < 1000 THEN 1 ELSE 0 END) AS sub_1000_count,
                SUM(CASE WHEN prh.rating_value >= 2000 THEN 1 ELSE 0 END) AS rating_2000_plus_count,
                SUM(CASE WHEN prh.rating_value >= :initial_rating_elite_min THEN 1 ELSE 0 END) AS elite_rating_count,
                ROUND(
                    100.0 * SUM(CASE WHEN prh.rating_value >= :initial_rating_elite_min THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(*), 0),
                    2
                ) AS elite_rating_pct,
                :initial_rating_elite_min AS configured_elite_min
            FROM player_rating_history prh
            JOIN players p
                ON p.id = prh.player_id
            WHERE p.generation_run_id = :generation_run_id
                AND prh.rating_type = 'initial'
        """,
        required_params=("generation_run_id", "initial_rating_elite_min"),
        tags=("players", "ratings"),
        related_config_keys=("ratings.initial_rating_elite_min",),
    ),
    RealismAuditQuery(
        name="club_membership_summary",
        scope="generation_run",
        category="clubs",
        description="Observed club-membership summary versus configured unaffiliated and multi-club targets.",
        sql="""
            WITH player_membership_counts AS (
                SELECT
                    p.id AS player_id,
                    COALESCE(mc.total_membership_count, 0) AS total_membership_count,
                    COALESCE(mc.primary_membership_count, 0) AS primary_membership_count
                FROM players p
                LEFT JOIN (
                    SELECT
                        cm.player_id,
                        COUNT(*) AS total_membership_count,
                        SUM(CASE WHEN cm.is_primary THEN 1 ELSE 0 END) AS primary_membership_count
                    FROM club_memberships cm
                    WHERE cm.generation_run_id = :generation_run_id
                    GROUP BY cm.player_id
                ) mc
                    ON mc.player_id = p.id
                WHERE p.generation_run_id = :generation_run_id
            )
            SELECT
                :generation_run_id AS generation_run_id,
                COUNT(*) AS player_count,
                SUM(CASE WHEN total_membership_count = 0 THEN 1 ELSE 0 END) AS unaffiliated_player_count,
                SUM(CASE WHEN total_membership_count > 1 THEN 1 ELSE 0 END) AS multi_club_player_count,
                SUM(CASE WHEN primary_membership_count > 1 THEN 1 ELSE 0 END) AS multi_primary_player_count,
                ROUND(
                    AVG(CASE WHEN total_membership_count > 0 THEN total_membership_count END),
                    3
                ) AS avg_memberships_per_affiliated_player,
                ROUND(
                    100.0 * SUM(CASE WHEN total_membership_count = 0 THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(*), 0),
                    2
                ) AS unaffiliated_player_pct,
                ROUND(
                    100.0 * SUM(CASE WHEN total_membership_count > 1 THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(*), 0),
                    2
                ) AS multi_club_player_pct,
                ROUND(:unaffiliated_player_rate * 100.0, 2) AS configured_unaffiliated_pct,
                ROUND(:multi_club_membership_rate * 100.0, 2) AS configured_multi_club_pct,
                ROUND(
                    (
                        100.0 * SUM(CASE WHEN total_membership_count = 0 THEN 1 ELSE 0 END)
                        / NULLIF(COUNT(*), 0)
                    ) - (:unaffiliated_player_rate * 100.0),
                    2
                ) AS unaffiliated_pct_point_drift,
                ROUND(
                    (
                        100.0 * SUM(CASE WHEN total_membership_count > 1 THEN 1 ELSE 0 END)
                        / NULLIF(COUNT(*), 0)
                    ) - (:multi_club_membership_rate * 100.0),
                    2
                ) AS multi_club_pct_point_drift
            FROM player_membership_counts
        """,
        required_params=(
            "generation_run_id",
            "unaffiliated_player_rate",
            "multi_club_membership_rate",
        ),
        tags=("clubs", "memberships"),
        related_config_keys=(
            "club_generation.unaffiliated_player_rate",
            "club_generation.multi_club_membership_rate",
        ),
    ),
    RealismAuditQuery(
        name="club_primary_membership_integrity",
        scope="generation_run",
        category="clubs",
        description="Primary-club membership integrity summary for one generation run.",
        sql="""
            WITH primary_membership_counts AS (
                SELECT
                    p.id AS player_id,
                    COALESCE(mc.primary_membership_count, 0) AS primary_membership_count
                FROM players p
                LEFT JOIN (
                    SELECT
                        cm.player_id,
                        SUM(CASE WHEN cm.is_primary THEN 1 ELSE 0 END) AS primary_membership_count
                    FROM club_memberships cm
                    WHERE cm.generation_run_id = :generation_run_id
                    GROUP BY cm.player_id
                ) mc
                    ON mc.player_id = p.id
                WHERE p.generation_run_id = :generation_run_id
            )
            SELECT
                :generation_run_id AS generation_run_id,
                COUNT(*) AS player_count,
                SUM(CASE WHEN primary_membership_count = 0 THEN 1 ELSE 0 END) AS zero_primary_player_count,
                SUM(CASE WHEN primary_membership_count = 1 THEN 1 ELSE 0 END) AS valid_primary_player_count,
                SUM(CASE WHEN primary_membership_count > 1 THEN 1 ELSE 0 END) AS multi_primary_player_count
            FROM primary_membership_counts
        """,
        required_params=("generation_run_id",),
        tags=("clubs", "integrity"),
    ),
    RealismAuditQuery(
        name="club_fill_ratio_summary",
        scope="generation_run",
        category="clubs",
        description="Club fill-ratio summary versus configured maximum fill ratio.",
        sql="""
            WITH club_load AS (
                SELECT
                    c.id AS club_id,
                    c.member_capacity,
                    COUNT(cm.id) AS membership_count,
                    SUM(CASE WHEN cm.is_primary THEN 1 ELSE 0 END) AS primary_membership_count,
                    CASE
                        WHEN c.member_capacity IS NOT NULL AND c.member_capacity > 0
                        THEN 1.0 * COUNT(cm.id) / c.member_capacity
                        ELSE NULL
                    END AS fill_ratio
                FROM clubs c
                LEFT JOIN club_memberships cm
                    ON cm.club_id = c.id
                    AND cm.generation_run_id = :generation_run_id
                WHERE c.generation_run_id IS NULL OR c.generation_run_id = :generation_run_id
                GROUP BY c.id, c.member_capacity
            )
            SELECT
                :generation_run_id AS generation_run_id,
                COUNT(*) AS club_count,
                SUM(CASE WHEN member_capacity IS NOT NULL AND member_capacity > 0 THEN 1 ELSE 0 END) AS capacity_tracked_club_count,
                SUM(CASE WHEN membership_count = 0 THEN 1 ELSE 0 END) AS zero_membership_club_count,
                ROUND(AVG(fill_ratio), 3) AS avg_fill_ratio,
                ROUND(MAX(fill_ratio), 3) AS max_fill_ratio,
                SUM(CASE WHEN fill_ratio > :max_club_fill_ratio THEN 1 ELSE 0 END) AS over_capacity_club_count,
                ROUND(:max_club_fill_ratio, 3) AS configured_max_fill_ratio
            FROM club_load
        """,
        required_params=("generation_run_id", "max_club_fill_ratio"),
        tags=("clubs", "capacity"),
        related_config_keys=("club_generation.max_club_fill_ratio",),
    ),
    RealismAuditQuery(
        name="club_fill_ratio_outliers",
        scope="generation_run",
        category="clubs",
        description="Most heavily loaded clubs for one generation run.",
        sql="""
            WITH club_load AS (
                SELECT
                    c.id AS club_id,
                    c.club_name,
                    c.member_capacity,
                    r.region_name,
                    COUNT(cm.id) AS membership_count,
                    SUM(CASE WHEN cm.is_primary THEN 1 ELSE 0 END) AS primary_membership_count,
                    CASE
                        WHEN c.member_capacity IS NOT NULL AND c.member_capacity > 0
                        THEN 1.0 * COUNT(cm.id) / c.member_capacity
                        ELSE NULL
                    END AS fill_ratio
                FROM clubs c
                LEFT JOIN regions r
                    ON r.id = c.region_id
                LEFT JOIN club_memberships cm
                    ON cm.club_id = c.id
                    AND cm.generation_run_id = :generation_run_id
                WHERE c.generation_run_id IS NULL OR c.generation_run_id = :generation_run_id
                GROUP BY c.id, c.club_name, c.member_capacity, r.region_name
            )
            SELECT
                club_id,
                club_name,
                region_name,
                member_capacity,
                membership_count,
                primary_membership_count,
                ROUND(fill_ratio, 3) AS fill_ratio,
                ROUND(:max_club_fill_ratio, 3) AS configured_max_fill_ratio
            FROM club_load
            WHERE member_capacity IS NOT NULL AND member_capacity > 0
            ORDER BY fill_ratio DESC, membership_count DESC, club_id ASC
            LIMIT 25
        """,
        required_params=("generation_run_id", "max_club_fill_ratio"),
        tags=("clubs", "capacity", "outliers"),
        related_config_keys=("club_generation.max_club_fill_ratio",),
    ),
    RealismAuditQuery(
        name="club_membership_geography",
        scope="generation_run",
        category="clubs",
        description="Secondary-membership locality and cross-region pressure for one generation run.",
        sql="""
            WITH memberships AS (
                SELECT
                    cm.player_id,
                    cm.is_primary,
                    p.home_region_id AS player_region_id,
                    c.region_id AS club_region_id
                FROM club_memberships cm
                JOIN players p
                    ON p.id = cm.player_id
                JOIN clubs c
                    ON c.id = cm.club_id
                WHERE cm.generation_run_id = :generation_run_id
            )
            SELECT
                COUNT(*) AS membership_count,
                SUM(CASE WHEN is_primary THEN 1 ELSE 0 END) AS primary_membership_count,
                SUM(CASE WHEN is_primary THEN 0 ELSE 1 END) AS secondary_membership_count,
                SUM(
                    CASE
                        WHEN player_region_id IS NOT NULL
                            AND club_region_id IS NOT NULL
                            AND player_region_id <> club_region_id
                        THEN 1
                        ELSE 0
                    END
                ) AS cross_region_membership_count,
                ROUND(
                    100.0 * SUM(
                        CASE
                            WHEN is_primary THEN 0
                            WHEN player_region_id IS NOT NULL
                                AND club_region_id IS NOT NULL
                                AND player_region_id = club_region_id
                            THEN 1
                            ELSE 0
                        END
                    ) / NULLIF(
                        SUM(CASE WHEN is_primary THEN 0 ELSE 1 END),
                        0
                    ),
                    2
                ) AS same_region_secondary_pct,
                ROUND(
                    CASE
                        WHEN :cross_region_assignment_enabled
                        THEN :secondary_membership_same_region_rate * 100.0
                        ELSE 100.0
                    END,
                    2
                ) AS configured_same_region_secondary_pct
            FROM memberships
        """,
        required_params=(
            "generation_run_id",
            "secondary_membership_same_region_rate",
            "cross_region_assignment_enabled",
        ),
        tags=("clubs", "geography"),
        related_config_keys=(
            "club_generation.secondary_membership_same_region_rate",
            "club_generation.cross_region_assignment_enabled",
        ),
    ),
    RealismAuditQuery(
        name="cross_region_membership_flows",
        scope="generation_run",
        category="clubs",
        description="Largest cross-region club-membership flows for one generation run.",
        sql="""
            SELECT
                pr.region_name AS player_region_name,
                cr.region_name AS club_region_name,
                COUNT(*) AS membership_count,
                SUM(CASE WHEN cm.is_primary THEN 1 ELSE 0 END) AS primary_membership_count,
                SUM(CASE WHEN cm.is_primary THEN 0 ELSE 1 END) AS secondary_membership_count
            FROM club_memberships cm
            JOIN players p
                ON p.id = cm.player_id
            JOIN clubs c
                ON c.id = cm.club_id
            LEFT JOIN regions pr
                ON pr.id = p.home_region_id
            LEFT JOIN regions cr
                ON cr.id = c.region_id
            WHERE cm.generation_run_id = :generation_run_id
                AND p.home_region_id IS NOT NULL
                AND c.region_id IS NOT NULL
                AND p.home_region_id <> c.region_id
            GROUP BY pr.region_name, cr.region_name
            ORDER BY membership_count DESC, player_region_name ASC, club_region_name ASC
            LIMIT 25
        """,
        required_params=("generation_run_id",),
        tags=("clubs", "geography", "outliers"),
    ),
    RealismAuditQuery(
        name="match_volume_by_batch",
        scope="generation_run",
        category="matches",
        description="Per-batch match volume trend across the full generation run.",
        sql="""
            SELECT
                b.id AS batch_id,
                b.batch_month,
                COUNT(m.id) AS match_count,
                COUNT(DISTINCT m.match_date) AS unique_match_days,
                ROUND(
                    1.0 * COUNT(m.id) / NULLIF(COUNT(DISTINCT m.match_date), 0),
                    3
                ) AS avg_matches_per_match_day,
                COUNT(DISTINCT m.region_id) AS distinct_match_regions
            FROM monthly_batches b
            LEFT JOIN matches m
                ON m.batch_id = b.id
            WHERE b.generation_run_id = :generation_run_id
            GROUP BY b.id, b.batch_month, b.batch_sequence
            ORDER BY b.batch_month ASC, b.batch_sequence ASC, b.id ASC
        """,
        required_params=("generation_run_id",),
        tags=("matches", "cadence", "batches"),
    ),
    RealismAuditQuery(
        name="match_volume_summary",
        scope="batch",
        category="matches",
        description="Top-line batch match volume and day coverage summary.",
        sql="""
            SELECT
                b.id AS batch_id,
                b.batch_month,
                COUNT(m.id) AS match_count,
                COUNT(DISTINCT m.match_date) AS unique_match_days,
                ROUND(
                    1.0 * COUNT(m.id) / NULLIF(COUNT(DISTINCT m.match_date), 0),
                    3
                ) AS avg_matches_per_match_day,
                COUNT(DISTINCT m.region_id) AS distinct_match_regions
            FROM monthly_batches b
            LEFT JOIN matches m
                ON m.batch_id = b.id
            WHERE b.id = :batch_id
            GROUP BY b.id, b.batch_month
        """,
        required_params=("batch_id",),
        tags=("matches", "cadence"),
    ),
    RealismAuditQuery(
        name="match_type_distribution",
        scope="batch",
        category="matches",
        description="Observed match-type mix for one monthly batch.",
        sql="""
            SELECT
                b.id AS batch_id,
                b.batch_month,
                m.match_type,
                COUNT(*) AS match_count,
                ROUND(
                    100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0),
                    2
                ) AS match_pct
            FROM matches m
            JOIN monthly_batches b
                ON b.id = m.batch_id
            WHERE m.batch_id = :batch_id
            GROUP BY b.id, b.batch_month, m.match_type
            ORDER BY match_count DESC, m.match_type ASC
        """,
        required_params=("batch_id",),
        tags=("matches", "distribution"),
        related_config_keys=("match_types.weights",),
        post_process=_post_process_match_type_distribution,
    ),
    RealismAuditQuery(
        name="match_day_of_week_distribution",
        scope="batch",
        category="matches",
        description="Observed day-of-week match distribution for one monthly batch.",
        sql=MATCH_DAY_OF_WEEK_SQL,
        required_params=("batch_id",),
        tags=("matches", "schedule"),
    ),
    RealismAuditQuery(
        name="weekend_match_share",
        scope="batch",
        category="matches",
        description="Weekend concentration check against configured validation bounds.",
        sql={
            "sqlite": """
                SELECT
                    b.id AS batch_id,
                    b.batch_month,
                    COUNT(*) AS total_matches,
                    SUM(
                        CASE
                            WHEN CAST(strftime('%w', m.match_date) AS INTEGER) IN (0, 6)
                            THEN 1
                            ELSE 0
                        END
                    ) AS weekend_match_count,
                    ROUND(
                        100.0 * SUM(
                            CASE
                                WHEN CAST(strftime('%w', m.match_date) AS INTEGER) IN (0, 6)
                                THEN 1
                                ELSE 0
                            END
                        ) / NULLIF(COUNT(*), 0),
                        2
                    ) AS weekend_match_pct,
                    ROUND(:weekend_concentration_min * 100.0, 2) AS configured_weekend_min_pct,
                    ROUND(:weekend_concentration_max * 100.0, 2) AS configured_weekend_max_pct,
                    CASE
                        WHEN (
                            1.0 * SUM(
                                CASE
                                    WHEN CAST(strftime('%w', m.match_date) AS INTEGER) IN (0, 6)
                                    THEN 1
                                    ELSE 0
                                END
                            ) / NULLIF(COUNT(*), 0)
                        ) BETWEEN :weekend_concentration_min AND :weekend_concentration_max
                        THEN 0
                        ELSE 1
                    END AS outside_config_range
                FROM matches m
                JOIN monthly_batches b
                    ON b.id = m.batch_id
                WHERE m.batch_id = :batch_id
                GROUP BY b.id, b.batch_month
            """,
            "postgresql": """
                SELECT
                    b.id AS batch_id,
                    b.batch_month,
                    COUNT(*) AS total_matches,
                    SUM(
                        CASE
                            WHEN EXTRACT(DOW FROM m.match_date) IN (0, 6)
                            THEN 1
                            ELSE 0
                        END
                    ) AS weekend_match_count,
                    ROUND(
                        100.0 * SUM(
                            CASE
                                WHEN EXTRACT(DOW FROM m.match_date) IN (0, 6)
                                THEN 1
                                ELSE 0
                            END
                        ) / NULLIF(COUNT(*), 0),
                        2
                    ) AS weekend_match_pct,
                    ROUND(:weekend_concentration_min * 100.0, 2) AS configured_weekend_min_pct,
                    ROUND(:weekend_concentration_max * 100.0, 2) AS configured_weekend_max_pct,
                    CASE
                        WHEN (
                            1.0 * SUM(
                                CASE
                                    WHEN EXTRACT(DOW FROM m.match_date) IN (0, 6)
                                    THEN 1
                                    ELSE 0
                                END
                            ) / NULLIF(COUNT(*), 0)
                        ) BETWEEN :weekend_concentration_min AND :weekend_concentration_max
                        THEN 0
                        ELSE 1
                    END AS outside_config_range
                FROM matches m
                JOIN monthly_batches b
                    ON b.id = m.batch_id
                WHERE m.batch_id = :batch_id
                GROUP BY b.id, b.batch_month
            """,
        },
        required_params=(
            "batch_id",
            "weekend_concentration_min",
            "weekend_concentration_max",
        ),
        tags=("matches", "schedule", "validation"),
        related_config_keys=(
            "validation.weekend_concentration_min",
            "validation.weekend_concentration_max",
        ),
    ),
    RealismAuditQuery(
        name="matches_per_team_distribution",
        scope="batch",
        category="matches",
        description="Distribution of batch match volume across active team rosters.",
        sql="""
            WITH batch_context AS (
                SELECT
                    b.id AS batch_id,
                    b.generation_run_id,
                    b.batch_month
                FROM monthly_batches b
                WHERE b.id = :batch_id
            ),
            active_team_rosters AS (
                SELECT
                    t.id AS team_id,
                    CAST(MIN(tm.player_id) AS TEXT) || ':' || CAST(MAX(tm.player_id) AS TEXT) AS roster_key
                FROM teams t
                JOIN batch_context bc
                    ON bc.generation_run_id = t.generation_run_id
                JOIN team_memberships tm
                    ON tm.team_id = t.id
                WHERE t.team_status = 'active'
                    AND t.formation_date <= bc.batch_month
                    AND (t.dissolution_date IS NULL OR t.dissolution_date > bc.batch_month)
                    AND tm.joined_date <= bc.batch_month
                    AND (tm.left_date IS NULL OR tm.left_date > bc.batch_month)
                GROUP BY t.id
                HAVING COUNT(*) = 2
            ),
            match_team_rosters AS (
                SELECT
                    CAST(MIN(mtp.player_id) AS TEXT) || ':' || CAST(MAX(mtp.player_id) AS TEXT) AS roster_key,
                    1 AS match_count
                FROM matches m
                JOIN match_teams mt
                    ON mt.match_id = m.id
                JOIN match_team_players mtp
                    ON mtp.match_team_id = mt.id
                WHERE m.batch_id = :batch_id
                GROUP BY mt.id
            ),
            roster_match_counts AS (
                SELECT
                    atr.team_id,
                    COALESCE(SUM(mtr.match_count), 0) AS match_count
                FROM active_team_rosters atr
                LEFT JOIN match_team_rosters mtr
                    ON mtr.roster_key = atr.roster_key
                GROUP BY atr.team_id
            ),
            bucketed AS (
                SELECT
                    CASE
                        WHEN match_count = 0 THEN '0'
                        WHEN match_count = 1 THEN '1'
                        WHEN match_count = 2 THEN '2'
                        WHEN match_count BETWEEN 3 AND 4 THEN '3_4'
                        ELSE '5_plus'
                    END AS match_count_bucket
                FROM roster_match_counts
            )
            SELECT
                match_count_bucket,
                COUNT(*) AS team_count,
                ROUND(
                    100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0),
                    2
                ) AS team_pct
            FROM bucketed
            GROUP BY match_count_bucket
            ORDER BY
                CASE match_count_bucket
                    WHEN '0' THEN 0
                    WHEN '1' THEN 1
                    WHEN '2' THEN 2
                    WHEN '3_4' THEN 3
                    ELSE 4
                END
        """,
        required_params=("batch_id",),
        tags=("matches", "cadence", "teams"),
    ),
    RealismAuditQuery(
        name="team_partner_continuity_by_batch",
        scope="generation_run",
        category="teams",
        description="Per-batch active-roster continuity relative to the immediately prior batch.",
        sql="""
            WITH ordered_batches AS (
                SELECT
                    b.id AS batch_id,
                    b.batch_month,
                    ROW_NUMBER() OVER (
                        ORDER BY b.batch_month ASC, b.batch_sequence ASC, b.id ASC
                    ) AS batch_ordinal
                FROM monthly_batches b
                WHERE b.generation_run_id = :generation_run_id
            ),
            batch_pairs AS (
                SELECT
                    current_batch.batch_id,
                    current_batch.batch_month,
                    current_batch.batch_ordinal,
                    prior_batch.batch_id AS prior_batch_id
                FROM ordered_batches current_batch
                LEFT JOIN ordered_batches prior_batch
                    ON prior_batch.batch_ordinal = current_batch.batch_ordinal - 1
            ),
            active_rosters AS (
                SELECT
                    bp.batch_id,
                    CAST(MIN(tm.player_id) AS TEXT) || ':' || CAST(MAX(tm.player_id) AS TEXT) AS roster_key
                FROM batch_pairs bp
                JOIN teams t
                    ON t.generation_run_id = :generation_run_id
                    AND t.team_status = 'active'
                    AND t.formation_date <= bp.batch_month
                    AND (t.dissolution_date IS NULL OR t.dissolution_date > bp.batch_month)
                JOIN team_memberships tm
                    ON tm.team_id = t.id
                    AND tm.joined_date <= bp.batch_month
                    AND (tm.left_date IS NULL OR tm.left_date > bp.batch_month)
                GROUP BY bp.batch_id, t.id
                HAVING COUNT(*) = 2
            ),
            classified AS (
                SELECT
                    bp.batch_id,
                    bp.batch_month,
                    bp.prior_batch_id,
                    ar.roster_key,
                    CASE
                        WHEN bp.prior_batch_id IS NOT NULL
                            AND EXISTS (
                                SELECT 1
                                FROM active_rosters prior_ar
                                WHERE prior_ar.batch_id = bp.prior_batch_id
                                    AND prior_ar.roster_key = ar.roster_key
                            )
                        THEN 1
                        ELSE 0
                    END AS persisted_from_prior_batch
                FROM batch_pairs bp
                LEFT JOIN active_rosters ar
                    ON ar.batch_id = bp.batch_id
            )
            SELECT
                batch_id,
                batch_month,
                COUNT(roster_key) AS active_roster_count,
                SUM(persisted_from_prior_batch) AS persisted_roster_count,
                SUM(
                    CASE
                        WHEN roster_key IS NOT NULL AND persisted_from_prior_batch = 0
                        THEN 1
                        ELSE 0
                    END
                ) AS new_roster_count,
                CASE
                    WHEN prior_batch_id IS NULL THEN NULL
                    ELSE ROUND(
                        100.0 * SUM(persisted_from_prior_batch) / NULLIF(COUNT(roster_key), 0),
                        2
                    )
                END AS persisted_roster_pct
            FROM classified
            GROUP BY batch_id, batch_month, prior_batch_id
            ORDER BY batch_month ASC, batch_id ASC
        """,
        required_params=("generation_run_id",),
        tags=("teams", "persistence", "batches"),
    ),
    RealismAuditQuery(
        name="matches_per_player_distribution",
        scope="batch",
        category="matches",
        description="Distribution of monthly match volume across active players in the batch.",
        sql="""
            WITH batch_context AS (
                SELECT
                    b.id AS batch_id,
                    b.generation_run_id,
                    b.batch_month
                FROM monthly_batches b
                WHERE b.id = :batch_id
            ),
            active_players AS (
                SELECT
                    p.id AS player_id
                FROM players p
                JOIN batch_context bc
                    ON bc.generation_run_id = p.generation_run_id
                WHERE p.player_status = 'ACTIVE'
            ),
            player_match_counts AS (
                SELECT
                    ap.player_id,
                    COUNT(DISTINCT m.id) AS match_count
                FROM active_players ap
                LEFT JOIN match_team_players mtp
                    ON mtp.player_id = ap.player_id
                LEFT JOIN match_teams mt
                    ON mt.id = mtp.match_team_id
                LEFT JOIN matches m
                    ON m.id = mt.match_id
                    AND m.batch_id = :batch_id
                GROUP BY ap.player_id
            ),
            bucketed AS (
                SELECT
                    CASE
                        WHEN match_count = 0 THEN '0'
                        WHEN match_count BETWEEN 1 AND 2 THEN '1_2'
                        WHEN match_count BETWEEN 3 AND 4 THEN '3_4'
                        WHEN match_count BETWEEN 5 AND 8 THEN '5_8'
                        ELSE '9_plus'
                    END AS match_count_bucket
                FROM player_match_counts
            )
            SELECT
                match_count_bucket,
                COUNT(*) AS player_count,
                ROUND(
                    100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0),
                    2
                ) AS player_pct,
                :monthly_matches_per_active_player_mean AS configured_match_mean,
                :monthly_matches_per_active_player_std_dev AS configured_match_std_dev,
                :match_volume_noise_factor AS configured_match_volume_noise_factor
            FROM bucketed
            GROUP BY match_count_bucket
            ORDER BY
                CASE match_count_bucket
                    WHEN '0' THEN 0
                    WHEN '1_2' THEN 1
                    WHEN '3_4' THEN 2
                    WHEN '5_8' THEN 3
                    ELSE 4
                END
        """,
        required_params=(
            "batch_id",
            "monthly_matches_per_active_player_mean",
            "monthly_matches_per_active_player_std_dev",
            "match_volume_noise_factor",
        ),
        tags=("matches", "cadence", "players"),
        related_config_keys=(
            "match_scheduling.monthly_matches_per_active_player_mean",
            "match_scheduling.monthly_matches_per_active_player_std_dev",
            "match_scheduling.match_volume_noise_factor",
        ),
    ),
    RealismAuditQuery(
        name="repeat_partner_match_distribution",
        scope="batch",
        category="matches",
        description="Distribution of prior same-partner match counts for match-team rosters in the audited batch.",
        sql="""
            WITH ordered_batches AS (
                SELECT
                    b.id AS batch_id,
                    b.generation_run_id,
                    b.batch_month,
                    ROW_NUMBER() OVER (
                        ORDER BY b.batch_month ASC, b.batch_sequence ASC, b.id ASC
                    ) AS batch_ordinal
                FROM monthly_batches b
                WHERE b.generation_run_id = (
                    SELECT generation_run_id
                    FROM monthly_batches
                    WHERE id = :batch_id
                )
            ),
            batch_context AS (
                SELECT
                    batch_id,
                    generation_run_id,
                    batch_month,
                    batch_ordinal
                FROM ordered_batches
                WHERE batch_id = :batch_id
            ),
            current_match_team_rosters AS (
                SELECT
                    mt.id AS match_team_id,
                    CAST(MIN(mtp.player_id) AS TEXT) || ':' || CAST(MAX(mtp.player_id) AS TEXT) AS roster_key
                FROM matches m
                JOIN match_teams mt
                    ON mt.match_id = m.id
                JOIN match_team_players mtp
                    ON mtp.match_team_id = mt.id
                WHERE m.batch_id = :batch_id
                GROUP BY mt.id
            ),
            prior_match_team_rosters AS (
                SELECT
                    CAST(MIN(mtp.player_id) AS TEXT) || ':' || CAST(MAX(mtp.player_id) AS TEXT) AS roster_key
                FROM batch_context bc
                JOIN ordered_batches ob
                    ON ob.generation_run_id = bc.generation_run_id
                    AND ob.batch_ordinal < bc.batch_ordinal
                JOIN matches m
                    ON m.batch_id = ob.batch_id
                JOIN match_teams mt
                    ON mt.match_id = m.id
                JOIN match_team_players mtp
                    ON mtp.match_team_id = mt.id
                GROUP BY mt.id
            ),
            prior_roster_counts AS (
                SELECT
                    roster_key,
                    COUNT(*) AS prior_match_count
                FROM prior_match_team_rosters
                GROUP BY roster_key
            ),
            prior_pair_counts AS (
                SELECT
                    cmtr.match_team_id,
                    COALESCE(prc.prior_match_count, 0) AS prior_match_count
                FROM current_match_team_rosters cmtr
                LEFT JOIN prior_roster_counts prc
                    ON prc.roster_key = cmtr.roster_key
            ),
            bucketed AS (
                SELECT
                    CASE
                        WHEN prior_match_count = 0 THEN '0'
                        WHEN prior_match_count <= 2 THEN '1_2'
                        WHEN prior_match_count <= 5 THEN '3_5'
                        ELSE '6_plus'
                    END AS prior_match_count_bucket,
                    prior_match_count
                FROM prior_pair_counts
            )
            SELECT
                prior_match_count_bucket,
                COUNT(*) AS team_count,
                ROUND(
                    100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0),
                    2
                ) AS team_pct,
                ROUND(AVG(prior_match_count), 2) AS avg_prior_match_count
            FROM bucketed
            GROUP BY prior_match_count_bucket
            ORDER BY
                CASE prior_match_count_bucket
                    WHEN '0' THEN 0
                    WHEN '1_2' THEN 1
                    WHEN '3_5' THEN 2
                    ELSE 3
                END
        """,
        required_params=("batch_id",),
        tags=("matches", "teams", "persistence"),
    ),
    RealismAuditQuery(
        name="zero_match_players_by_registration_cohort",
        scope="batch",
        category="matches",
        description=(
            "Zero-match active players split between initial-batch registrations "
            "and later registration cohorts."
        ),
        sql="""
            WITH batch_context AS (
                SELECT
                    b.id AS batch_id,
                    b.generation_run_id,
                    b.batch_month
                FROM monthly_batches b
                WHERE b.id = :batch_id
            ),
            first_run_batch AS (
                SELECT
                    MIN(b.batch_month) AS first_batch_month
                FROM monthly_batches b
                JOIN batch_context bc
                    ON bc.generation_run_id = b.generation_run_id
            ),
            active_players AS (
                SELECT
                    p.id AS player_id,
                    CASE
                        WHEN COALESCE(
                            MIN(pr.registration_month),
                            p.registration_date
                        ) = (SELECT first_batch_month FROM first_run_batch)
                            THEN 'initial_batch'
                        ELSE 'later_batch'
                    END AS registration_cohort
                FROM players p
                JOIN batch_context bc
                    ON bc.generation_run_id = p.generation_run_id
                LEFT JOIN player_registrations pr
                    ON pr.player_id = p.id
                WHERE p.player_status = 'ACTIVE'
                    AND p.registration_date <= bc.batch_month
                GROUP BY p.id, p.registration_date
            ),
            player_match_counts AS (
                SELECT
                    ap.player_id,
                    ap.registration_cohort,
                    COUNT(DISTINCT m.id) AS match_count
                FROM active_players ap
                LEFT JOIN match_team_players mtp
                    ON mtp.player_id = ap.player_id
                LEFT JOIN match_teams mt
                    ON mt.id = mtp.match_team_id
                LEFT JOIN matches m
                    ON m.id = mt.match_id
                    AND m.batch_id = :batch_id
                GROUP BY ap.player_id, ap.registration_cohort
            )
            SELECT
                registration_cohort,
                COUNT(*) AS active_player_count,
                SUM(CASE WHEN match_count = 0 THEN 1 ELSE 0 END) AS zero_match_player_count,
                ROUND(
                    100.0 * SUM(CASE WHEN match_count = 0 THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(*), 0),
                    2
                ) AS zero_match_player_pct
            FROM player_match_counts
            GROUP BY registration_cohort
            ORDER BY
                CASE registration_cohort
                    WHEN 'initial_batch' THEN 0
                    ELSE 1
                END
        """,
        required_params=("batch_id",),
        tags=("matches", "cadence", "players", "registrations"),
    ),
    RealismAuditQuery(
        name="zero_match_players_by_team_membership",
        scope="batch",
        category="matches",
        description=(
            "Zero-match active players split by active team-roster status in the "
            "batch month. In doubles-only simulation, unteamed players are not "
            "match-eligible, so this is primarily a roster-readiness audit."
        ),
        sql="""
            WITH batch_context AS (
                SELECT
                    b.id AS batch_id,
                    b.generation_run_id,
                    b.batch_month
                FROM monthly_batches b
                WHERE b.id = :batch_id
            ),
            active_team_players AS (
                SELECT DISTINCT
                    tm.player_id
                FROM batch_context bc
                JOIN teams t
                    ON t.generation_run_id = bc.generation_run_id
                    AND t.team_status = 'active'
                    AND t.formation_date <= bc.batch_month
                    AND (t.dissolution_date IS NULL OR t.dissolution_date > bc.batch_month)
                JOIN team_memberships tm
                    ON tm.team_id = t.id
                    AND tm.joined_date <= bc.batch_month
                    AND (tm.left_date IS NULL OR tm.left_date > bc.batch_month)
            ),
            active_players AS (
                SELECT
                    p.id AS player_id,
                    CASE
                        WHEN atp.player_id IS NULL THEN 'unteamed'
                        ELSE 'teamed'
                    END AS team_membership_status
                FROM players p
                JOIN batch_context bc
                    ON bc.generation_run_id = p.generation_run_id
                LEFT JOIN active_team_players atp
                    ON atp.player_id = p.id
                WHERE p.player_status = 'ACTIVE'
                    AND p.registration_date <= bc.batch_month
            ),
            player_match_counts AS (
                SELECT
                    ap.player_id,
                    ap.team_membership_status,
                    COUNT(DISTINCT m.id) AS match_count
                FROM active_players ap
                LEFT JOIN match_team_players mtp
                    ON mtp.player_id = ap.player_id
                LEFT JOIN match_teams mt
                    ON mt.id = mtp.match_team_id
                LEFT JOIN matches m
                    ON m.id = mt.match_id
                    AND m.batch_id = :batch_id
                GROUP BY ap.player_id, ap.team_membership_status
            )
            SELECT
                team_membership_status,
                COUNT(*) AS active_player_count,
                SUM(CASE WHEN match_count = 0 THEN 1 ELSE 0 END) AS zero_match_player_count,
                ROUND(
                    100.0 * SUM(CASE WHEN match_count = 0 THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(*), 0),
                    2
                ) AS zero_match_player_pct
            FROM player_match_counts
            GROUP BY team_membership_status
            ORDER BY
                CASE team_membership_status
                    WHEN 'teamed' THEN 0
                    ELSE 1
                END
        """,
        required_params=("batch_id",),
        tags=("matches", "cadence", "players", "teams"),
    ),
    RealismAuditQuery(
        name="team_assignment_delay_summary",
        scope="batch",
        category="teams",
        description=(
            "Average time from player registration to first team assignment, plus "
            "the current unteamed inventory as of the audited batch."
        ),
        sql={
            "sqlite": """
                WITH batch_context AS (
                    SELECT
                        b.id AS batch_id,
                        b.generation_run_id,
                        b.batch_month
                    FROM monthly_batches b
                    WHERE b.id = :batch_id
                ),
                player_creation_dates AS (
                    SELECT
                        p.id AS player_id,
                        COALESCE(MIN(pr.registration_month), p.registration_date) AS creation_date
                    FROM players p
                    JOIN batch_context bc
                        ON bc.generation_run_id = p.generation_run_id
                    LEFT JOIN player_registrations pr
                        ON pr.player_id = p.id
                    WHERE p.player_status = 'ACTIVE'
                        AND p.registration_date <= bc.batch_month
                    GROUP BY p.id, p.registration_date
                ),
                player_first_team_dates AS (
                    SELECT
                        pcd.player_id,
                        pcd.creation_date,
                        MIN(tm.joined_date) AS first_team_joined_date
                    FROM player_creation_dates pcd
                    JOIN batch_context bc
                        ON 1 = 1
                    LEFT JOIN team_memberships tm
                        ON tm.player_id = pcd.player_id
                        AND tm.joined_date >= pcd.creation_date
                        AND tm.joined_date <= bc.batch_month
                    GROUP BY pcd.player_id, pcd.creation_date
                ),
                player_delays AS (
                    SELECT
                        player_id,
                        creation_date,
                        first_team_joined_date,
                        CAST(
                            julianday(
                                COALESCE(first_team_joined_date, (SELECT batch_month FROM batch_context))
                            ) - julianday(creation_date) AS INTEGER
                        ) AS days_unteamed_until_resolution_or_batch,
                        CASE
                            WHEN first_team_joined_date IS NULL THEN 1
                            ELSE 0
                        END AS still_unteamed_as_of_batch
                    FROM player_first_team_dates
                )
                SELECT
                    :batch_id AS batch_id,
                    (SELECT batch_month FROM batch_context) AS batch_month,
                    COUNT(*) AS player_count,
                    SUM(CASE WHEN first_team_joined_date IS NOT NULL THEN 1 ELSE 0 END) AS ever_teamed_player_count,
                    SUM(still_unteamed_as_of_batch) AS still_unteamed_player_count,
                    ROUND(
                        AVG(
                            CASE
                                WHEN first_team_joined_date IS NOT NULL
                                    THEN days_unteamed_until_resolution_or_batch
                            END
                        ),
                        2
                    ) AS avg_days_to_first_team,
                    ROUND(
                        AVG(days_unteamed_until_resolution_or_batch),
                        2
                    ) AS avg_days_unteamed_including_unresolved,
                    MAX(days_unteamed_until_resolution_or_batch) AS max_days_unteamed_including_unresolved
                FROM player_delays
            """,
            "postgresql": """
                WITH batch_context AS (
                    SELECT
                        b.id AS batch_id,
                        b.generation_run_id,
                        b.batch_month
                    FROM monthly_batches b
                    WHERE b.id = :batch_id
                ),
                player_creation_dates AS (
                    SELECT
                        p.id AS player_id,
                        COALESCE(MIN(pr.registration_month), p.registration_date) AS creation_date
                    FROM players p
                    JOIN batch_context bc
                        ON bc.generation_run_id = p.generation_run_id
                    LEFT JOIN player_registrations pr
                        ON pr.player_id = p.id
                    WHERE p.player_status = 'ACTIVE'
                        AND p.registration_date <= bc.batch_month
                    GROUP BY p.id, p.registration_date
                ),
                player_first_team_dates AS (
                    SELECT
                        pcd.player_id,
                        pcd.creation_date,
                        MIN(tm.joined_date) AS first_team_joined_date
                    FROM player_creation_dates pcd
                    JOIN batch_context bc
                        ON 1 = 1
                    LEFT JOIN team_memberships tm
                        ON tm.player_id = pcd.player_id
                        AND tm.joined_date >= pcd.creation_date
                        AND tm.joined_date <= bc.batch_month
                    GROUP BY pcd.player_id, pcd.creation_date
                ),
                player_delays AS (
                    SELECT
                        player_id,
                        creation_date,
                        first_team_joined_date,
                        CAST(
                            COALESCE(first_team_joined_date, (SELECT batch_month FROM batch_context))
                            - creation_date AS INTEGER
                        ) AS days_unteamed_until_resolution_or_batch,
                        CASE
                            WHEN first_team_joined_date IS NULL THEN 1
                            ELSE 0
                        END AS still_unteamed_as_of_batch
                    FROM player_first_team_dates
                )
                SELECT
                    :batch_id AS batch_id,
                    (SELECT batch_month FROM batch_context) AS batch_month,
                    COUNT(*) AS player_count,
                    SUM(CASE WHEN first_team_joined_date IS NOT NULL THEN 1 ELSE 0 END) AS ever_teamed_player_count,
                    SUM(still_unteamed_as_of_batch) AS still_unteamed_player_count,
                    ROUND(
                        AVG(
                            CASE
                                WHEN first_team_joined_date IS NOT NULL
                                    THEN days_unteamed_until_resolution_or_batch
                            END
                        )::numeric,
                        2
                    ) AS avg_days_to_first_team,
                    ROUND(
                        AVG(days_unteamed_until_resolution_or_batch)::numeric,
                        2
                    ) AS avg_days_unteamed_including_unresolved,
                    MAX(days_unteamed_until_resolution_or_batch) AS max_days_unteamed_including_unresolved
                FROM player_delays
            """,
        },
        required_params=("batch_id",),
        tags=("teams", "players", "registrations"),
    ),
    RealismAuditQuery(
        name="zero_match_players_by_club_affiliation",
        scope="batch",
        category="matches",
        description=(
            "Zero-match active players split by whether they have an active club "
            "membership in the batch month."
        ),
        sql="""
            WITH batch_context AS (
                SELECT
                    b.id AS batch_id,
                    b.generation_run_id,
                    b.batch_month
                FROM monthly_batches b
                WHERE b.id = :batch_id
            ),
            affiliated_players AS (
                SELECT DISTINCT
                    cm.player_id
                FROM batch_context bc
                JOIN club_memberships cm
                    ON cm.generation_run_id = bc.generation_run_id
                    AND cm.start_date <= bc.batch_month
            ),
            active_players AS (
                SELECT
                    p.id AS player_id,
                    CASE
                        WHEN af.player_id IS NULL THEN 'unaffiliated'
                        ELSE 'affiliated'
                    END AS club_affiliation_status
                FROM players p
                JOIN batch_context bc
                    ON bc.generation_run_id = p.generation_run_id
                LEFT JOIN affiliated_players af
                    ON af.player_id = p.id
                WHERE p.player_status = 'ACTIVE'
                    AND p.registration_date <= bc.batch_month
            ),
            player_match_counts AS (
                SELECT
                    ap.player_id,
                    ap.club_affiliation_status,
                    COUNT(DISTINCT m.id) AS match_count
                FROM active_players ap
                LEFT JOIN match_team_players mtp
                    ON mtp.player_id = ap.player_id
                LEFT JOIN match_teams mt
                    ON mt.id = mtp.match_team_id
                LEFT JOIN matches m
                    ON m.id = mt.match_id
                    AND m.batch_id = :batch_id
                GROUP BY ap.player_id, ap.club_affiliation_status
            )
            SELECT
                club_affiliation_status,
                COUNT(*) AS active_player_count,
                SUM(CASE WHEN match_count = 0 THEN 1 ELSE 0 END) AS zero_match_player_count,
                ROUND(
                    100.0 * SUM(CASE WHEN match_count = 0 THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(*), 0),
                    2
                ) AS zero_match_player_pct
            FROM player_match_counts
            GROUP BY club_affiliation_status
            ORDER BY
                CASE club_affiliation_status
                    WHEN 'affiliated' THEN 0
                    ELSE 1
                END
        """,
        required_params=("batch_id",),
        tags=("matches", "cadence", "players", "clubs"),
    ),
    RealismAuditQuery(
        name="daily_team_match_cap_violations",
        scope="batch",
        category="matches",
        description="Active team rosters exceeding the configured same-day match cap.",
        sql="""
            WITH match_team_rosters AS (
                SELECT
                    m.match_date,
                    CAST(MIN(mtp.player_id) AS TEXT) || ':' || CAST(MAX(mtp.player_id) AS TEXT) AS roster_key,
                    MIN(mtp.player_id) AS player_one_id,
                    MAX(mtp.player_id) AS player_two_id
                FROM matches m
                JOIN match_teams mt
                    ON mt.match_id = m.id
                JOIN match_team_players mtp
                    ON mtp.match_team_id = mt.id
                WHERE m.batch_id = :batch_id
                GROUP BY mt.id, m.match_date
            )
            SELECT
                roster_key,
                player_one_id,
                player_two_id,
                match_date,
                COUNT(*) AS daily_match_count,
                :max_daily_matches_per_team AS configured_max_daily_matches
            FROM match_team_rosters
            GROUP BY roster_key, player_one_id, player_two_id, match_date
            HAVING COUNT(*) > :max_daily_matches_per_team
            ORDER BY daily_match_count DESC, match_date ASC, roster_key ASC
        """,
        required_params=("batch_id", "max_daily_matches_per_team"),
        tags=("matches", "cadence", "violations"),
        related_config_keys=("match_scheduling.max_daily_matches_per_team",),
    ),
    RealismAuditQuery(
        name="batch_region_match_distribution",
        scope="batch",
        category="matches",
        description="Observed region-level match concentration for one monthly batch.",
        sql="""
            SELECT
                r.id AS region_id,
                r.region_name,
                COUNT(*) AS match_count,
                ROUND(
                    100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0),
                    2
                ) AS match_pct
            FROM matches m
            LEFT JOIN regions r
                ON r.id = m.region_id
            WHERE m.batch_id = :batch_id
            GROUP BY r.id, r.region_name
            ORDER BY match_count DESC, r.region_name ASC
        """,
        required_params=("batch_id",),
        tags=("matches", "regions"),
    ),
    RealismAuditQuery(
        name="game_competitiveness_summary",
        scope="batch",
        category="scores",
        description="Game margin and extension-rate summary for one monthly batch.",
        sql="""
            SELECT
                m.batch_id,
                COUNT(g.id) AS game_count,
                ROUND(AVG(ABS(g.team_one_score - g.team_two_score)), 3) AS avg_margin,
                SUM(
                    CASE
                        WHEN (
                            CASE
                                WHEN g.team_one_score >= g.team_two_score THEN g.team_one_score
                                ELSE g.team_two_score
                            END
                        ) > g.target_score
                        THEN 1
                        ELSE 0
                    END
                ) AS extended_game_count,
                ROUND(
                    100.0 * SUM(
                        CASE
                            WHEN (
                                CASE
                                    WHEN g.team_one_score >= g.team_two_score THEN g.team_one_score
                                    ELSE g.team_two_score
                                END
                            ) > g.target_score
                            THEN 1
                            ELSE 0
                        END
                    ) / NULLIF(COUNT(g.id), 0),
                    2
                ) AS extended_game_pct
            FROM match_games g
            JOIN matches m
                ON m.id = g.match_id
            WHERE m.batch_id = :batch_id
            GROUP BY m.batch_id
        """,
        required_params=("batch_id",),
        tags=("games", "scores"),
    ),
    RealismAuditQuery(
        name="game_margin_distribution",
        scope="batch",
        category="scores",
        description="Distribution of per-game score margins for one monthly batch.",
        sql="""
            WITH game_margins AS (
                SELECT
                    CASE
                        WHEN ABS(g.team_one_score - g.team_two_score) <= 2 THEN '0_2'
                        WHEN ABS(g.team_one_score - g.team_two_score) <= 5 THEN '3_5'
                        WHEN ABS(g.team_one_score - g.team_two_score) <= 8 THEN '6_8'
                        ELSE '9_plus'
                    END AS margin_bucket
                FROM match_games g
                JOIN matches m
                    ON m.id = g.match_id
                WHERE m.batch_id = :batch_id
            )
            SELECT
                margin_bucket,
                COUNT(*) AS game_count,
                ROUND(
                    100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0),
                    2
                ) AS game_pct
            FROM game_margins
            GROUP BY margin_bucket
            ORDER BY
                CASE margin_bucket
                    WHEN '0_2' THEN 0
                    WHEN '3_5' THEN 1
                    WHEN '6_8' THEN 2
                    ELSE 3
                END
        """,
        required_params=("batch_id",),
        tags=("games", "scores", "distribution"),
    ),
    RealismAuditQuery(
        name="upset_rate_summary",
        scope="batch",
        category="scores",
        description="Observed upset rate relative to the predicted favorite in one monthly batch.",
        sql="""
            WITH match_outcomes AS (
                SELECT
                    m.id AS match_id,
                    m.batch_id,
                    m.predicted_winning_team_number,
                    m.predicted_win_probability,
                    MAX(
                        CASE
                            WHEN mt.id = m.winning_team_id
                            THEN mt.team_number
                            ELSE NULL
                        END
                    ) AS actual_winning_team_number
                FROM matches m
                JOIN match_teams mt
                    ON mt.match_id = m.id
                WHERE m.batch_id = :batch_id
                GROUP BY
                    m.id,
                    m.batch_id,
                    m.predicted_winning_team_number,
                    m.predicted_win_probability
            )
            SELECT
                batch_id,
                COUNT(*) AS total_matches,
                SUM(
                    CASE
                        WHEN predicted_winning_team_number <> actual_winning_team_number
                        THEN 1
                        ELSE 0
                    END
                ) AS upset_match_count,
                ROUND(
                    100.0 * SUM(
                        CASE
                            WHEN predicted_winning_team_number <> actual_winning_team_number
                            THEN 1
                            ELSE 0
                        END
                    ) / NULLIF(COUNT(*), 0),
                    2
                ) AS upset_match_pct,
                ROUND(AVG(predicted_win_probability), 4) AS avg_predicted_win_probability
            FROM match_outcomes
            GROUP BY batch_id
        """,
        required_params=("batch_id",),
        tags=("matches", "scores", "upsets"),
    ),
    RealismAuditQuery(
        name="predicted_vs_actual_outcome_buckets",
        scope="batch",
        category="scores",
        description="Favorite win rates by predicted win-probability bucket for one monthly batch.",
        sql="""
            WITH match_outcomes AS (
                SELECT
                    m.id AS match_id,
                    m.predicted_winning_team_number,
                    m.predicted_win_probability,
                    MAX(
                        CASE
                            WHEN mt.id = m.winning_team_id
                            THEN mt.team_number
                            ELSE NULL
                        END
                    ) AS actual_winning_team_number
                FROM matches m
                JOIN match_teams mt
                    ON mt.match_id = m.id
                WHERE m.batch_id = :batch_id
                GROUP BY
                    m.id,
                    m.predicted_winning_team_number,
                    m.predicted_win_probability
            ),
            bucketed AS (
                SELECT
                    CASE
                        WHEN predicted_win_probability < 0.60 THEN '50_59'
                        WHEN predicted_win_probability < 0.70 THEN '60_69'
                        WHEN predicted_win_probability < 0.80 THEN '70_79'
                        WHEN predicted_win_probability < 0.90 THEN '80_89'
                        ELSE '90_plus'
                    END AS probability_bucket,
                    predicted_win_probability,
                    CASE
                        WHEN predicted_winning_team_number = actual_winning_team_number
                        THEN 1
                        ELSE 0
                    END AS favorite_won
                FROM match_outcomes
            )
            SELECT
                probability_bucket,
                COUNT(*) AS match_count,
                SUM(favorite_won) AS favorite_win_count,
                ROUND(
                    100.0 * SUM(favorite_won) / NULLIF(COUNT(*), 0),
                    2
                ) AS favorite_win_pct,
                ROUND(AVG(predicted_win_probability), 4) AS avg_predicted_win_probability
            FROM bucketed
            GROUP BY probability_bucket
            ORDER BY
                CASE probability_bucket
                    WHEN '50_59' THEN 0
                    WHEN '60_69' THEN 1
                    WHEN '70_79' THEN 2
                    WHEN '80_89' THEN 3
                    ELSE 4
                END
        """,
        required_params=("batch_id",),
        tags=("matches", "scores", "probabilities"),
    ),
    RealismAuditQuery(
        name="rating_summary_by_batch",
        scope="generation_run",
        category="ratings",
        description="Per-batch current-rating summary and spread trend across the full generation run.",
        sql="""
            WITH ordered_batches AS (
                SELECT
                    b.id AS batch_id,
                    b.batch_month,
                    ROW_NUMBER() OVER (
                        ORDER BY b.batch_month ASC, b.batch_sequence ASC, b.id ASC
                    ) AS batch_ordinal
                FROM monthly_batches b
                WHERE b.generation_run_id = :generation_run_id
            ),
            player_batch_terminal_ratings AS (
                SELECT
                    prh.player_id,
                    source_batch.batch_ordinal AS start_batch_ordinal,
                    prh.rating_value,
                    ROW_NUMBER() OVER (
                        PARTITION BY prh.player_id, prh.batch_id
                        ORDER BY prh.rating_date DESC, prh.id DESC
                    ) AS rn
                FROM player_rating_history prh
                JOIN ordered_batches source_batch
                    ON source_batch.batch_id = prh.batch_id
            ),
            player_rating_spans AS (
                SELECT
                    player_id,
                    start_batch_ordinal,
                    COALESCE(
                        LEAD(start_batch_ordinal) OVER (
                            PARTITION BY player_id
                            ORDER BY start_batch_ordinal
                        ),
                        (SELECT MAX(batch_ordinal) + 1 FROM ordered_batches)
                    ) AS end_batch_ordinal,
                    rating_value
                FROM player_batch_terminal_ratings
                WHERE rn = 1
            ),
            latest_ratings AS (
                SELECT
                    ob.batch_id,
                    ob.batch_month,
                    prs.player_id,
                    prs.rating_value
                FROM player_rating_spans prs
                JOIN players p
                    ON p.id = prs.player_id
                    AND p.generation_run_id = :generation_run_id
                JOIN ordered_batches ob
                    ON ob.batch_ordinal >= prs.start_batch_ordinal
                    AND ob.batch_ordinal < prs.end_batch_ordinal
                    AND p.registration_date <= ob.batch_month
            )
            SELECT
                batch_id,
                batch_month,
                COUNT(*) AS rated_player_count,
                ROUND(AVG(rating_value), 3) AS avg_rating,
                MIN(rating_value) AS min_rating,
                MAX(rating_value) AS max_rating,
                ROUND(MAX(rating_value) - MIN(rating_value), 3) AS rating_range,
                SUM(CASE WHEN rating_value < 1000 THEN 1 ELSE 0 END) AS sub_1000_count,
                SUM(CASE WHEN rating_value >= 2000 THEN 1 ELSE 0 END) AS rating_2000_plus_count
            FROM latest_ratings
            GROUP BY batch_id, batch_month
            ORDER BY batch_month ASC, batch_id ASC
        """,
        required_params=("generation_run_id",),
        tags=("ratings", "batches", "distribution"),
    ),
    RealismAuditQuery(
        name="rating_band_distribution_by_batch",
        scope="generation_run",
        category="ratings",
        description="Per-batch current-rating band distribution across the full generation run.",
        sql="""
            WITH ordered_batches AS (
                SELECT
                    b.id AS batch_id,
                    b.batch_month,
                    ROW_NUMBER() OVER (
                        ORDER BY b.batch_month ASC, b.batch_sequence ASC, b.id ASC
                    ) AS batch_ordinal
                FROM monthly_batches b
                WHERE b.generation_run_id = :generation_run_id
            ),
            player_batch_terminal_ratings AS (
                SELECT
                    prh.player_id,
                    source_batch.batch_ordinal AS start_batch_ordinal,
                    prh.rating_value,
                    ROW_NUMBER() OVER (
                        PARTITION BY prh.player_id, prh.batch_id
                        ORDER BY prh.rating_date DESC, prh.id DESC
                    ) AS rn
                FROM player_rating_history prh
                JOIN ordered_batches source_batch
                    ON source_batch.batch_id = prh.batch_id
            ),
            player_rating_spans AS (
                SELECT
                    player_id,
                    start_batch_ordinal,
                    COALESCE(
                        LEAD(start_batch_ordinal) OVER (
                            PARTITION BY player_id
                            ORDER BY start_batch_ordinal
                        ),
                        (SELECT MAX(batch_ordinal) + 1 FROM ordered_batches)
                    ) AS end_batch_ordinal,
                    rating_value
                FROM player_batch_terminal_ratings
                WHERE rn = 1
            ),
            latest_ratings AS (
                SELECT
                    ob.batch_id,
                    ob.batch_month,
                    prs.player_id,
                    prs.rating_value
                FROM player_rating_spans prs
                JOIN players p
                    ON p.id = prs.player_id
                    AND p.generation_run_id = :generation_run_id
                JOIN ordered_batches ob
                    ON ob.batch_ordinal >= prs.start_batch_ordinal
                    AND ob.batch_ordinal < prs.end_batch_ordinal
                    AND p.registration_date <= ob.batch_month
            ),
            bucketed AS (
                SELECT
                    batch_id,
                    batch_month,
                    CASE
                        WHEN rating_value < 1000 THEN 'sub_1000'
                        WHEN rating_value < 1500 THEN '1000_1499'
                        WHEN rating_value < 2000 THEN '1500_1999'
                        ELSE '2000_plus'
                    END AS rating_band
                FROM latest_ratings
            )
            SELECT
                batch_id,
                batch_month,
                rating_band,
                COUNT(*) AS player_count,
                ROUND(
                    100.0 * COUNT(*) / NULLIF(
                        SUM(COUNT(*)) OVER (PARTITION BY batch_id),
                        0
                    ),
                    2
                ) AS player_pct
            FROM bucketed
            GROUP BY batch_id, batch_month, rating_band
            ORDER BY
                batch_month ASC,
                batch_id ASC,
                CASE rating_band
                    WHEN 'sub_1000' THEN 0
                    WHEN '1000_1499' THEN 1
                    WHEN '1500_1999' THEN 2
                    ELSE 3
                END
        """,
        required_params=("generation_run_id",),
        tags=("ratings", "batches", "distribution"),
    ),
    RealismAuditQuery(
        name="rating_delta_summary",
        scope="batch",
        category="ratings",
        description="Batch-level rating movement summary keyed to the configured warning threshold.",
        sql="""
            SELECT
                r.batch_id,
                COUNT(*) AS player_update_count,
                ROUND(AVG(ABS(r.rating_delta)), 3) AS avg_abs_rating_delta,
                MAX(ABS(r.rating_delta)) AS max_abs_rating_delta,
                SUM(
                    CASE
                        WHEN ABS(r.rating_delta) >= :rating_delta_warning_threshold
                        THEN 1
                        ELSE 0
                    END
                ) AS large_delta_count,
                ROUND(
                    100.0 * SUM(
                        CASE
                            WHEN ABS(r.rating_delta) >= :rating_delta_warning_threshold
                            THEN 1
                            ELSE 0
                        END
                    ) / NULLIF(COUNT(*), 0),
                    2
                ) AS large_delta_pct,
                :rating_delta_warning_threshold AS configured_warning_threshold
            FROM ratings_update_log r
            WHERE r.batch_id = :batch_id
            GROUP BY r.batch_id
        """,
        required_params=("batch_id", "rating_delta_warning_threshold"),
        tags=("ratings", "validation"),
        related_config_keys=("ratings.rating_movement_warning_threshold",),
    ),
    RealismAuditQuery(
        name="rating_delta_distribution",
        scope="batch",
        category="ratings",
        description="Distribution of absolute rating deltas for one monthly batch.",
        sql="""
            WITH bucketed AS (
                SELECT
                    CASE
                        WHEN ABS(r.rating_delta) < 25 THEN 'under_25'
                        WHEN ABS(r.rating_delta) < 50 THEN '25_49'
                        WHEN ABS(r.rating_delta) < 100 THEN '50_99'
                        WHEN ABS(r.rating_delta) < 200 THEN '100_199'
                        ELSE '200_plus'
                    END AS delta_bucket
                FROM ratings_update_log r
                WHERE r.batch_id = :batch_id
            )
            SELECT
                delta_bucket,
                COUNT(*) AS player_update_count,
                ROUND(
                    100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0),
                    2
                ) AS player_update_pct
            FROM bucketed
            GROUP BY delta_bucket
            ORDER BY
                CASE delta_bucket
                    WHEN 'under_25' THEN 0
                    WHEN '25_49' THEN 1
                    WHEN '50_99' THEN 2
                    WHEN '100_199' THEN 3
                    ELSE 4
                END
        """,
        required_params=("batch_id",),
        tags=("ratings", "distribution"),
    ),
    RealismAuditQuery(
        name="rating_delta_by_confidence_band",
        scope="batch",
        category="ratings",
        description="Rating-movement summary grouped by pre-match confidence band.",
        sql="""
            WITH banded AS (
                SELECT
                    CASE
                        WHEN r.confidence_before IS NULL THEN 'unknown'
                        WHEN r.confidence_before < 0.25 THEN '0_24'
                        WHEN r.confidence_before < 0.50 THEN '25_49'
                        WHEN r.confidence_before < 0.75 THEN '50_74'
                        ELSE '75_plus'
                    END AS confidence_band,
                    ABS(r.rating_delta) AS abs_rating_delta
                FROM ratings_update_log r
                WHERE r.batch_id = :batch_id
            )
            SELECT
                confidence_band,
                COUNT(*) AS player_update_count,
                ROUND(AVG(abs_rating_delta), 3) AS avg_abs_rating_delta,
                MAX(abs_rating_delta) AS max_abs_rating_delta
            FROM banded
            GROUP BY confidence_band
            ORDER BY
                CASE confidence_band
                    WHEN 'unknown' THEN 0
                    WHEN '0_24' THEN 1
                    WHEN '25_49' THEN 2
                    WHEN '50_74' THEN 3
                    ELSE 4
                END
        """,
        required_params=("batch_id",),
        tags=("ratings", "confidence"),
    ),
    RealismAuditQuery(
        name="rating_outlier_players",
        scope="batch",
        category="ratings",
        description="Players with the largest rating swings in one monthly batch.",
        sql="""
            SELECT
                r.player_id,
                p.first_name,
                p.last_name,
                COUNT(*) AS update_count,
                ROUND(AVG(ABS(r.rating_delta)), 3) AS avg_abs_rating_delta,
                MAX(ABS(r.rating_delta)) AS max_abs_rating_delta,
                ROUND(SUM(r.rating_delta), 3) AS net_rating_delta
            FROM ratings_update_log r
            JOIN players p
                ON p.id = r.player_id
            WHERE r.batch_id = :batch_id
            GROUP BY r.player_id, p.first_name, p.last_name
            ORDER BY max_abs_rating_delta DESC, avg_abs_rating_delta DESC, r.player_id ASC
            LIMIT 25
        """,
        required_params=("batch_id",),
        tags=("ratings", "outliers"),
    ),
)


class RealismAuditRunner:
    """Execute named audit queries against the current database."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self._queries_by_name = {query.name: query for query in REALISM_AUDIT_QUERIES}

    def run(
        self,
        *,
        query_names: Sequence[str] | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> tuple[RealismAuditResult, ...]:
        """Run one or more realism audit queries and return row mappings."""
        selected_queries = self._select_queries(query_names)
        if params is None:
            params = resolve_realism_audit_parameters(self.session)

        results: list[RealismAuditResult] = []
        dialect_name = (
            self.session.bind.dialect.name
            if self.session.bind is not None
            else "default"
        )
        for query in selected_queries:
            missing = [name for name in query.required_params if params.get(name) is None]
            if missing:
                raise ValueError(
                    f"Audit query {query.name!r} requires parameters: {', '.join(missing)}."
                )

            sql_params = {
                name: _sql_value(params[name])
                for name in query.required_params
                if name in params
            }
            rows = tuple(
                dict(row)
                for row in self.session.execute(
                    text(query.sql_for_dialect(dialect_name)),
                    sql_params,
                ).mappings()
            )
            if query.post_process is not None:
                rows = query.post_process(rows, params)
            results.append(RealismAuditResult(query=query, rows=rows))
        return tuple(results)

    def available_queries(self) -> tuple[RealismAuditQuery, ...]:
        """Return all registered realism audit queries."""
        return REALISM_AUDIT_QUERIES

    def _select_queries(
        self,
        query_names: Sequence[str] | None,
    ) -> tuple[RealismAuditQuery, ...]:
        if not query_names:
            return REALISM_AUDIT_QUERIES

        selected: list[RealismAuditQuery] = []
        for name in query_names:
            query = self._queries_by_name.get(name)
            if query is None:
                available = ", ".join(sorted(self._queries_by_name))
                raise ValueError(
                    f"Unknown audit query {name!r}. Available queries: {available}."
                )
            selected.append(query)
        return tuple(selected)


def resolve_realism_audit_parameters(
    session: Session,
) -> dict[str, Any]:
    """Resolve audit thresholds from defaults and the run snapshot when available."""
    resolved_generation_run_id = _latest_generation_run_id(session)
    resolved_batch_id = None
    if resolved_generation_run_id is not None:
        resolved_batch_id = _latest_batch_id_for_generation_run(
            session,
            generation_run_id=resolved_generation_run_id,
        )

    payload = DEFAULT_CONFIG_PAYLOAD
    if resolved_generation_run_id is not None:
        parameter_snapshot = session.scalar(
            select(GenerationRun.parameter_snapshot).where(
                GenerationRun.id == resolved_generation_run_id
            )
        )
        payload = _payload_mapping(parameter_snapshot, default=payload)

    return {
        "generation_run_id": resolved_generation_run_id,
        "batch_id": resolved_batch_id,
        "weekend_concentration_min": _payload_number(
            payload,
            ("validation", "weekend_concentration_min"),
            Decimal("0.40"),
        ),
        "weekend_concentration_max": _payload_number(
            payload,
            ("validation", "weekend_concentration_max"),
            Decimal("0.60"),
        ),
        "rating_delta_warning_threshold": _payload_number(
            payload,
            ("ratings", "rating_movement_warning_threshold"),
            Decimal("300"),
        ),
        "initial_rating_elite_min": _payload_number(
            payload,
            ("ratings", "initial_rating_elite_min"),
            Decimal("4000"),
        ),
        "max_club_fill_ratio": _payload_number(
            payload,
            ("club_generation", "max_club_fill_ratio"),
            Decimal("1.0"),
        ),
        "unaffiliated_player_rate": _payload_number(
            payload,
            ("club_generation", "unaffiliated_player_rate"),
            Decimal("0.12"),
        ),
        "multi_club_membership_rate": _payload_number(
            payload,
            ("club_generation", "multi_club_membership_rate"),
            Decimal("0.06"),
        ),
        "secondary_membership_same_region_rate": _payload_number(
            payload,
            ("club_generation", "secondary_membership_same_region_rate"),
            Decimal("0.85"),
        ),
        "cross_region_assignment_enabled": _payload_bool(
            payload,
            ("club_generation", "cross_region_assignment_enabled"),
            False,
        ),
        "max_daily_matches_per_team": _payload_int(
            payload,
            ("match_scheduling", "max_daily_matches_per_team"),
            2,
        ),
        "monthly_matches_per_active_player_mean": _payload_number(
            payload,
            ("match_scheduling", "monthly_matches_per_active_player_mean"),
            Decimal("8.0"),
        ),
        "monthly_matches_per_active_player_std_dev": _payload_number(
            payload,
            ("match_scheduling", "monthly_matches_per_active_player_std_dev"),
            Decimal("4.0"),
        ),
        "match_volume_noise_factor": _payload_number(
            payload,
            ("match_scheduling", "match_volume_noise_factor"),
            Decimal("0.15"),
        ),
        "player_status_target_pcts": _payload_pct_map(
            payload,
            ("player_generation", "player_status_weights"),
            value_map={
                "active": "ACTIVE",
                "injured": "INJURED",
                "inactive": "INACTIVE",
                "retired": "RETIRED",
            },
        ),
        "gender_target_pcts": _payload_pct_map(
            payload,
            ("player_generation", "gender_weights"),
            value_map={"male": "M", "female": "F"},
        ),
        "age_bucket_target_pcts": _payload_pct_map(
            payload,
            ("player_generation", "age_distribution"),
        ),
        "match_type_target_pcts": _payload_pct_map(
            payload,
            ("match_types", "weights"),
        ),
    }


def _payload_number(
    payload: Mapping[str, Any],
    path: tuple[str, ...],
    default: Decimal,
) -> Decimal:
    value: Any = payload
    for part in path:
        if not isinstance(value, Mapping) or part not in value:
            return default
        value = value[part]
    try:
        return Decimal(str(value))
    except ArithmeticError:
        return default


def _payload_int(
    payload: Mapping[str, Any],
    path: tuple[str, ...],
    default: int,
) -> int:
    value: Any = payload
    for part in path:
        if not isinstance(value, Mapping) or part not in value:
            return default
        value = value[part]
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _payload_bool(
    payload: Mapping[str, Any],
    path: tuple[str, ...],
    default: bool,
) -> bool:
    value: Any = payload
    for part in path:
        if not isinstance(value, Mapping) or part not in value:
            return default
        value = value[part]
    return bool(value)


def _payload_pct_map(
    payload: Mapping[str, Any],
    path: tuple[str, ...],
    value_map: Mapping[str, str] | None = None,
) -> dict[str, float]:
    value: Any = payload
    for part in path:
        if not isinstance(value, Mapping) or part not in value:
            return {}
        value = value[part]
    if not isinstance(value, Mapping):
        return {}

    raw_items = []
    for key, item_value in value.items():
        try:
            numeric_value = Decimal(str(item_value))
        except ArithmeticError:
            continue
        raw_items.append((value_map.get(str(key), str(key)) if value_map else str(key), numeric_value))

    total = sum(item_value for _, item_value in raw_items)
    if total <= 0:
        return {}
    return {
        key: float((item_value / total * Decimal("100")).quantize(Decimal("0.01")))
        for key, item_value in raw_items
    }


def _payload_mapping(value: Any, *, default: Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return default
        return parsed if isinstance(parsed, Mapping) else default
    return default


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sql_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return value


def _latest_generation_run_id(session: Session) -> int | None:
    latest_auditable_run_id = session.scalar(
        select(GenerationRun.id)
        .where(
            select(MonthlyBatch.id)
            .where(MonthlyBatch.generation_run_id == GenerationRun.id)
            .exists()
        )
        .order_by(GenerationRun.created_at.desc(), GenerationRun.id.desc())
        .limit(1)
    )
    if latest_auditable_run_id is not None:
        return latest_auditable_run_id

    return session.scalar(
        select(GenerationRun.id)
        .order_by(GenerationRun.created_at.desc(), GenerationRun.id.desc())
        .limit(1)
    )


def _latest_batch_id_for_generation_run(
    session: Session,
    *,
    generation_run_id: int,
) -> int | None:
    return session.scalar(
        select(MonthlyBatch.id)
        .where(MonthlyBatch.generation_run_id == generation_run_id)
        .order_by(
            MonthlyBatch.batch_month.desc(),
            MonthlyBatch.batch_sequence.desc(),
            MonthlyBatch.id.desc(),
        )
        .limit(1)
    )
