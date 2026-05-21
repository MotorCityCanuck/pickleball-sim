"""Reusable SQL-backed realism audit queries for generated data."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import json
from typing import Any, Literal, Mapping, Sequence

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.default_configuration import DEFAULT_CONFIG_PAYLOAD
from app.models import GenerationRun, MonthlyBatch


AuditScope = Literal["generation_run", "batch"]


@dataclass(frozen=True)
class RealismAuditQuery:
    """One named audit query with scope and parameter requirements."""

    name: str
    scope: AuditScope
    description: str
    sql: str | Mapping[str, str]
    required_params: tuple[str, ...]
    tags: tuple[str, ...] = ()

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


REALISM_AUDIT_QUERIES: tuple[RealismAuditQuery, ...] = (
    RealismAuditQuery(
        name="player_roster_summary",
        scope="generation_run",
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
        name="club_membership_geography",
        scope="generation_run",
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
                ) AS same_region_secondary_pct
            FROM memberships
        """,
        required_params=("generation_run_id",),
        tags=("clubs", "geography"),
    ),
    RealismAuditQuery(
        name="match_type_distribution",
        scope="batch",
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
    ),
    RealismAuditQuery(
        name="weekend_match_share",
        scope="batch",
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
    ),
    RealismAuditQuery(
        name="game_competitiveness_summary",
        scope="batch",
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
        name="rating_delta_summary",
        scope="batch",
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
        generation_run_id: int | None = None,
        batch_id: int | None = None,
    ) -> tuple[RealismAuditResult, ...]:
        """Run one or more realism audit queries and return row mappings."""
        selected_queries = self._select_queries(query_names)
        params = resolve_realism_audit_parameters(
            self.session,
            generation_run_id=generation_run_id,
            batch_id=batch_id,
        )
        if generation_run_id is not None:
            params["generation_run_id"] = generation_run_id
        if batch_id is not None:
            params["batch_id"] = batch_id

        results: list[RealismAuditResult] = []
        dialect_name = self.session.bind.dialect.name if self.session.bind is not None else "default"
        sql_params = {
            key: float(value) if isinstance(value, Decimal) else value
            for key, value in params.items()
        }
        for query in selected_queries:
            missing = [name for name in query.required_params if sql_params.get(name) is None]
            if missing:
                raise ValueError(
                    f"Audit query {query.name!r} requires parameters: {', '.join(missing)}."
                )
            rows = tuple(
                dict(row)
                for row in self.session.execute(
                    text(query.sql_for_dialect(dialect_name)),
                    sql_params,
                ).mappings()
            )
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
                raise ValueError(f"Unknown audit query {name!r}. Available queries: {available}.")
            selected.append(query)
        return tuple(selected)


def resolve_realism_audit_parameters(
    session: Session,
    *,
    generation_run_id: int | None = None,
    batch_id: int | None = None,
) -> dict[str, Any]:
    """Resolve audit thresholds from defaults and the run snapshot when available."""
    resolved_generation_run_id = generation_run_id
    if resolved_generation_run_id is None and batch_id is not None:
        resolved_generation_run_id = session.scalar(
            select(MonthlyBatch.generation_run_id).where(MonthlyBatch.id == batch_id)
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
        "batch_id": batch_id,
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
