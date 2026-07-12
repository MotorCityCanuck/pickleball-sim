"""Deterministic export-layer data quality injection."""

from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
import logging
from time import perf_counter
from typing import Any, Callable, Iterator, Mapping
import math
import random

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
    SUPPORTED_ISSUE_TYPES,
    DataQualityInjectionConfig,
    level_profile,
    normalize_data_quality_level,
)
from .manifests import DataQualityInjectionManifestEntry
from .rules import (
    CATEGORICAL_RATE_ISSUES,
    FIELD_RATE_ISSUES,
    ROW_RATE_ISSUES,
    categorical_variant,
    delayed_rating_update,
    eligible_columns,
    formatting_variant,
    name_case_variant,
    next_primary_key,
    numeric_outlier,
    primary_key_column,
    rounding_variant,
    timestamp_jitter,
)
from .validators import DataQualityInjectionValidationResult, validate_injected_tables


logger = logging.getLogger("uvicorn.error")
InjectionInstrumentationCallback = Callable[[str, Mapping[str, Any]], None]
_CANDIDATE_SAMPLE_MULTIPLIER = 4
_CANDIDATE_SAMPLE_MIN_EXTRA = 1024
_DUPLICATE_LIKE_SAMPLE_MULTIPLIER = 8
_DUPLICATE_LIKE_SAMPLE_MIN_EXTRA = 4096


@dataclass(frozen=True)
class DataQualityReleaseContext:
    """Release metadata used to drive deterministic injection."""

    release_id: str
    release_name: str
    release_type: str
    generation_run_id: int
    snapshot_month: date


@dataclass(frozen=True)
class DataQualityInjectionSummary:
    """High-level injection counts for one release."""

    release_name: str
    requested_level: str
    effective_level: str
    total_affected_rows: int
    total_affected_fields: int
    issue_type_affected_rows: Mapping[str, int]
    issue_type_candidate_rows: Mapping[str, int]
    table_issue_type_affected_rows: Mapping[str, Mapping[str, int]]
    table_issue_type_candidate_rows: Mapping[str, Mapping[str, int]]
    table_row_deltas: Mapping[str, int]


@dataclass(frozen=True)
class DataQualityInjectionResult:
    """Complete export-layer mutation result."""

    tables: Mapping[str, list[dict[str, Any]]]
    manifest_entries: tuple[DataQualityInjectionManifestEntry, ...]
    summary: DataQualityInjectionSummary
    validation_result: DataQualityInjectionValidationResult


def inject_data_quality_issues(
    *,
    tables: Mapping[str, list[dict[str, Any]]],
    config: DataQualityInjectionConfig,
    release_context: DataQualityReleaseContext,
    instrumentation_callback: InjectionInstrumentationCallback | None = None,
    copy_tables: bool = True,
) -> DataQualityInjectionResult:
    """Inject bounded, deterministic quality issues into exported table rows."""

    requested_level = normalize_data_quality_level(config.level)
    effective_level = config.effective_level_for_release(release_context.release_type)
    if (
        not config.enabled
        or effective_level == "none"
        or not config.applies_to_release_type(release_context.release_type)
    ):
        summary = DataQualityInjectionSummary(
            release_name=release_context.release_name,
            requested_level=requested_level,
            effective_level=effective_level,
            total_affected_rows=0,
            total_affected_fields=0,
            issue_type_affected_rows={},
            issue_type_candidate_rows={},
            table_issue_type_affected_rows={},
            table_issue_type_candidate_rows={},
            table_row_deltas={table_name: 0 for table_name in tables},
        )
        return DataQualityInjectionResult(
            tables=tables,
            manifest_entries=(),
            summary=summary,
            validation_result=DataQualityInjectionValidationResult(
                status="passed",
                checks=(),
            ),
        )
    with _measure_injection_phase(
        instrumentation_callback,
        "capture_original_table_stats",
        table_count=len(tables),
        input_count=_total_row_count(tables),
    ) as metric:
        original_table_row_counts = {
            table_name: len(rows)
            for table_name, rows in tables.items()
        }
        metric["output_count"] = sum(original_table_row_counts.values())
    with _measure_injection_phase(
        instrumentation_callback,
        "copy_injected_tables" if copy_tables else "prepare_injected_tables",
        table_count=len(tables),
        input_count=_total_row_count(tables),
    ) as metric:
        if copy_tables:
            injected_tables = {
                table_name: [dict(row) for row in rows]
                for table_name, rows in tables.items()
            }
            metric["copy_mode"] = "copy"
        else:
            injected_tables = dict(tables)
            metric["copy_mode"] = "in_place"
        metric["output_count"] = _total_row_count(injected_tables)

    state = _InjectionState(
        config=config,
        release_context=release_context,
        effective_level=effective_level,
        tables=injected_tables,
        manifest_entries=[],
        row_field_counts=defaultdict(int),
        affected_rows=set(),
        issue_type_rows=defaultdict(set),
        issue_type_candidate_rows={},
        table_issue_type_rows=defaultdict(set),
        table_issue_type_candidate_rows={},
        issue_type_field_count=defaultdict(int),
        table_row_deltas=defaultdict(int),
        instrumentation_callback=instrumentation_callback,
    )
    logger.info(
        "Student dataset data quality injection start release_name=%s release_type=%s effective_level=%s table_count=%s",
        release_context.release_name,
        release_context.release_type,
        effective_level,
        len(injected_tables),
    )
    for table_name in injected_tables:
        _apply_table_rules(state, table_name)
    _apply_duplicate_like_rows(state)

    summary = DataQualityInjectionSummary(
        release_name=release_context.release_name,
        requested_level=requested_level,
        effective_level=effective_level,
        total_affected_rows=len(state.affected_rows),
        total_affected_fields=sum(state.issue_type_field_count.values()),
        issue_type_affected_rows={
            issue_type: len(keys)
            for issue_type, keys in state.issue_type_rows.items()
        },
        issue_type_candidate_rows=dict(state.issue_type_candidate_rows),
        table_issue_type_affected_rows=_nested_issue_counts(state.table_issue_type_rows),
        table_issue_type_candidate_rows=_nested_issue_totals(
            state.table_issue_type_candidate_rows
        ),
        table_row_deltas=dict(state.table_row_deltas),
    )
    with _measure_injection_phase(
        instrumentation_callback,
        "validate_injected_tables",
        table_count=len(injected_tables),
        input_count=_total_row_count(injected_tables),
    ):
        validation_result = validate_injected_tables(
            original_table_row_counts=original_table_row_counts,
            injected_tables=injected_tables,
            config=config,
            summary=summary,
            manifest_entries=state.manifest_entries,
        )
    return DataQualityInjectionResult(
        tables=injected_tables,
        manifest_entries=tuple(state.manifest_entries),
        summary=summary,
        validation_result=validation_result,
    )


@dataclass
class _InjectionState:
    config: DataQualityInjectionConfig
    release_context: DataQualityReleaseContext
    effective_level: str
    tables: dict[str, list[dict[str, Any]]]
    manifest_entries: list[DataQualityInjectionManifestEntry]
    row_field_counts: dict[tuple[str, object], int]
    affected_rows: set[tuple[str, object]]
    issue_type_rows: dict[str, set[tuple[str, object]]]
    issue_type_candidate_rows: dict[str, int]
    table_issue_type_rows: dict[tuple[str, str], set[tuple[str, object]]]
    table_issue_type_candidate_rows: dict[tuple[str, str], int]
    issue_type_field_count: dict[str, int]
    table_row_deltas: dict[str, int]
    instrumentation_callback: InjectionInstrumentationCallback | None = None


def _apply_table_rules(state: _InjectionState, table_name: str) -> None:
    rule = state.config.table_rules.get(table_name)
    if rule is None or not rule.enabled:
        return

    profile = level_profile(rule.issue_profile or state.effective_level)
    rows = state.tables[table_name]
    for issue_type in rule.allowed_issue_types:
        if issue_type not in SUPPORTED_ISSUE_TYPES or issue_type in ROW_RATE_ISSUES:
            continue
        columns = eligible_columns(table_name, issue_type)
        if not rows or not columns:
            state.issue_type_candidate_rows.setdefault(issue_type, 0)
            state.table_issue_type_candidate_rows.setdefault((table_name, issue_type), 0)
            logger.info(
                "Student dataset data quality issue_skipped table_name=%s issue_type=%s row_count=%s candidate_count=%s target_count=%s reason=%s",
                table_name,
                issue_type,
                len(rows),
                0,
                0,
                "no_rows_or_columns",
            )
            continue
        state.issue_type_candidate_rows[issue_type] = (
            state.issue_type_candidate_rows.get(issue_type, 0) + len(rows)
        )
        state.table_issue_type_candidate_rows[(table_name, issue_type)] = (
            state.table_issue_type_candidate_rows.get((table_name, issue_type), 0)
            + len(rows)
        )
        target_count = _target_count(
            issue_type=issue_type,
            row_count=len(rows),
            profile=profile,
        )
        if target_count <= 0:
            continue
        rng = random.Random(
            state.config.seed_for(
                state.release_context.release_id,
                table_name,
                issue_type,
            )
        )
        with _measure_injection_phase(
            state.instrumentation_callback,
            "issue_candidate_build",
            table_name=table_name,
            issue_type=issue_type,
            row_count=len(rows),
            target_count=target_count,
        ) as metric:
            candidate_count = _count_candidate_locations(rows, columns)
            metric["output_count"] = candidate_count
            metric["candidate_count"] = candidate_count
        if candidate_count <= 0:
            logger.info(
                "Student dataset data quality issue_skipped table_name=%s issue_type=%s row_count=%s candidate_count=%s target_count=%s reason=%s",
                table_name,
                issue_type,
                len(rows),
                0,
                target_count,
                "no_candidate_values",
            )
            continue
        logger.info(
            "Student dataset data quality issue_start table_name=%s issue_type=%s row_count=%s candidate_count=%s target_count=%s",
            table_name,
            issue_type,
            len(rows),
            candidate_count,
            target_count,
        )
        with _measure_injection_phase(
            state.instrumentation_callback,
            "issue_candidate_shuffle",
            table_name=table_name,
            issue_type=issue_type,
            input_count=candidate_count,
            target_count=target_count,
        ) as metric:
            sample_limit = _candidate_sample_limit(
                candidate_count=candidate_count,
                target_count=target_count,
            )
            candidates = _sample_candidate_locations(
                rows=rows,
                columns=columns,
                candidate_count=candidate_count,
                sample_limit=sample_limit,
                rng=rng,
            )
            rng.shuffle(candidates)
            metric["output_count"] = len(candidates)
            metric["candidate_count"] = candidate_count
            metric["sampled_count"] = len(candidates)
            metric["selection_strategy"] = "deterministic_bounded_sample"
        applied = 0
        with _measure_injection_phase(
            state.instrumentation_callback,
            "issue_apply",
            table_name=table_name,
            issue_type=issue_type,
            input_count=len(candidates),
            target_count=target_count,
        ) as metric:
            metric["candidate_count"] = candidate_count
            metric["sampled_count"] = len(candidates)
            noop_count = 0
            skipped_row_limit_count = 0
            for row_index, column_name in candidates:
                if applied >= target_count:
                    break
                row = rows[row_index]
                pk_value = row[primary_key_column(table_name)]
                row_key = (table_name, pk_value)
                if state.row_field_counts[row_key] >= state.config.global_limits.max_affected_fields_per_row:
                    skipped_row_limit_count += 1
                    continue
                original_value = row.get(column_name)
                injected_value = _mutated_value(
                    issue_type=issue_type,
                    table_name=table_name,
                    column_name=column_name,
                    row=row,
                    original_value=original_value,
                    rng=rng,
                )
                if injected_value == original_value:
                    noop_count += 1
                    continue
                row[column_name] = injected_value
                state.row_field_counts[row_key] += 1
                state.affected_rows.add(row_key)
                state.issue_type_rows[issue_type].add(row_key)
                state.table_issue_type_rows[(table_name, issue_type)].add(row_key)
                state.issue_type_field_count[issue_type] += 1
                state.manifest_entries.append(
                    DataQualityInjectionManifestEntry.create(
                        release_id=state.release_context.release_id,
                        release_name=state.release_context.release_name,
                        table_name=table_name,
                        record_primary_key=pk_value,
                        column_name=column_name,
                        issue_type=issue_type,
                        original_value=original_value,
                        injected_value=injected_value,
                        injection_level=state.effective_level,
                        random_seed=state.config.random_seed,
                        rule_id=f"{table_name}.{issue_type}",
                    )
                )
                applied += 1
            metric["output_count"] = applied
            metric["applied_count"] = applied
            metric["noop_count"] = noop_count
            metric["skipped_row_limit_count"] = skipped_row_limit_count
            metric["candidate_count"] = candidate_count
            metric["sampled_count"] = len(candidates)
        logger.info(
            "Student dataset data quality issue_end table_name=%s issue_type=%s row_count=%s candidate_count=%s target_count=%s applied_count=%s",
            table_name,
            issue_type,
            len(rows),
            candidate_count,
            target_count,
            applied,
        )


def _apply_duplicate_like_rows(state: _InjectionState) -> None:
    matches_rule = state.config.table_rules.get("matches")
    if matches_rule is None or ISSUE_TYPE_DUPLICATE_LIKE_ROWS not in matches_rule.allowed_issue_types:
        state.issue_type_candidate_rows.setdefault(
            ISSUE_TYPE_DUPLICATE_LIKE_ROWS,
            len(state.tables.get("matches", ())),
        )
        state.table_issue_type_candidate_rows.setdefault(
            ("matches", ISSUE_TYPE_DUPLICATE_LIKE_ROWS),
            len(state.tables.get("matches", ())),
        )
        return
    matches = state.tables.get("matches", [])
    if not matches:
        state.issue_type_candidate_rows.setdefault(ISSUE_TYPE_DUPLICATE_LIKE_ROWS, 0)
        state.table_issue_type_candidate_rows.setdefault(
            ("matches", ISSUE_TYPE_DUPLICATE_LIKE_ROWS),
            0,
        )
        return

    profile = level_profile(matches_rule.issue_profile or state.effective_level)
    state.issue_type_candidate_rows.setdefault(ISSUE_TYPE_DUPLICATE_LIKE_ROWS, len(matches))
    state.table_issue_type_candidate_rows.setdefault(
        ("matches", ISSUE_TYPE_DUPLICATE_LIKE_ROWS),
        len(matches),
    )
    target_count = _target_count(
        issue_type=ISSUE_TYPE_DUPLICATE_LIKE_ROWS,
        row_count=len(matches),
        profile=profile,
    )
    logger.info(
        "Student dataset data quality duplicate_like_rows_plan match_row_count=%s target_count=%s",
        len(matches),
        target_count,
    )
    if target_count <= 0:
        return

    rng = random.Random(
        state.config.seed_for(
            state.release_context.release_id,
            "matches",
            ISSUE_TYPE_DUPLICATE_LIKE_ROWS,
        )
    )
    with _measure_injection_phase(
        state.instrumentation_callback,
        "duplicate_like_match_copy_shuffle",
        table_name="matches",
        issue_type=ISSUE_TYPE_DUPLICATE_LIKE_ROWS,
        input_count=len(matches),
        target_count=target_count,
    ) as metric:
        source_match_sample_limit = _candidate_sample_limit(
            candidate_count=len(matches),
            target_count=target_count,
            multiplier=_DUPLICATE_LIKE_SAMPLE_MULTIPLIER,
            min_extra=_DUPLICATE_LIKE_SAMPLE_MIN_EXTRA,
        )
        match_rows = _sample_rows(
            rows=matches,
            sample_limit=source_match_sample_limit,
            rng=rng,
        )
        rng.shuffle(match_rows)
        metric["output_count"] = len(match_rows)
        metric["candidate_count"] = len(matches)
        metric["sampled_count"] = len(match_rows)
        metric["selection_strategy"] = "deterministic_bounded_sample"

    match_teams = state.tables["match_teams"]
    match_team_players = state.tables["match_team_players"]
    match_games = state.tables["match_games"]
    source_match_ids = {row["id"] for row in match_rows}
    with _measure_injection_phase(
        state.instrumentation_callback,
        "duplicate_like_lookup_build",
        table_name="matches",
        issue_type=ISSUE_TYPE_DUPLICATE_LIKE_ROWS,
        input_count=len(match_teams) + len(match_team_players) + len(match_games),
        target_count=target_count,
    ) as metric:
        match_teams_by_match_id: dict[object, list[dict[str, Any]]] = defaultdict(list)
        for row in match_teams:
            if row["match_id"] in source_match_ids:
                match_teams_by_match_id[row["match_id"]].append(row)
        source_match_team_ids = {
            row["id"]
            for rows_for_match in match_teams_by_match_id.values()
            for row in rows_for_match
        }
        players_by_match_team_id: dict[object, list[dict[str, Any]]] = defaultdict(list)
        for row in match_team_players:
            if row["match_team_id"] in source_match_team_ids:
                players_by_match_team_id[row["match_team_id"]].append(row)
        games_by_match_id: dict[object, list[dict[str, Any]]] = defaultdict(list)
        for row in match_games:
            if row["match_id"] in source_match_ids:
                games_by_match_id[row["match_id"]].append(row)
        metric["output_count"] = (
            sum(len(rows_for_match) for rows_for_match in match_teams_by_match_id.values())
            + sum(len(rows_for_team) for rows_for_team in players_by_match_team_id.values())
            + sum(len(rows_for_match) for rows_for_match in games_by_match_id.values())
        )
        metric["source_match_count"] = len(source_match_ids)
        metric["source_match_team_count"] = len(source_match_team_ids)
    next_match_id = next_primary_key(matches, "matches")
    next_match_team_id = next_primary_key(match_teams, "match_teams")
    next_match_team_player_id = next_primary_key(match_team_players, "match_team_players")
    next_match_game_id = next_primary_key(match_games, "match_games")

    applied = 0
    with _measure_injection_phase(
        state.instrumentation_callback,
        "duplicate_like_apply",
        table_name="matches",
        issue_type=ISSUE_TYPE_DUPLICATE_LIKE_ROWS,
        input_count=len(match_rows),
        target_count=target_count,
    ) as metric:
        for source_match in match_rows:
            if applied >= target_count:
                break
            source_match_id = source_match["id"]
            source_match_teams = match_teams_by_match_id.get(source_match_id, [])
            if len(source_match_teams) != 2:
                continue
            source_players = [
                row
                for team_row in source_match_teams
                for row in players_by_match_team_id.get(team_row["id"], [])
            ]
            source_games = games_by_match_id.get(source_match_id, [])

            team_id_map: dict[int, int] = {}
            new_match = dict(source_match)
            new_match["id"] = next_match_id
            next_match_id += 1

            new_match_teams: list[dict[str, Any]] = []
            for team_row in source_match_teams:
                cloned_team = dict(team_row)
                source_team_id = int(team_row["id"])
                cloned_team["id"] = next_match_team_id
                team_id_map[source_team_id] = next_match_team_id
                next_match_team_id += 1
                cloned_team["match_id"] = new_match["id"]
                new_match_teams.append(cloned_team)
            winning_team_id = source_match.get("winning_team_id")
            if winning_team_id is not None:
                new_match["winning_team_id"] = team_id_map.get(int(winning_team_id))

            new_match_team_players: list[dict[str, Any]] = []
            for player_row in source_players:
                cloned_player = dict(player_row)
                cloned_player["id"] = next_match_team_player_id
                next_match_team_player_id += 1
                cloned_player["match_team_id"] = team_id_map[int(player_row["match_team_id"])]
                new_match_team_players.append(cloned_player)

            new_match_games: list[dict[str, Any]] = []
            for game_row in source_games:
                cloned_game = dict(game_row)
                cloned_game["id"] = next_match_game_id
                next_match_game_id += 1
                cloned_game["match_id"] = new_match["id"]
                new_match_games.append(cloned_game)

            matches.append(new_match)
            match_teams.extend(new_match_teams)
            match_team_players.extend(new_match_team_players)
            match_games.extend(new_match_games)

            state.table_row_deltas["matches"] += 1
            state.table_row_deltas["match_teams"] += len(new_match_teams)
            state.table_row_deltas["match_team_players"] += len(new_match_team_players)
            state.table_row_deltas["match_games"] += len(new_match_games)
            row_key = ("matches", source_match_id)
            state.affected_rows.add(row_key)
            state.issue_type_rows[ISSUE_TYPE_DUPLICATE_LIKE_ROWS].add(row_key)
            state.table_issue_type_rows[("matches", ISSUE_TYPE_DUPLICATE_LIKE_ROWS)].add(
                row_key
            )

            for table_name, original_pk, injected_pk in (
                ("matches", source_match_id, new_match["id"]),
                *(
                    ("match_teams", original_team["id"], cloned_team["id"])
                    for original_team, cloned_team in zip(source_match_teams, new_match_teams, strict=False)
                ),
                *(
                    ("match_team_players", original_player["id"], cloned_player["id"])
                    for original_player, cloned_player in zip(source_players, new_match_team_players, strict=False)
                ),
                *(
                    ("match_games", original_game["id"], cloned_game["id"])
                    for original_game, cloned_game in zip(source_games, new_match_games, strict=False)
                ),
            ):
                state.manifest_entries.append(
                    DataQualityInjectionManifestEntry.create(
                        release_id=state.release_context.release_id,
                        release_name=state.release_context.release_name,
                        table_name=table_name,
                        record_primary_key=injected_pk,
                        column_name="__row__",
                        issue_type=ISSUE_TYPE_DUPLICATE_LIKE_ROWS,
                        original_value={"source_primary_key": original_pk},
                        injected_value={"duplicated_primary_key": injected_pk},
                        injection_level=state.effective_level,
                        random_seed=state.config.random_seed,
                        rule_id=f"{table_name}.{ISSUE_TYPE_DUPLICATE_LIKE_ROWS}",
                    )
            )
            applied += 1
        metric["output_count"] = applied
        metric["applied_count"] = applied
        metric["noop_count"] = 0
    logger.info(
        "Student dataset data quality duplicate_like_rows_end applied_count=%s match_row_delta=%s match_team_row_delta=%s match_team_player_row_delta=%s match_game_row_delta=%s",
        applied,
        state.table_row_deltas["matches"],
        state.table_row_deltas["match_teams"],
        state.table_row_deltas["match_team_players"],
        state.table_row_deltas["match_games"],
    )


def _mutated_value(
    *,
    issue_type: str,
    table_name: str,
    column_name: str,
    row: Mapping[str, Any],
    original_value: Any,
    rng: random.Random,
) -> Any:
    if issue_type == ISSUE_TYPE_MISSING_OPTIONAL_VALUES:
        return None
    if issue_type == ISSUE_TYPE_CATEGORICAL_VARIANTS:
        return categorical_variant(original_value, rng)
    if issue_type == ISSUE_TYPE_FORMATTING_VARIANTS:
        return formatting_variant(original_value, rng)
    if issue_type == ISSUE_TYPE_NAME_CASE_VARIANTS:
        return name_case_variant(original_value, rng)
    if issue_type == ISSUE_TYPE_SOFT_JOIN_AMBIGUITY:
        return formatting_variant(original_value, rng)
    if issue_type == ISSUE_TYPE_ROUNDING_VARIANTS:
        return rounding_variant(original_value, rng)
    if issue_type == ISSUE_TYPE_NUMERIC_OUTLIERS:
        return numeric_outlier(table_name, column_name, original_value, rng)
    if issue_type == ISSUE_TYPE_TIMESTAMP_JITTER:
        return timestamp_jitter(original_value, rng)
    if issue_type == ISSUE_TYPE_DELAYED_RATING_UPDATES:
        return delayed_rating_update(row).get(column_name, original_value)
    return original_value


def _target_count(*, issue_type: str, row_count: int, profile) -> int:
    if row_count <= 0:
        return 0
    if issue_type in FIELD_RATE_ISSUES:
        rate = profile.field_level_issue_rate.midpoint_ratio
    elif issue_type in CATEGORICAL_RATE_ISSUES:
        rate = profile.categorical_variant_rate.midpoint_ratio
    elif issue_type in ROW_RATE_ISSUES:
        rate = profile.duplicate_like_row_rate.midpoint_ratio
    else:
        rate = profile.field_level_issue_rate.midpoint_ratio
    if math.isclose(rate, 0.0):
        return 0
    return math.floor(row_count * rate)


def _nested_issue_counts(
    counts: Mapping[tuple[str, str], set[tuple[str, object]]],
) -> dict[str, dict[str, int]]:
    nested: dict[str, dict[str, int]] = {}
    for (table_name, issue_type), row_keys in counts.items():
        nested.setdefault(table_name, {})[issue_type] = len(row_keys)
    return nested


def _nested_issue_totals(
    totals: Mapping[tuple[str, str], int],
) -> dict[str, dict[str, int]]:
    nested: dict[str, dict[str, int]] = {}
    for (table_name, issue_type), candidate_total in totals.items():
        nested.setdefault(table_name, {})[issue_type] = candidate_total
    return nested


def _count_candidate_locations(
    rows: list[dict[str, Any]],
    columns: tuple[str, ...],
) -> int:
    return sum(
        1
        for row in rows
        for column_name in columns
        if row.get(column_name) is not None
    )


def _candidate_sample_limit(
    *,
    candidate_count: int,
    target_count: int,
    multiplier: int = _CANDIDATE_SAMPLE_MULTIPLIER,
    min_extra: int = _CANDIDATE_SAMPLE_MIN_EXTRA,
) -> int:
    if candidate_count <= 0 or target_count <= 0:
        return 0
    return min(
        candidate_count,
        max(
            target_count * multiplier,
            target_count + min_extra,
        ),
    )


def _sample_candidate_locations(
    *,
    rows: list[dict[str, Any]],
    columns: tuple[str, ...],
    candidate_count: int,
    sample_limit: int,
    rng: random.Random,
) -> list[tuple[int, str]]:
    selected_ordinals = _sample_candidate_ordinals(
        candidate_count=candidate_count,
        sample_limit=sample_limit,
        rng=rng,
    )
    if not selected_ordinals:
        return []

    candidates: list[tuple[int, str]] = []
    ordinal = 0
    for row_index, row in enumerate(rows):
        for column_name in columns:
            if row.get(column_name) is None:
                continue
            if ordinal in selected_ordinals:
                candidates.append((row_index, column_name))
                if len(candidates) >= sample_limit:
                    return candidates
            ordinal += 1
    return candidates


def _sample_rows(
    *,
    rows: list[dict[str, Any]],
    sample_limit: int,
    rng: random.Random,
) -> list[dict[str, Any]]:
    selected_ordinals = _sample_candidate_ordinals(
        candidate_count=len(rows),
        sample_limit=sample_limit,
        rng=rng,
    )
    if not selected_ordinals:
        return []
    return [
        row
        for row_index, row in enumerate(rows)
        if row_index in selected_ordinals
    ]


def _sample_candidate_ordinals(
    *,
    candidate_count: int,
    sample_limit: int,
    rng: random.Random,
) -> set[int]:
    if sample_limit <= 0 or candidate_count <= 0:
        return set()
    if sample_limit >= candidate_count:
        return set(range(candidate_count))

    selected: set[int] = set()
    for ordinal in range(candidate_count - sample_limit, candidate_count):
        replacement = rng.randrange(ordinal + 1)
        if replacement in selected:
            selected.add(ordinal)
        else:
            selected.add(replacement)
    return selected


@contextmanager
def _measure_injection_phase(
    callback: InjectionInstrumentationCallback | None,
    phase_name: str,
    **fields: Any,
) -> Iterator[dict[str, Any]]:
    metric = dict(fields)
    _emit_injection_event(callback, f"{phase_name}_start", phase_name=phase_name, **metric)
    started = perf_counter()
    try:
        yield metric
    except Exception as exc:
        elapsed_ms = int((perf_counter() - started) * 1000)
        _emit_injection_event(
            callback,
            f"{phase_name}_failed",
            phase_name=phase_name,
            elapsed_ms=max(elapsed_ms, 0),
            error=str(exc),
            **metric,
        )
        raise
    else:
        elapsed_ms = int((perf_counter() - started) * 1000)
        _emit_injection_event(
            callback,
            f"{phase_name}_end",
            phase_name=phase_name,
            elapsed_ms=max(elapsed_ms, 0),
            **metric,
        )


def _emit_injection_event(
    callback: InjectionInstrumentationCallback | None,
    event_name: str,
    **fields: Any,
) -> None:
    if callback is None:
        return
    callback(event_name, fields)


def _total_row_count(tables: Mapping[str, list[dict[str, Any]]]) -> int:
    return sum(len(rows) for rows in tables.values())
