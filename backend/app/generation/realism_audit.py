"""Reusable SQL-backed realism audit queries for generated data."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import json
from typing import Any, Callable, Literal, Mapping, Sequence

from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from app.core.default_configuration import DEFAULT_CONFIG_PAYLOAD
from app.models import AuditBatchTeamRoster, GenerationRun, MonthlyBatch
from .release_certification_pillars import (
    ASSIGNMENT_READINESS_PILLAR,
    EXPORT_READINESS_PILLAR,
    HISTORICAL_REGRESSION_PILLAR,
    OPERATIONAL_REALISM_PILLAR,
    SIMULATION_FIDELITY_PILLAR,
    STRUCTURAL_INTEGRITY_PILLAR,
)


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
    pillar: str = OPERATIONAL_REALISM_PILLAR.key
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


TEAM_PARTNER_CONTINUITY_BY_BATCH_LEGACY_SQL = """
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
    has_lifecycle_events AS (
        SELECT
            CASE
                WHEN EXISTS (
                    SELECT 1
                    FROM team_lifecycle_events tle
                    WHERE tle.generation_run_id = :generation_run_id
                )
                THEN 1
                ELSE 0
            END AS has_events
    ),
    event_ranked AS (
        SELECT
            bp.batch_id,
            tle.team_id,
            tle.event_type,
            ROW_NUMBER() OVER (
                PARTITION BY bp.batch_id, tle.team_id
                ORDER BY tle.event_date DESC, tle.id DESC
            ) AS event_rank
        FROM batch_pairs bp
        JOIN team_lifecycle_events tle
            ON tle.generation_run_id = :generation_run_id
            AND tle.event_date <= bp.batch_month
    ),
    active_teams AS (
        SELECT
            er.batch_id,
            er.team_id
        FROM event_ranked er
        JOIN has_lifecycle_events h
            ON h.has_events = 1
        WHERE er.event_rank = 1
            AND er.event_type IN ('formed', 'reactivated')

        UNION ALL

        SELECT
            bp.batch_id,
            t.id AS team_id
        FROM batch_pairs bp
        JOIN has_lifecycle_events h
            ON h.has_events = 0
        JOIN teams t
            ON t.generation_run_id = :generation_run_id
            AND t.team_status = 'active'
            AND t.formation_date <= bp.batch_month
            AND (t.dissolution_date IS NULL OR t.dissolution_date > bp.batch_month)
    ),
    active_rosters AS (
        SELECT
            at.batch_id,
            CAST(MIN(tm.player_id) AS TEXT) || ':' || CAST(MAX(tm.player_id) AS TEXT) AS roster_key
        FROM active_teams at
        JOIN batch_pairs bp
            ON bp.batch_id = at.batch_id
        JOIN team_memberships tm
            ON tm.team_id = at.team_id
            AND tm.joined_date <= bp.batch_month
            AND (tm.left_date IS NULL OR tm.left_date > bp.batch_month)
        GROUP BY at.batch_id, at.team_id
        HAVING COUNT(*) = 2
    ),
    distinct_rosters AS (
        SELECT DISTINCT
            batch_id,
            roster_key
        FROM active_rosters
    ),
    classified AS (
        SELECT
            bp.batch_id,
            bp.batch_month,
            bp.prior_batch_id,
            current_rosters.roster_key,
            CASE
                WHEN prior_rosters.roster_key IS NOT NULL THEN 1
                ELSE 0
            END AS persisted_from_prior_batch
        FROM batch_pairs bp
        LEFT JOIN distinct_rosters current_rosters
            ON current_rosters.batch_id = bp.batch_id
        LEFT JOIN distinct_rosters prior_rosters
            ON prior_rosters.batch_id = bp.prior_batch_id
            AND prior_rosters.roster_key = current_rosters.roster_key
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
"""


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


FATIGUE_EFFECTIVENESS_SQL = {
    "sqlite": """
        WITH player_match_load AS (
            SELECT
                r.id AS rating_update_id,
                r.player_id,
                r.match_id,
                r.match_date,
                r.expected_score_share,
                r.actual_score_share,
                COUNT(DISTINCT prior.match_id) AS recent_match_count
            FROM ratings_update_log r
            JOIN monthly_batches b
                ON b.id = r.batch_id
            LEFT JOIN ratings_update_log prior
                ON prior.generation_run_id = r.generation_run_id
                AND prior.player_id = r.player_id
                AND prior.match_date < r.match_date
                AND julianday(r.match_date) - julianday(prior.match_date) <= 14
            WHERE b.generation_run_id = :generation_run_id
            GROUP BY
                r.id,
                r.player_id,
                r.match_id,
                r.match_date,
                r.expected_score_share,
                r.actual_score_share
        ),
        bucketed AS (
            SELECT
                CASE
                    WHEN recent_match_count = 0 THEN '0'
                    WHEN recent_match_count = 1 THEN '1'
                    ELSE '2_plus'
                END AS workload_band,
                recent_match_count,
                actual_score_share - expected_score_share AS score_share_delta
            FROM player_match_load
        )
        SELECT
            workload_band,
            COUNT(*) AS player_update_count,
            ROUND(AVG(recent_match_count), 3) AS avg_recent_match_count,
            ROUND(AVG(score_share_delta), 4) AS avg_score_share_delta,
            ROUND(
                AVG(CASE WHEN score_share_delta >= 0 THEN 1.0 ELSE 0.0 END),
                4
            ) AS met_or_exceeded_expected_rate
        FROM bucketed
        GROUP BY workload_band
        ORDER BY
            CASE workload_band
                WHEN '0' THEN 0
                WHEN '1' THEN 1
                ELSE 2
            END
    """,
    "postgresql": """
        WITH player_match_load AS (
            SELECT
                r.id AS rating_update_id,
                r.player_id,
                r.match_id,
                r.match_date,
                r.expected_score_share,
                r.actual_score_share,
                COUNT(DISTINCT prior.match_id) AS recent_match_count
            FROM ratings_update_log r
            JOIN monthly_batches b
                ON b.id = r.batch_id
            LEFT JOIN ratings_update_log prior
                ON prior.generation_run_id = r.generation_run_id
                AND prior.player_id = r.player_id
                AND prior.match_date < r.match_date
                AND prior.match_date >= r.match_date - INTERVAL '14 days'
            WHERE b.generation_run_id = :generation_run_id
            GROUP BY
                r.id,
                r.player_id,
                r.match_id,
                r.match_date,
                r.expected_score_share,
                r.actual_score_share
        ),
        bucketed AS (
            SELECT
                CASE
                    WHEN recent_match_count = 0 THEN '0'
                    WHEN recent_match_count = 1 THEN '1'
                    ELSE '2_plus'
                END AS workload_band,
                recent_match_count,
                actual_score_share - expected_score_share AS score_share_delta
            FROM player_match_load
        )
        SELECT
            workload_band,
            COUNT(*) AS player_update_count,
            ROUND(AVG(recent_match_count), 3) AS avg_recent_match_count,
            ROUND(AVG(score_share_delta), 4) AS avg_score_share_delta,
            ROUND(
                AVG(CASE WHEN score_share_delta >= 0 THEN 1.0 ELSE 0.0 END),
                4
            ) AS met_or_exceeded_expected_rate
        FROM bucketed
        GROUP BY workload_band
        ORDER BY
            CASE workload_band
                WHEN '0' THEN 0
                WHEN '1' THEN 1
                ELSE 2
            END
    """,
}


TEAM_AGE_DISTRIBUTION_SQL = {
    "sqlite": """
        WITH reference_date AS (
            SELECT MAX(batch_month) AS analysis_date
            FROM monthly_batches
            WHERE generation_run_id = :generation_run_id
        ),
        aged_teams AS (
            SELECT
                CAST(
                    julianday(COALESCE(t.dissolution_date, rd.analysis_date)) - julianday(t.formation_date)
                    AS INTEGER
                ) AS team_age_days
            FROM teams t
            CROSS JOIN reference_date rd
            WHERE t.generation_run_id = :generation_run_id
        ),
        bucketed AS (
            SELECT
                CASE
                    WHEN team_age_days < 30 THEN '0_29'
                    WHEN team_age_days < 90 THEN '30_89'
                    WHEN team_age_days < 180 THEN '90_179'
                    ELSE '180_plus'
                END AS team_age_band,
                team_age_days
            FROM aged_teams
        )
        SELECT
            team_age_band,
            COUNT(*) AS team_count,
            ROUND(AVG(team_age_days), 1) AS avg_team_age_days
        FROM bucketed
        GROUP BY team_age_band
        ORDER BY
            CASE team_age_band
                WHEN '0_29' THEN 0
                WHEN '30_89' THEN 1
                WHEN '90_179' THEN 2
                ELSE 3
            END
    """,
    "postgresql": """
        WITH reference_date AS (
            SELECT MAX(batch_month) AS analysis_date
            FROM monthly_batches
            WHERE generation_run_id = :generation_run_id
        ),
        aged_teams AS (
            SELECT
                CAST(
                    COALESCE(t.dissolution_date, rd.analysis_date) - t.formation_date
                    AS INTEGER
                ) AS team_age_days
            FROM teams t
            CROSS JOIN reference_date rd
            WHERE t.generation_run_id = :generation_run_id
        ),
        bucketed AS (
            SELECT
                CASE
                    WHEN team_age_days < 30 THEN '0_29'
                    WHEN team_age_days < 90 THEN '30_89'
                    WHEN team_age_days < 180 THEN '90_179'
                    ELSE '180_plus'
                END AS team_age_band,
                team_age_days
            FROM aged_teams
        )
        SELECT
            team_age_band,
            COUNT(*) AS team_count,
            ROUND(AVG(team_age_days), 1) AS avg_team_age_days
        FROM bucketed
        GROUP BY team_age_band
        ORDER BY
            CASE team_age_band
                WHEN '0_29' THEN 0
                WHEN '30_89' THEN 1
                WHEN '90_179' THEN 2
                ELSE 3
            END
    """,
}


REALISM_AUDIT_QUERIES: tuple[RealismAuditQuery, ...] = (
    RealismAuditQuery(
        name="player_roster_summary",
        scope="generation_run",
        category="players",
        description=(
            "Top-line player, status, and club-affiliation counts for one "
            "generation run. Club unaffiliated status is descriptive and does "
            "not imply match ineligibility."
        ),
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
            aligned AS (
                SELECT
                    CASE
                        WHEN pc.country_code IS NULL THEN 'missing_reference'
                        WHEN EXISTS (
                            SELECT 1
                            FROM last_names ln
                            WHERE ln.country_code = pc.country_code
                                AND ln.state_province_code = pc.state_province_code
                                AND ln.last_name = pc.last_name
                        ) THEN 'exact_state'
                        WHEN EXISTS (
                            SELECT 1
                            FROM last_names ln
                            WHERE ln.country_code = pc.country_code
                                AND ln.last_name = pc.last_name
                        ) THEN 'country_other_state'
                        ELSE 'missing_reference'
                    END AS alignment_bucket
                FROM player_context pc
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
        description=(
            "Observed club-membership summary versus configured unaffiliated "
            "and multi-club targets. Unaffiliated players can still be eligible "
            "for ad hoc matches."
        ),
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
        description=(
            "Primary-club membership summary for one generation run. Zero "
            "primary memberships represent unaffiliated players; multiple "
            "primary memberships are integrity issues."
        ),
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
        pillar=STRUCTURAL_INTEGRITY_PILLAR.key,
    ),
    RealismAuditQuery(
        name="team_current_roster_integrity",
        scope="generation_run",
        category="teams",
        description="Active teams whose current open roster does not contain exactly two members.",
        sql="""
            SELECT
                t.id AS team_id,
                t.team_type,
                t.team_division,
                t.team_status,
                t.country_code,
                t.formation_date,
                t.dissolution_date,
                COUNT(tm.id) AS current_member_count
            FROM teams t
            LEFT JOIN team_memberships tm
                ON tm.team_id = t.id
                AND tm.left_date IS NULL
            WHERE t.generation_run_id = :generation_run_id
                AND t.team_status = 'active'
            GROUP BY
                t.id,
                t.team_type,
                t.team_division,
                t.team_status,
                t.country_code,
                t.formation_date,
                t.dissolution_date
            HAVING COUNT(tm.id) <> 2
            ORDER BY t.id ASC
        """,
        required_params=("generation_run_id",),
        tags=("teams", "integrity", "rosters"),
        pillar=STRUCTURAL_INTEGRITY_PILLAR.key,
    ),
    RealismAuditQuery(
        name="team_membership_date_integrity",
        scope="generation_run",
        category="teams",
        description="Team memberships with temporal inconsistencies relative to team lifecycle dates.",
        sql="""
            SELECT
                t.id AS team_id,
                tm.player_id,
                t.team_type,
                t.team_division,
                t.team_status,
                t.formation_date,
                t.dissolution_date,
                tm.joined_date,
                tm.left_date,
                CASE
                    WHEN tm.joined_date < t.formation_date THEN 'joined_before_formation'
                    WHEN tm.left_date IS NOT NULL AND tm.left_date <= tm.joined_date THEN 'left_not_after_joined'
                    WHEN t.dissolution_date IS NOT NULL AND tm.left_date IS NULL THEN 'open_membership_on_dissolved_team'
                    WHEN t.dissolution_date IS NOT NULL AND tm.joined_date > t.dissolution_date THEN 'joined_after_team_dissolution'
                    WHEN t.dissolution_date IS NOT NULL
                        AND tm.left_date IS NOT NULL
                        AND tm.left_date > t.dissolution_date
                        THEN 'left_after_team_dissolution'
                END AS issue_type
            FROM teams t
            JOIN team_memberships tm
                ON tm.team_id = t.id
            WHERE t.generation_run_id = :generation_run_id
                AND (
                    tm.joined_date < t.formation_date
                    OR (tm.left_date IS NOT NULL AND tm.left_date <= tm.joined_date)
                    OR (t.dissolution_date IS NOT NULL AND tm.left_date IS NULL)
                    OR (t.dissolution_date IS NOT NULL AND tm.joined_date > t.dissolution_date)
                    OR (
                        t.dissolution_date IS NOT NULL
                        AND tm.left_date IS NOT NULL
                        AND tm.left_date > t.dissolution_date
                    )
                )
            ORDER BY t.id ASC, tm.player_id ASC
        """,
        required_params=("generation_run_id",),
        tags=("teams", "integrity", "lifecycle"),
        pillar=STRUCTURAL_INTEGRITY_PILLAR.key,
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
        name="match_team_pairing_source_distribution",
        scope="batch",
        category="matches",
        description="Observed match-team source mix for one monthly batch.",
        sql={
            "postgresql": """
                WITH source_rows AS (
                    SELECT
                        COALESCE(to_jsonb(mt) ->> 'pairing_source', 'unknown') AS pairing_source,
                        NULLIF(to_jsonb(mt) ->> 'source_team_id', '') AS source_team_id
                    FROM match_teams mt
                    JOIN matches m
                        ON m.id = mt.match_id
                    WHERE m.batch_id = :batch_id
                ),
                source_counts AS (
                    SELECT
                        pairing_source,
                        COUNT(*) AS match_team_count,
                        SUM(CASE WHEN source_team_id IS NOT NULL THEN 1 ELSE 0 END) AS source_team_count
                    FROM source_rows
                    GROUP BY pairing_source
                )
                SELECT
                    pairing_source,
                    match_team_count,
                    ROUND(
                        100.0 * match_team_count / NULLIF(SUM(match_team_count) OVER (), 0),
                        2
                    ) AS match_team_pct,
                    source_team_count,
                    ROUND(
                        100.0 * source_team_count / NULLIF(match_team_count, 0),
                        2
                    ) AS source_team_pct
                FROM source_counts
                ORDER BY
                    CASE pairing_source
                        WHEN 'competitive_team' THEN 0
                        WHEN 'ad_hoc' THEN 1
                        ELSE 2
                    END
            """,
            "default": """
                WITH source_counts AS (
                    SELECT
                        COALESCE(mt.pairing_source, 'unknown') AS pairing_source,
                        COUNT(*) AS match_team_count,
                        SUM(CASE WHEN mt.source_team_id IS NOT NULL THEN 1 ELSE 0 END) AS source_team_count
                    FROM match_teams mt
                    JOIN matches m
                        ON m.id = mt.match_id
                    WHERE m.batch_id = :batch_id
                    GROUP BY COALESCE(mt.pairing_source, 'unknown')
                )
                SELECT
                    pairing_source,
                    match_team_count,
                    ROUND(
                        100.0 * match_team_count / NULLIF(SUM(match_team_count) OVER (), 0),
                        2
                    ) AS match_team_pct,
                    source_team_count,
                    ROUND(
                        100.0 * source_team_count / NULLIF(match_team_count, 0),
                        2
                    ) AS source_team_pct
                FROM source_counts
                ORDER BY
                    CASE pairing_source
                        WHEN 'competitive_team' THEN 0
                        WHEN 'ad_hoc' THEN 1
                        ELSE 2
                    END
            """,
        },
        required_params=("batch_id",),
        tags=("matches", "teams", "pairing_source"),
        related_config_keys=(
            "matchmaking.pairing_source_weights_by_class",
            "matchmaking.pairing_source_overrides_by_type",
        ),
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
            distinct_rosters AS (
                SELECT DISTINCT
                    batch_id,
                    roster_key
                FROM audit_batch_team_rosters
                WHERE generation_run_id = :generation_run_id
            ),
            classified AS (
                SELECT
                    bp.batch_id,
                    bp.batch_month,
                    bp.prior_batch_id,
                    current_rosters.roster_key,
                    CASE
                        WHEN prior_rosters.roster_key IS NOT NULL THEN 1
                        ELSE 0
                    END AS persisted_from_prior_batch
                FROM batch_pairs bp
                LEFT JOIN distinct_rosters current_rosters
                    ON current_rosters.batch_id = bp.batch_id
                LEFT JOIN distinct_rosters prior_rosters
                    ON prior_rosters.batch_id = bp.prior_batch_id
                    AND prior_rosters.roster_key = current_rosters.roster_key
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
        description=(
            "Distribution of prior same-partner match counts for audited "
            "match-team rosters, grouped by pairing source and match class."
        ),
        sql={
            "postgresql": """
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
                        COALESCE(to_jsonb(mt) ->> 'pairing_source', 'unknown') AS pairing_source,
                        CASE
                            WHEN m.match_type IN ('recreational', 'clinic') THEN 'casual'
                            WHEN m.match_type IN ('challenge', 'ladder') THEN 'semi_competitive'
                            WHEN m.match_type IN ('league', 'tournament') THEN 'competitive'
                            ELSE 'unknown'
                        END AS match_class,
                        CAST(MIN(mtp.player_id) AS TEXT) || ':' || CAST(MAX(mtp.player_id) AS TEXT) AS roster_key
                    FROM matches m
                    JOIN match_teams mt
                        ON mt.match_id = m.id
                    JOIN match_team_players mtp
                        ON mtp.match_team_id = mt.id
                    WHERE m.batch_id = :batch_id
                    GROUP BY mt.id, COALESCE(to_jsonb(mt) ->> 'pairing_source', 'unknown'), m.match_type
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
                        cmtr.pairing_source,
                        cmtr.match_class,
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
                        pairing_source,
                        match_class,
                        prior_match_count
                    FROM prior_pair_counts
                )
                SELECT
                    pairing_source,
                    match_class,
                    prior_match_count_bucket,
                    COUNT(*) AS match_team_count,
                    ROUND(
                        100.0 * COUNT(*) / NULLIF(
                            SUM(COUNT(*)) OVER (PARTITION BY pairing_source, match_class),
                            0
                        ),
                        2
                    ) AS match_team_pct_within_source_class,
                    ROUND(AVG(prior_match_count), 2) AS avg_prior_match_count
                FROM bucketed
                GROUP BY pairing_source, match_class, prior_match_count_bucket
                ORDER BY
                    CASE pairing_source
                        WHEN 'competitive_team' THEN 0
                        WHEN 'ad_hoc' THEN 1
                        ELSE 2
                    END,
                    CASE match_class
                        WHEN 'casual' THEN 0
                        WHEN 'semi_competitive' THEN 1
                        WHEN 'competitive' THEN 2
                        ELSE 3
                    END,
                    CASE prior_match_count_bucket
                        WHEN '0' THEN 0
                        WHEN '1_2' THEN 1
                        WHEN '3_5' THEN 2
                        ELSE 3
                    END
            """,
            "default": """
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
                        COALESCE(mt.pairing_source, 'unknown') AS pairing_source,
                        CASE
                            WHEN m.match_type IN ('recreational', 'clinic') THEN 'casual'
                            WHEN m.match_type IN ('challenge', 'ladder') THEN 'semi_competitive'
                            WHEN m.match_type IN ('league', 'tournament') THEN 'competitive'
                            ELSE 'unknown'
                        END AS match_class,
                        CAST(MIN(mtp.player_id) AS TEXT) || ':' || CAST(MAX(mtp.player_id) AS TEXT) AS roster_key
                    FROM matches m
                    JOIN match_teams mt
                        ON mt.match_id = m.id
                    JOIN match_team_players mtp
                        ON mtp.match_team_id = mt.id
                    WHERE m.batch_id = :batch_id
                    GROUP BY mt.id, mt.pairing_source, m.match_type
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
                        cmtr.pairing_source,
                        cmtr.match_class,
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
                        pairing_source,
                        match_class,
                        prior_match_count
                    FROM prior_pair_counts
                )
                SELECT
                    pairing_source,
                    match_class,
                    prior_match_count_bucket,
                    COUNT(*) AS match_team_count,
                    ROUND(
                        100.0 * COUNT(*) / NULLIF(
                            SUM(COUNT(*)) OVER (PARTITION BY pairing_source, match_class),
                            0
                        ),
                        2
                    ) AS match_team_pct_within_source_class,
                    ROUND(AVG(prior_match_count), 2) AS avg_prior_match_count
                FROM bucketed
                GROUP BY pairing_source, match_class, prior_match_count_bucket
                ORDER BY
                    CASE pairing_source
                        WHEN 'competitive_team' THEN 0
                        WHEN 'ad_hoc' THEN 1
                        ELSE 2
                    END,
                    CASE match_class
                        WHEN 'casual' THEN 0
                        WHEN 'semi_competitive' THEN 1
                        WHEN 'competitive' THEN 2
                        ELSE 3
                    END,
                    CASE prior_match_count_bucket
                        WHEN '0' THEN 0
                        WHEN '1_2' THEN 1
                        WHEN '3_5' THEN 2
                        ELSE 3
                    END
            """,
        },
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
            "Zero-match active players split by active competitive-team roster "
            "status in the batch month. Untyped or unteamed players may still "
            "be match-eligible through ad hoc pairing when that source is enabled."
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
        name="zero_match_players_by_competitive_team_status",
        scope="batch",
        category="matches",
        description=(
            "Zero-match active players grouped by whether they are currently on "
            "a formal competitive team. This does not treat unteamed players as "
            "match-ineligible because ad hoc pairing may serve them."
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
            competitive_team_players AS (
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
                        WHEN ctp.player_id IS NULL THEN 'not_on_competitive_team'
                        ELSE 'on_competitive_team'
                    END AS competitive_team_status
                FROM players p
                JOIN batch_context bc
                    ON bc.generation_run_id = p.generation_run_id
                LEFT JOIN competitive_team_players ctp
                    ON ctp.player_id = p.id
                WHERE p.player_status = 'ACTIVE'
                    AND p.registration_date <= bc.batch_month
            ),
            player_match_counts AS (
                SELECT
                    ap.player_id,
                    ap.competitive_team_status,
                    COUNT(DISTINCT m.id) AS match_count
                FROM active_players ap
                LEFT JOIN match_team_players mtp
                    ON mtp.player_id = ap.player_id
                LEFT JOIN match_teams mt
                    ON mt.id = mtp.match_team_id
                LEFT JOIN matches m
                    ON m.id = mt.match_id
                    AND m.batch_id = :batch_id
                GROUP BY ap.player_id, ap.competitive_team_status
            )
            SELECT
                competitive_team_status,
                COUNT(*) AS active_player_count,
                SUM(CASE WHEN match_count = 0 THEN 1 ELSE 0 END) AS zero_match_player_count,
                ROUND(
                    100.0 * SUM(CASE WHEN match_count = 0 THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(*), 0),
                    2
                ) AS zero_match_player_pct
            FROM player_match_counts
            GROUP BY competitive_team_status
            ORDER BY
                CASE competitive_team_status
                    WHEN 'on_competitive_team' THEN 0
                    ELSE 1
                END
        """,
        required_params=("batch_id",),
        tags=("matches", "cadence", "players", "teams", "pairing_source"),
    ),
    RealismAuditQuery(
        name="team_assignment_delay_summary",
        scope="batch",
        category="teams",
        description=(
            "Average time from player registration to first formal competitive "
            "team assignment, plus the current non-formal-team inventory as of "
            "the audited batch."
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
        name="zero_match_players_by_ad_hoc_eligibility",
        scope="batch",
        category="matches",
        description=(
            "Zero-match active players split by whether they have the minimum "
            "data needed for ad hoc pairing: active status, registration by "
            "batch month, and a latest rating as of the batch."
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
            latest_ratings AS (
                SELECT
                    prh.player_id,
                    prh.rating_value,
                    ROW_NUMBER() OVER (
                        PARTITION BY prh.player_id
                        ORDER BY prh.rating_date DESC, prh.id DESC
                    ) AS rating_rank
                FROM player_rating_history prh
                JOIN batch_context bc
                    ON prh.rating_date <= bc.batch_month
            ),
            active_players AS (
                SELECT
                    p.id AS player_id,
                    CASE
                        WHEN lr.player_id IS NULL THEN 'missing_current_rating'
                        ELSE 'ad_hoc_eligible'
                    END AS ad_hoc_eligibility_status
                FROM players p
                JOIN batch_context bc
                    ON bc.generation_run_id = p.generation_run_id
                LEFT JOIN latest_ratings lr
                    ON lr.player_id = p.id
                    AND lr.rating_rank = 1
                WHERE p.player_status = 'ACTIVE'
                    AND p.registration_date <= bc.batch_month
            ),
            player_match_counts AS (
                SELECT
                    ap.player_id,
                    ap.ad_hoc_eligibility_status,
                    COUNT(DISTINCT m.id) AS match_count
                FROM active_players ap
                LEFT JOIN match_team_players mtp
                    ON mtp.player_id = ap.player_id
                LEFT JOIN match_teams mt
                    ON mt.id = mtp.match_team_id
                LEFT JOIN matches m
                    ON m.id = mt.match_id
                    AND m.batch_id = :batch_id
                GROUP BY ap.player_id, ap.ad_hoc_eligibility_status
            )
            SELECT
                ad_hoc_eligibility_status,
                COUNT(*) AS active_player_count,
                SUM(CASE WHEN match_count = 0 THEN 1 ELSE 0 END) AS zero_match_player_count,
                ROUND(
                    100.0 * SUM(CASE WHEN match_count = 0 THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(*), 0),
                    2
                ) AS zero_match_player_pct
            FROM player_match_counts
            GROUP BY ad_hoc_eligibility_status
            ORDER BY
                CASE ad_hoc_eligibility_status
                    WHEN 'ad_hoc_eligible' THEN 0
                    ELSE 1
                END
        """,
        required_params=("batch_id",),
        tags=("matches", "cadence", "players", "pairing_source", "ad_hoc"),
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
        name="match_winner_integrity",
        scope="batch",
        category="matches",
        description="Matches whose recorded winning team is missing or inconsistent with match-team scores.",
        sql="""
            SELECT
                m.id AS match_id,
                m.match_date,
                m.winning_team_id,
                COUNT(mt.id) AS team_count,
                SUM(CASE WHEN mt.source_team_id = m.winning_team_id THEN 1 ELSE 0 END) AS winning_team_row_count,
                MAX(CASE WHEN mt.source_team_id = m.winning_team_id THEN mt.team_score END) AS winning_team_score,
                MAX(CASE WHEN mt.source_team_id <> m.winning_team_id THEN mt.team_score END) AS opposing_team_score,
                CASE
                    WHEN m.winning_team_id IS NULL THEN 'missing_winning_team'
                    WHEN COUNT(mt.id) <> 2 THEN 'unexpected_team_count'
                    WHEN SUM(CASE WHEN mt.source_team_id = m.winning_team_id THEN 1 ELSE 0 END) = 0
                        THEN 'winning_team_not_in_match'
                    WHEN MAX(CASE WHEN mt.source_team_id = m.winning_team_id THEN mt.team_score END) IS NULL
                        THEN 'missing_winning_team_score'
                    WHEN MAX(CASE WHEN mt.source_team_id <> m.winning_team_id THEN mt.team_score END) IS NULL
                        THEN 'missing_opposing_team_score'
                    WHEN MAX(CASE WHEN mt.source_team_id = m.winning_team_id THEN mt.team_score END)
                        <= MAX(CASE WHEN mt.source_team_id <> m.winning_team_id THEN mt.team_score END)
                        THEN 'winning_team_not_high_score'
                END AS issue_type
            FROM matches m
            LEFT JOIN match_teams mt
                ON mt.match_id = m.id
            WHERE m.batch_id = :batch_id
            GROUP BY m.id, m.match_date, m.winning_team_id
            HAVING
                m.winning_team_id IS NULL
                OR COUNT(mt.id) <> 2
                OR SUM(CASE WHEN mt.source_team_id = m.winning_team_id THEN 1 ELSE 0 END) = 0
                OR MAX(CASE WHEN mt.source_team_id = m.winning_team_id THEN mt.team_score END) IS NULL
                OR MAX(CASE WHEN mt.source_team_id <> m.winning_team_id THEN mt.team_score END) IS NULL
                OR MAX(CASE WHEN mt.source_team_id = m.winning_team_id THEN mt.team_score END)
                    <= MAX(CASE WHEN mt.source_team_id <> m.winning_team_id THEN mt.team_score END)
            ORDER BY m.match_date ASC, m.id ASC
        """,
        required_params=("batch_id",),
        tags=("matches", "integrity", "winners"),
        pillar=STRUCTURAL_INTEGRITY_PILLAR.key,
    ),
    RealismAuditQuery(
        name="match_game_score_integrity",
        scope="batch",
        category="matches",
        description="Games whose stored winner, target score, or margin is inconsistent with the scoreline.",
        sql="""
            SELECT
                mg.match_id,
                mg.id AS game_id,
                mg.game_number,
                mg.team_one_score,
                mg.team_two_score,
                mg.winning_team_number,
                mg.target_score,
                mg.win_by,
                CASE
                    WHEN mg.winning_team_number NOT IN (1, 2) THEN 'invalid_winning_team_number'
                    WHEN mg.team_one_score = mg.team_two_score THEN 'tied_score'
                    WHEN mg.winning_team_number = 1 AND mg.team_one_score <= mg.team_two_score THEN 'winner_score_mismatch'
                    WHEN mg.winning_team_number = 2 AND mg.team_two_score <= mg.team_one_score THEN 'winner_score_mismatch'
                    WHEN (
                        CASE
                            WHEN mg.team_one_score > mg.team_two_score THEN mg.team_one_score
                            ELSE mg.team_two_score
                        END
                    ) < mg.target_score THEN 'target_score_not_reached'
                    WHEN ABS(mg.team_one_score - mg.team_two_score) < mg.win_by THEN 'win_by_not_met'
                END AS issue_type
            FROM match_games mg
            JOIN matches m
                ON m.id = mg.match_id
            WHERE m.batch_id = :batch_id
                AND (
                    mg.winning_team_number NOT IN (1, 2)
                    OR mg.team_one_score = mg.team_two_score
                    OR (mg.winning_team_number = 1 AND mg.team_one_score <= mg.team_two_score)
                    OR (mg.winning_team_number = 2 AND mg.team_two_score <= mg.team_one_score)
                    OR (
                        CASE
                            WHEN mg.team_one_score > mg.team_two_score THEN mg.team_one_score
                            ELSE mg.team_two_score
                        END
                    ) < mg.target_score
                    OR ABS(mg.team_one_score - mg.team_two_score) < mg.win_by
                )
            ORDER BY mg.match_id ASC, mg.game_number ASC, mg.id ASC
        """,
        required_params=("batch_id",),
        tags=("matches", "integrity", "scores"),
        pillar=STRUCTURAL_INTEGRITY_PILLAR.key,
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
                            WHEN mt.source_team_id = m.winning_team_id
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
                            WHEN mt.source_team_id = m.winning_team_id
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
        name="chemistry_effectiveness",
        scope="generation_run",
        category="simulation_fidelity",
        pillar=SIMULATION_FIDELITY_PILLAR.key,
        description="Observed team win rates versus expected results grouped by stored chemistry score.",
        sql="""
            WITH team_match_results AS (
                SELECT
                    CASE
                        WHEN t.chemistry_score IS NULL THEN 'unknown'
                        WHEN t.chemistry_score < 0.40 THEN 'low'
                        WHEN t.chemistry_score < 0.70 THEN 'medium'
                        ELSE 'high'
                    END AS chemistry_band,
                    t.chemistry_score,
                    CASE
                        WHEN m.predicted_winning_team_number = mt.team_number
                            THEN COALESCE(m.predicted_win_probability, 0.5)
                        ELSE 1.0 - COALESCE(m.predicted_win_probability, 0.5)
                    END AS expected_win_probability,
                    CASE
                        WHEN m.winning_team_id = mt.source_team_id THEN 1.0
                        ELSE 0.0
                    END AS actual_win_rate
                FROM match_teams mt
                JOIN matches m
                    ON m.id = mt.match_id
                JOIN monthly_batches b
                    ON b.id = m.batch_id
                JOIN teams t
                    ON t.id = mt.source_team_id
                WHERE b.generation_run_id = :generation_run_id
                    AND t.chemistry_score IS NOT NULL
            )
            SELECT
                chemistry_band,
                COUNT(*) AS team_match_count,
                ROUND(AVG(chemistry_score), 4) AS avg_chemistry_score,
                ROUND(AVG(expected_win_probability), 4) AS avg_expected_win_probability,
                ROUND(AVG(actual_win_rate), 4) AS actual_win_rate,
                ROUND(AVG(actual_win_rate) - AVG(expected_win_probability), 4) AS win_rate_minus_expected
            FROM team_match_results
            GROUP BY chemistry_band
            ORDER BY
                CASE chemistry_band
                    WHEN 'unknown' THEN 0
                    WHEN 'low' THEN 1
                    WHEN 'medium' THEN 2
                    ELSE 3
                END
        """,
        required_params=("generation_run_id",),
        tags=("simulation", "chemistry"),
    ),
    RealismAuditQuery(
        name="fatigue_effectiveness",
        scope="generation_run",
        category="simulation_fidelity",
        pillar=SIMULATION_FIDELITY_PILLAR.key,
        description="Actual-versus-expected score share grouped by recent match load within the fatigue lookback window.",
        sql=FATIGUE_EFFECTIVENESS_SQL,
        required_params=("generation_run_id",),
        tags=("simulation", "fatigue"),
    ),
    RealismAuditQuery(
        name="confidence_stability",
        scope="generation_run",
        category="simulation_fidelity",
        pillar=SIMULATION_FIDELITY_PILLAR.key,
        description="Rating-movement stability grouped by pre-match confidence bands.",
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
                    ABS(r.rating_delta) AS abs_rating_delta,
                    COALESCE(r.confidence_after, r.confidence_before) - r.confidence_before AS confidence_delta
                FROM ratings_update_log r
                JOIN monthly_batches b
                    ON b.id = r.batch_id
                WHERE b.generation_run_id = :generation_run_id
            )
            SELECT
                confidence_band,
                COUNT(*) AS player_update_count,
                ROUND(AVG(abs_rating_delta), 3) AS avg_abs_rating_delta,
                ROUND(AVG(confidence_delta), 4) AS avg_confidence_delta
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
        required_params=("generation_run_id",),
        tags=("simulation", "confidence"),
    ),
    RealismAuditQuery(
        name="volatility_decay",
        scope="generation_run",
        category="simulation_fidelity",
        pillar=SIMULATION_FIDELITY_PILLAR.key,
        description="Observed volatility levels grouped by rating-history match-count experience bands.",
        sql="""
            WITH banded AS (
                SELECT
                    CASE
                        WHEN prh.match_count_used IS NULL THEN 'unknown'
                        WHEN prh.match_count_used < 5 THEN '0_4'
                        WHEN prh.match_count_used < 10 THEN '5_9'
                        ELSE '10_plus'
                    END AS experience_band,
                    prh.volatility_score,
                    prh.confidence_score
                FROM player_rating_history prh
                JOIN monthly_batches b
                    ON b.id = prh.batch_id
                WHERE b.generation_run_id = :generation_run_id
                    AND prh.volatility_score IS NOT NULL
            )
            SELECT
                experience_band,
                COUNT(*) AS rating_snapshot_count,
                ROUND(AVG(volatility_score), 4) AS avg_volatility_score,
                ROUND(AVG(confidence_score), 4) AS avg_confidence_score
            FROM banded
            GROUP BY experience_band
            ORDER BY
                CASE experience_band
                    WHEN 'unknown' THEN 0
                    WHEN '0_4' THEN 1
                    WHEN '5_9' THEN 2
                    ELSE 3
                END
        """,
        required_params=("generation_run_id",),
        tags=("simulation", "volatility"),
    ),
    RealismAuditQuery(
        name="rating_predictiveness",
        scope="generation_run",
        category="simulation_fidelity",
        pillar=SIMULATION_FIDELITY_PILLAR.key,
        description="Predicted-win probability accuracy grouped into model-confidence buckets.",
        sql="""
            WITH bucketed AS (
                SELECT
                    CASE
                        WHEN m.predicted_win_probability IS NULL THEN 'unknown'
                        WHEN m.predicted_win_probability < 0.60 THEN '50_59'
                        WHEN m.predicted_win_probability < 0.70 THEN '60_69'
                        WHEN m.predicted_win_probability < 0.80 THEN '70_79'
                        ELSE '80_plus'
                    END AS prediction_bucket,
                    CASE
                        WHEN mt.team_number = m.predicted_winning_team_number
                            AND m.winning_team_id = mt.source_team_id
                        THEN 1.0
                        WHEN mt.team_number = m.predicted_winning_team_number
                        THEN 0.0
                        ELSE NULL
                    END AS favorite_won
                FROM matches m
                JOIN monthly_batches b
                    ON b.id = m.batch_id
                LEFT JOIN match_teams mt
                    ON mt.match_id = m.id
                    AND mt.team_number = m.predicted_winning_team_number
                WHERE b.generation_run_id = :generation_run_id
            )
            SELECT
                prediction_bucket,
                COUNT(favorite_won) AS predicted_match_count,
                ROUND(AVG(favorite_won), 4) AS favorite_win_rate
            FROM bucketed
            GROUP BY prediction_bucket
            ORDER BY
                CASE prediction_bucket
                    WHEN 'unknown' THEN 0
                    WHEN '50_59' THEN 1
                    WHEN '60_69' THEN 2
                    WHEN '70_79' THEN 3
                    ELSE 4
                END
        """,
        required_params=("generation_run_id",),
        tags=("simulation", "prediction"),
    ),
    RealismAuditQuery(
        name="regional_strength_balance",
        scope="generation_run",
        category="simulation_fidelity",
        pillar=SIMULATION_FIDELITY_PILLAR.key,
        description="Latest player-rating strength distribution by home region.",
        sql="""
            WITH latest_ratings AS (
                SELECT
                    prh.player_id,
                    prh.rating_value,
                    ROW_NUMBER() OVER (
                        PARTITION BY prh.player_id
                        ORDER BY prh.rating_date DESC, prh.id DESC
                    ) AS rating_rank
                FROM player_rating_history prh
                JOIN monthly_batches b
                    ON b.id = prh.batch_id
                WHERE b.generation_run_id = :generation_run_id
            )
            SELECT
                r.id AS region_id,
                r.country_code,
                r.state_province_code,
                r.region_name,
                COUNT(lr.player_id) AS rated_player_count,
                ROUND(AVG(lr.rating_value), 3) AS avg_rating,
                ROUND(MAX(lr.rating_value), 3) AS max_rating,
                ROUND(
                    100.0 * SUM(
                        CASE WHEN lr.rating_value >= :initial_rating_elite_min THEN 1 ELSE 0 END
                    ) / NULLIF(COUNT(lr.player_id), 0),
                    2
                ) AS elite_player_pct
            FROM players p
            JOIN regions r
                ON r.id = p.home_region_id
            LEFT JOIN latest_ratings lr
                ON lr.player_id = p.id
                AND lr.rating_rank = 1
            WHERE p.generation_run_id = :generation_run_id
            GROUP BY r.id, r.country_code, r.state_province_code, r.region_name
            HAVING COUNT(lr.player_id) >= :regional_strength_min_rated_players
            ORDER BY avg_rating DESC, rated_player_count DESC, r.id ASC
        """,
        required_params=(
            "generation_run_id",
            "initial_rating_elite_min",
            "regional_strength_min_rated_players",
        ),
        related_config_keys=("validation.regional_strength_min_rated_players",),
        tags=("simulation", "regions", "strength"),
    ),
    RealismAuditQuery(
        name="team_age_distribution",
        scope="generation_run",
        category="partnership_dynamics",
        pillar=SIMULATION_FIDELITY_PILLAR.key,
        description="Distribution of team ages in days as of the current release window.",
        sql=TEAM_AGE_DISTRIBUTION_SQL,
        required_params=("generation_run_id",),
        tags=("teams", "age"),
    ),
    RealismAuditQuery(
        name="team_dissolution_rate",
        scope="generation_run",
        category="partnership_dynamics",
        pillar=SIMULATION_FIDELITY_PILLAR.key,
        description="Lifecycle-event rate for dormant, retired, and reactivated teams relative to formed teams.",
        sql="""
            WITH formed AS (
                SELECT COUNT(*) AS formed_team_count
                FROM team_lifecycle_events
                WHERE generation_run_id = :generation_run_id
                    AND event_type = 'formed'
            ),
            event_counts AS (
                SELECT 'dormant' AS event_type
                UNION ALL SELECT 'retired'
                UNION ALL SELECT 'reactivated'
            )
            SELECT
                ec.event_type,
                (
                    SELECT COUNT(*)
                    FROM team_lifecycle_events tle
                    WHERE tle.generation_run_id = :generation_run_id
                        AND tle.event_type = ec.event_type
                ) AS event_count,
                formed.formed_team_count,
                ROUND(
                    100.0 * (
                        SELECT COUNT(*)
                        FROM team_lifecycle_events tle
                        WHERE tle.generation_run_id = :generation_run_id
                            AND tle.event_type = ec.event_type
                    ) / NULLIF(formed.formed_team_count, 0),
                    2
                ) AS event_pct_of_formed_teams
            FROM event_counts ec
            CROSS JOIN formed
            ORDER BY ec.event_type
        """,
        required_params=("generation_run_id",),
        tags=("teams", "lifecycle"),
    ),
    RealismAuditQuery(
        name="repeat_partner_frequency",
        scope="generation_run",
        category="partnership_dynamics",
        pillar=SIMULATION_FIDELITY_PILLAR.key,
        description="How often the same two-player partnership reappears across matches in one run.",
        sql="""
            WITH roster_match_counts AS (
                SELECT
                    CAST(MIN(mtp.player_id) AS TEXT) || ':' || CAST(MAX(mtp.player_id) AS TEXT) AS roster_key,
                    COUNT(DISTINCT mt.match_id) AS partner_match_count
                FROM match_teams mt
                JOIN matches m
                    ON m.id = mt.match_id
                JOIN monthly_batches b
                    ON b.id = m.batch_id
                JOIN match_team_players mtp
                    ON mtp.match_team_id = mt.id
                WHERE b.generation_run_id = :generation_run_id
                GROUP BY mt.id
                HAVING COUNT(*) = 2
            ),
            partnership_counts AS (
                SELECT
                    roster_key,
                    COUNT(*) AS match_count
                FROM roster_match_counts
                GROUP BY roster_key
            )
            SELECT
                match_count AS repeat_match_count,
                COUNT(*) AS partnership_count,
                ROUND(
                    100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0),
                    2
                ) AS partnership_pct
            FROM partnership_counts
            GROUP BY match_count
            ORDER BY repeat_match_count ASC
        """,
        required_params=("generation_run_id",),
        tags=("teams", "partners"),
    ),
    RealismAuditQuery(
        name="repeat_opponent_rate",
        scope="generation_run",
        category="competition_ecology",
        pillar=SIMULATION_FIDELITY_PILLAR.key,
        description="Distribution of repeated opponent matchups across the generation run.",
        sql="""
            WITH team_rosters AS (
                SELECT
                    mt.match_id,
                    mt.team_number,
                    CAST(MIN(mtp.player_id) AS TEXT) || ':' || CAST(MAX(mtp.player_id) AS TEXT) AS roster_key
                FROM match_teams mt
                JOIN matches m
                    ON m.id = mt.match_id
                JOIN monthly_batches b
                    ON b.id = m.batch_id
                JOIN match_team_players mtp
                    ON mtp.match_team_id = mt.id
                WHERE b.generation_run_id = :generation_run_id
                GROUP BY mt.match_id, mt.team_number
                HAVING COUNT(*) = 2
            ),
            matchup_counts AS (
                SELECT
                    CASE
                        WHEN one.roster_key < two.roster_key
                            THEN one.roster_key || ' vs ' || two.roster_key
                        ELSE two.roster_key || ' vs ' || one.roster_key
                    END AS matchup_key,
                    COUNT(*) AS meeting_count
                FROM team_rosters one
                JOIN team_rosters two
                    ON two.match_id = one.match_id
                    AND two.team_number = 2
                WHERE one.team_number = 1
                GROUP BY matchup_key
            )
            SELECT
                meeting_count,
                COUNT(*) AS matchup_pair_count,
                ROUND(
                    100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0),
                    2
                ) AS matchup_pair_pct
            FROM matchup_counts
            GROUP BY meeting_count
            ORDER BY meeting_count ASC
        """,
        required_params=("generation_run_id",),
        tags=("matches", "opponents"),
    ),
    RealismAuditQuery(
        name="candidate_depth_by_country_division",
        scope="generation_run",
        category="assignment_readiness",
        pillar=ASSIGNMENT_READINESS_PILLAR.key,
        description="Current competitive-team candidate depth by country and division.",
        sql="""
            WITH latest_ratings AS (
                SELECT
                    prh.player_id,
                    prh.rating_value,
                    ROW_NUMBER() OVER (
                        PARTITION BY prh.player_id
                        ORDER BY prh.rating_date DESC, prh.id DESC
                    ) AS rating_rank
                FROM player_rating_history prh
                JOIN monthly_batches b
                    ON b.id = prh.batch_id
                WHERE b.generation_run_id = :generation_run_id
            ),
            active_team_rosters AS (
                SELECT
                    t.id AS team_id,
                    t.country_code,
                    t.team_division,
                    COUNT(DISTINCT tm.player_id) AS member_count,
                    ROUND(AVG(lr.rating_value), 3) AS avg_team_rating
                FROM teams t
                JOIN team_memberships tm
                    ON tm.team_id = t.id
                    AND tm.left_date IS NULL
                LEFT JOIN latest_ratings lr
                    ON lr.player_id = tm.player_id
                    AND lr.rating_rank = 1
                WHERE t.generation_run_id = :generation_run_id
                    AND t.team_type = 'competitive'
                    AND t.team_status = 'active'
                GROUP BY t.id, t.country_code, t.team_division
                HAVING COUNT(DISTINCT tm.player_id) = 2
            )
            SELECT
                country_code,
                team_division,
                COUNT(*) AS candidate_team_count,
                SUM(member_count) AS candidate_player_count,
                ROUND(AVG(avg_team_rating), 3) AS avg_team_rating
            FROM active_team_rosters
            GROUP BY country_code, team_division
            ORDER BY country_code ASC, team_division ASC
        """,
        required_params=("generation_run_id",),
        tags=("assignment", "candidates"),
    ),
    RealismAuditQuery(
        name="elite_player_depth",
        scope="generation_run",
        category="assignment_readiness",
        pillar=ASSIGNMENT_READINESS_PILLAR.key,
        description="Elite-player roster depth by country and current team division.",
        sql="""
            WITH latest_ratings AS (
                SELECT
                    prh.player_id,
                    prh.rating_value,
                    ROW_NUMBER() OVER (
                        PARTITION BY prh.player_id
                        ORDER BY prh.rating_date DESC, prh.id DESC
                    ) AS rating_rank
                FROM player_rating_history prh
                JOIN monthly_batches b
                    ON b.id = prh.batch_id
                WHERE b.generation_run_id = :generation_run_id
            )
            SELECT
                t.country_code,
                t.team_division,
                COUNT(DISTINCT CASE WHEN lr.rating_value >= :initial_rating_elite_min THEN tm.player_id END) AS elite_player_count,
                COUNT(DISTINCT tm.player_id) AS rostered_player_count,
                ROUND(
                    100.0 * COUNT(DISTINCT CASE WHEN lr.rating_value >= :initial_rating_elite_min THEN tm.player_id END)
                    / NULLIF(COUNT(DISTINCT tm.player_id), 0),
                    2
                ) AS elite_player_pct
            FROM teams t
            JOIN team_memberships tm
                ON tm.team_id = t.id
                AND tm.left_date IS NULL
            LEFT JOIN latest_ratings lr
                ON lr.player_id = tm.player_id
                AND lr.rating_rank = 1
            WHERE t.generation_run_id = :generation_run_id
                AND t.team_type = 'competitive'
                AND t.team_status = 'active'
            GROUP BY t.country_code, t.team_division
            ORDER BY t.country_code ASC, t.team_division ASC
        """,
        required_params=("generation_run_id", "initial_rating_elite_min"),
        tags=("assignment", "elite", "players"),
    ),
    RealismAuditQuery(
        name="elite_team_depth",
        scope="generation_run",
        category="assignment_readiness",
        pillar=ASSIGNMENT_READINESS_PILLAR.key,
        description="Elite-team depth by country and division using average current roster rating.",
        sql="""
            WITH latest_ratings AS (
                SELECT
                    prh.player_id,
                    prh.rating_value,
                    ROW_NUMBER() OVER (
                        PARTITION BY prh.player_id
                        ORDER BY prh.rating_date DESC, prh.id DESC
                    ) AS rating_rank
                FROM player_rating_history prh
                JOIN monthly_batches b
                    ON b.id = prh.batch_id
                WHERE b.generation_run_id = :generation_run_id
            ),
            active_team_rosters AS (
                SELECT
                    t.id AS team_id,
                    t.country_code,
                    t.team_division,
                    ROUND(AVG(lr.rating_value), 3) AS avg_team_rating
                FROM teams t
                JOIN team_memberships tm
                    ON tm.team_id = t.id
                    AND tm.left_date IS NULL
                LEFT JOIN latest_ratings lr
                    ON lr.player_id = tm.player_id
                    AND lr.rating_rank = 1
                WHERE t.generation_run_id = :generation_run_id
                    AND t.team_type = 'competitive'
                    AND t.team_status = 'active'
                GROUP BY t.id, t.country_code, t.team_division
                HAVING COUNT(DISTINCT tm.player_id) = 2
            )
            SELECT
                country_code,
                team_division,
                COUNT(*) AS candidate_team_count,
                SUM(CASE WHEN avg_team_rating >= :initial_rating_elite_min THEN 1 ELSE 0 END) AS elite_team_count,
                ROUND(
                    100.0 * SUM(CASE WHEN avg_team_rating >= :initial_rating_elite_min THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(*), 0),
                    2
                ) AS elite_team_pct
            FROM active_team_rosters
            GROUP BY country_code, team_division
            ORDER BY country_code ASC, team_division ASC
        """,
        required_params=("generation_run_id", "initial_rating_elite_min"),
        tags=("assignment", "elite", "teams"),
    ),
    RealismAuditQuery(
        name="alternate_candidate_depth",
        scope="generation_run",
        category="assignment_readiness",
        pillar=ASSIGNMENT_READINESS_PILLAR.key,
        description="Teams available beyond the top-ranked team in each country/division candidate pool.",
        sql="""
            WITH latest_ratings AS (
                SELECT
                    prh.player_id,
                    prh.rating_value,
                    ROW_NUMBER() OVER (
                        PARTITION BY prh.player_id
                        ORDER BY prh.rating_date DESC, prh.id DESC
                    ) AS rating_rank
                FROM player_rating_history prh
                JOIN monthly_batches b
                    ON b.id = prh.batch_id
                WHERE b.generation_run_id = :generation_run_id
            ),
            team_ratings AS (
                SELECT
                    t.id AS team_id,
                    t.country_code,
                    t.team_division,
                    ROUND(AVG(lr.rating_value), 3) AS avg_team_rating
                FROM teams t
                JOIN team_memberships tm
                    ON tm.team_id = t.id
                    AND tm.left_date IS NULL
                LEFT JOIN latest_ratings lr
                    ON lr.player_id = tm.player_id
                    AND lr.rating_rank = 1
                WHERE t.generation_run_id = :generation_run_id
                    AND t.team_type = 'competitive'
                    AND t.team_status = 'active'
                GROUP BY t.id, t.country_code, t.team_division
                HAVING COUNT(DISTINCT tm.player_id) = 2
            ),
            ranked_teams AS (
                SELECT
                    team_id,
                    country_code,
                    team_division,
                    avg_team_rating,
                    ROW_NUMBER() OVER (
                        PARTITION BY country_code, team_division
                        ORDER BY avg_team_rating DESC, team_id ASC
                    ) AS division_rank
                FROM team_ratings
            )
            SELECT
                country_code,
                team_division,
                COUNT(*) AS ranked_team_count,
                SUM(CASE WHEN division_rank > 1 THEN 1 ELSE 0 END) AS alternate_team_count
            FROM ranked_teams
            GROUP BY country_code, team_division
            ORDER BY country_code ASC, team_division ASC
        """,
        required_params=("generation_run_id",),
        tags=("assignment", "alternates"),
    ),
    RealismAuditQuery(
        name="missing_gold_inputs",
        scope="generation_run",
        category="export_readiness",
        pillar=EXPORT_READINESS_PILLAR.key,
        description="Required source-table row coverage for downstream Gold and student-release workflows.",
        sql="""
            SELECT 'players' AS table_name, COUNT(*) AS row_count, CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END AS missing_flag
            FROM players
            WHERE generation_run_id = :generation_run_id
            UNION ALL
            SELECT 'teams', COUNT(*), CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END
            FROM teams
            WHERE generation_run_id = :generation_run_id
            UNION ALL
            SELECT 'team_memberships', COUNT(*), CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END
            FROM team_memberships tm
            JOIN teams t ON t.id = tm.team_id
            WHERE t.generation_run_id = :generation_run_id
            UNION ALL
            SELECT 'matches', COUNT(*), CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END
            FROM matches m
            JOIN monthly_batches b ON b.id = m.batch_id
            WHERE b.generation_run_id = :generation_run_id
            UNION ALL
            SELECT 'match_teams', COUNT(*), CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END
            FROM match_teams mt
            JOIN matches m ON m.id = mt.match_id
            JOIN monthly_batches b ON b.id = m.batch_id
            WHERE b.generation_run_id = :generation_run_id
            UNION ALL
            SELECT 'match_team_players', COUNT(*), CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END
            FROM match_team_players mtp
            JOIN match_teams mt ON mt.id = mtp.match_team_id
            JOIN matches m ON m.id = mt.match_id
            JOIN monthly_batches b ON b.id = m.batch_id
            WHERE b.generation_run_id = :generation_run_id
            UNION ALL
            SELECT 'player_rating_history', COUNT(*), CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END
            FROM player_rating_history prh
            JOIN monthly_batches b ON b.id = prh.batch_id
            WHERE b.generation_run_id = :generation_run_id
            UNION ALL
            SELECT 'ratings_update_log', COUNT(*), CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END
            FROM ratings_update_log r
            JOIN monthly_batches b ON b.id = r.batch_id
            WHERE b.generation_run_id = :generation_run_id
            UNION ALL
            SELECT 'clubs', COUNT(*), CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END
            FROM clubs
            UNION ALL
            SELECT 'club_memberships', COUNT(*), CASE WHEN COUNT(*) = 0 THEN 1 ELSE 0 END
            FROM club_memberships
            WHERE generation_run_id = :generation_run_id
            ORDER BY table_name ASC
        """,
        required_params=("generation_run_id",),
        tags=("export", "gold"),
    ),
    RealismAuditQuery(
        name="student_candidate_availability",
        scope="generation_run",
        category="export_readiness",
        pillar=EXPORT_READINESS_PILLAR.key,
        description="Release-ready candidate coverage by country and division where both team members have ratings.",
        sql="""
            WITH latest_ratings AS (
                SELECT
                    prh.player_id,
                    prh.rating_value,
                    ROW_NUMBER() OVER (
                        PARTITION BY prh.player_id
                        ORDER BY prh.rating_date DESC, prh.id DESC
                    ) AS rating_rank
                FROM player_rating_history prh
                JOIN monthly_batches b
                    ON b.id = prh.batch_id
                WHERE b.generation_run_id = :generation_run_id
            ),
            rated_team_rosters AS (
                SELECT
                    t.id AS team_id,
                    t.country_code,
                    t.team_division,
                    COUNT(DISTINCT tm.player_id) AS member_count,
                    COUNT(DISTINCT lr.player_id) AS rated_member_count
                FROM teams t
                JOIN team_memberships tm
                    ON tm.team_id = t.id
                    AND tm.left_date IS NULL
                LEFT JOIN latest_ratings lr
                    ON lr.player_id = tm.player_id
                    AND lr.rating_rank = 1
                WHERE t.generation_run_id = :generation_run_id
                    AND t.team_type = 'competitive'
                    AND t.team_status = 'active'
                GROUP BY t.id, t.country_code, t.team_division
                HAVING COUNT(DISTINCT tm.player_id) = 2
            )
            SELECT
                country_code,
                team_division,
                COUNT(*) AS candidate_team_count,
                SUM(CASE WHEN rated_member_count = 2 THEN 1 ELSE 0 END) AS fully_rated_team_count,
                ROUND(
                    100.0 * SUM(CASE WHEN rated_member_count = 2 THEN 1 ELSE 0 END)
                    / NULLIF(COUNT(*), 0),
                    2
                ) AS fully_rated_team_pct
            FROM rated_team_rosters
            GROUP BY country_code, team_division
            ORDER BY country_code ASC, team_division ASC
        """,
        required_params=("generation_run_id",),
        tags=("export", "candidates"),
    ),
    RealismAuditQuery(
        name="division_balance",
        scope="generation_run",
        category="export_readiness",
        pillar=EXPORT_READINESS_PILLAR.key,
        description="Active competitive-team balance by country and doubles division.",
        sql="""
            WITH active_divisions AS (
                SELECT
                    t.country_code,
                    t.team_division,
                    COUNT(*) AS team_count
                FROM teams t
                WHERE t.generation_run_id = :generation_run_id
                    AND t.team_type = 'competitive'
                    AND t.team_status = 'active'
                GROUP BY t.country_code, t.team_division
            ),
            country_totals AS (
                SELECT
                    country_code,
                    SUM(team_count) AS total_team_count
                FROM active_divisions
                GROUP BY country_code
            )
            SELECT
                d.country_code,
                d.team_division,
                d.team_count,
                ROUND(
                    100.0 * d.team_count / NULLIF(ct.total_team_count, 0),
                    2
                ) AS team_pct_within_country
            FROM active_divisions d
            JOIN country_totals ct
                ON ct.country_code = d.country_code
            ORDER BY d.country_code ASC, d.team_division ASC
        """,
        required_params=("generation_run_id",),
        tags=("export", "divisions"),
    ),
    RealismAuditQuery(
        name="historical_run_size_regression",
        scope="generation_run",
        category="historical_regression",
        pillar=HISTORICAL_REGRESSION_PILLAR.key,
        description="Cross-run player, team, and match counts with simple growth rates versus the prior run.",
        sql="""
            WITH player_counts AS (
                SELECT
                    p.generation_run_id,
                    COUNT(*) AS player_count
                FROM players p
                GROUP BY p.generation_run_id
            ),
            team_counts AS (
                SELECT
                    t.generation_run_id,
                    COUNT(*) AS team_count
                FROM teams t
                GROUP BY t.generation_run_id
            ),
            match_counts AS (
                SELECT
                    mb.generation_run_id,
                    COUNT(*) AS match_count
                FROM monthly_batches mb
                JOIN matches m
                    ON m.batch_id = mb.id
                GROUP BY mb.generation_run_id
            ),
            run_sizes AS (
                SELECT
                    gr.id AS generation_run_id,
                    gr.generation_name,
                    COALESCE(pc.player_count, 0) AS player_count,
                    COALESCE(tc.team_count, 0) AS team_count,
                    COALESCE(mc.match_count, 0) AS match_count
                FROM generation_runs gr
                LEFT JOIN player_counts pc
                    ON pc.generation_run_id = gr.id
                LEFT JOIN team_counts tc
                    ON tc.generation_run_id = gr.id
                LEFT JOIN match_counts mc
                    ON mc.generation_run_id = gr.id
            ),
            ranked AS (
                SELECT
                    generation_run_id,
                    generation_name,
                    player_count,
                    team_count,
                    match_count,
                    LAG(player_count) OVER (ORDER BY generation_run_id) AS prior_player_count,
                    LAG(team_count) OVER (ORDER BY generation_run_id) AS prior_team_count,
                    LAG(match_count) OVER (ORDER BY generation_run_id) AS prior_match_count
                FROM run_sizes
            )
            SELECT
                generation_run_id,
                generation_name,
                player_count,
                team_count,
                match_count,
                ROUND(
                    100.0 * (player_count - prior_player_count) / NULLIF(prior_player_count, 0),
                    2
                ) AS player_growth_pct,
                ROUND(
                    100.0 * (team_count - prior_team_count) / NULLIF(prior_team_count, 0),
                    2
                ) AS team_growth_pct,
                ROUND(
                    100.0 * (match_count - prior_match_count) / NULLIF(prior_match_count, 0),
                    2
                ) AS match_growth_pct
            FROM ranked
            ORDER BY generation_run_id DESC
            LIMIT 10
        """,
        required_params=(),
        tags=("history", "regression"),
    ),
    RealismAuditQuery(
        name="historical_baseline_scale_regression",
        scope="generation_run",
        category="historical_regression",
        pillar=HISTORICAL_REGRESSION_PILLAR.key,
        description="Current run counts versus the latest successful baseline release and recent prior-run trend.",
        sql="""
            WITH player_counts AS (
                SELECT
                    p.generation_run_id,
                    COUNT(*) AS player_count
                FROM players p
                GROUP BY p.generation_run_id
            ),
            team_counts AS (
                SELECT
                    t.generation_run_id,
                    COUNT(*) AS team_count
                FROM teams t
                GROUP BY t.generation_run_id
            ),
            match_counts AS (
                SELECT
                    mb.generation_run_id,
                    COUNT(*) AS match_count
                FROM monthly_batches mb
                JOIN matches m
                    ON m.batch_id = mb.id
                GROUP BY mb.generation_run_id
            ),
            run_sizes AS (
                SELECT
                    gr.id AS generation_run_id,
                    gr.generation_name,
                    COALESCE(pc.player_count, 0) AS player_count,
                    COALESCE(tc.team_count, 0) AS team_count,
                    COALESCE(mc.match_count, 0) AS match_count
                FROM generation_runs gr
                LEFT JOIN player_counts pc
                    ON pc.generation_run_id = gr.id
                LEFT JOIN team_counts tc
                    ON tc.generation_run_id = gr.id
                LEFT JOIN match_counts mc
                    ON mc.generation_run_id = gr.id
            ),
            current_run AS (
                SELECT *
                FROM run_sizes
                WHERE generation_run_id = :generation_run_id
            ),
            baseline_release AS (
                SELECT
                    r.generation_run_id AS baseline_generation_run_id,
                    r.release_name AS baseline_release_name,
                    r.release_type AS baseline_release_type,
                    COALESCE(r.data_quality_level, 'none') AS baseline_data_quality_level,
                    r.completed_at
                FROM student_dataset_releases r
                WHERE r.status = 'succeeded'
                    AND r.generation_run_id <> :generation_run_id
                    AND r.release_type IN ('historical_baseline', 'initial_snapshot')
                ORDER BY
                    r.completed_at DESC,
                    r.generation_run_id DESC,
                    r.id DESC
                LIMIT 1
            ),
            baseline_run AS (
                SELECT
                    br.baseline_generation_run_id,
                    br.baseline_release_name,
                    br.baseline_release_type,
                    br.baseline_data_quality_level,
                    rs.player_count AS baseline_player_count,
                    rs.team_count AS baseline_team_count,
                    rs.match_count AS baseline_match_count
                FROM baseline_release br
                JOIN run_sizes rs
                    ON rs.generation_run_id = br.baseline_generation_run_id
            ),
            prior_runs AS (
                SELECT
                    generation_run_id,
                    player_count,
                    team_count,
                    match_count
                FROM run_sizes
                WHERE generation_run_id < :generation_run_id
                ORDER BY generation_run_id DESC
                LIMIT 3
            ),
            prior_summary AS (
                SELECT
                    COUNT(*) AS prior_run_count,
                    ROUND(AVG(player_count), 2) AS avg_prior_player_count,
                    ROUND(AVG(team_count), 2) AS avg_prior_team_count,
                    ROUND(AVG(match_count), 2) AS avg_prior_match_count
                FROM prior_runs
            )
            SELECT
                cr.generation_run_id,
                cr.generation_name,
                cr.player_count,
                cr.team_count,
                cr.match_count,
                br.baseline_generation_run_id,
                br.baseline_release_name,
                br.baseline_release_type,
                br.baseline_data_quality_level,
                br.baseline_player_count,
                br.baseline_team_count,
                br.baseline_match_count,
                ROUND(
                    100.0 * (cr.player_count - br.baseline_player_count)
                    / NULLIF(br.baseline_player_count, 0),
                    2
                ) AS player_delta_vs_baseline_pct,
                ROUND(
                    100.0 * (cr.team_count - br.baseline_team_count)
                    / NULLIF(br.baseline_team_count, 0),
                    2
                ) AS team_delta_vs_baseline_pct,
                ROUND(
                    100.0 * (cr.match_count - br.baseline_match_count)
                    / NULLIF(br.baseline_match_count, 0),
                    2
                ) AS match_delta_vs_baseline_pct,
                ps.prior_run_count,
                ps.avg_prior_player_count,
                ps.avg_prior_team_count,
                ps.avg_prior_match_count,
                ROUND(
                    100.0 * (cr.player_count - ps.avg_prior_player_count)
                    / NULLIF(ps.avg_prior_player_count, 0),
                    2
                ) AS player_delta_vs_trend_pct,
                ROUND(
                    100.0 * (cr.team_count - ps.avg_prior_team_count)
                    / NULLIF(ps.avg_prior_team_count, 0),
                    2
                ) AS team_delta_vs_trend_pct,
                ROUND(
                    100.0 * (cr.match_count - ps.avg_prior_match_count)
                    / NULLIF(ps.avg_prior_match_count, 0),
                    2
                ) AS match_delta_vs_trend_pct
            FROM current_run cr
            LEFT JOIN baseline_run br
                ON 1 = 1
            LEFT JOIN prior_summary ps
                ON 1 = 1
        """,
        required_params=("generation_run_id",),
        tags=("history", "baseline", "regression"),
    ),
    RealismAuditQuery(
        name="historical_release_file_coverage",
        scope="generation_run",
        category="historical_regression",
        pillar=HISTORICAL_REGRESSION_PILLAR.key,
        description="Historical student-release file coverage and row counts across prior releases.",
        sql="""
            SELECT
                r.generation_run_id,
                r.release_name,
                r.release_type,
                COALESCE(r.data_quality_level, 'none') AS data_quality_level,
                r.status,
                COUNT(f.id) AS file_count,
                COALESCE(SUM(f.row_count), 0) AS total_row_count
            FROM student_dataset_releases r
            LEFT JOIN student_dataset_release_files f
                ON f.release_id = r.id
            GROUP BY
                r.generation_run_id,
                r.release_name,
                r.release_type,
                COALESCE(r.data_quality_level, 'none'),
                r.status
            ORDER BY r.generation_run_id DESC, r.release_name ASC
        """,
        required_params=(),
        tags=("history", "releases"),
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
            sql_text = self._sql_for_query(
                query,
                dialect_name=dialect_name,
                sql_params=sql_params,
            )
            rows = tuple(
                dict(row)
                for row in self.session.execute(
                    text(sql_text),
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

    def _sql_for_query(
        self,
        query: RealismAuditQuery,
        *,
        dialect_name: str,
        sql_params: Mapping[str, Any],
    ) -> str:
        if query.name != "team_partner_continuity_by_batch":
            return query.sql_for_dialect(dialect_name)
        generation_run_id = sql_params.get("generation_run_id")
        if generation_run_id is None or self._has_team_roster_helper_rows(
            int(generation_run_id)
        ):
            return query.sql_for_dialect(dialect_name)
        return TEAM_PARTNER_CONTINUITY_BY_BATCH_LEGACY_SQL

    def _has_team_roster_helper_rows(self, generation_run_id: int) -> bool:
        bind = self.session.get_bind()
        if bind is None:
            return False
        if not inspect(bind).has_table(AuditBatchTeamRoster.__tablename__):
            return False
        count = self.session.scalar(
            select(AuditBatchTeamRoster.batch_id)
            .where(AuditBatchTeamRoster.generation_run_id == generation_run_id)
            .limit(1)
        )
        return count is not None

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

    hidden_bias_enabled = _payload_bool(
        payload,
        ("hidden_performance_bias", "enabled"),
        False,
    )
    fatigue_bias_enabled = hidden_bias_enabled and _payload_bool(
        payload,
        ("hidden_performance_bias", "fatigue", "enabled"),
        False,
    )
    regional_strength_bias_enabled = hidden_bias_enabled and _payload_bool(
        payload,
        ("hidden_performance_bias", "regional_strength", "enabled"),
        False,
    )
    partnership_affinity_bias_enabled = hidden_bias_enabled and _payload_bool(
        payload,
        ("hidden_performance_bias", "partnership_affinity", "enabled"),
        False,
    )
    age_advantage_bias_enabled = hidden_bias_enabled and _payload_bool(
        payload,
        ("hidden_performance_bias", "age_advantage", "enabled"),
        False,
    )
    experience_bias_enabled = hidden_bias_enabled and _payload_bool(
        payload,
        ("hidden_performance_bias", "experience", "enabled"),
        False,
    )

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
        "regional_strength_min_rated_players": _payload_int(
            payload,
            ("validation", "regional_strength_min_rated_players"),
            15,
        ),
        "hidden_bias_enabled": hidden_bias_enabled,
        "fatigue_bias_enabled": fatigue_bias_enabled,
        "regional_strength_bias_enabled": regional_strength_bias_enabled,
        "partnership_affinity_bias_enabled": partnership_affinity_bias_enabled,
        "age_advantage_bias_enabled": age_advantage_bias_enabled,
        "experience_bias_enabled": experience_bias_enabled,
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
