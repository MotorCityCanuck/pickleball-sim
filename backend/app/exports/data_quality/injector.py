"""Deterministic export-layer data quality injection."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping
import copy
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
) -> DataQualityInjectionResult:
    """Inject bounded, deterministic quality issues into exported table rows."""

    requested_level = normalize_data_quality_level(config.level)
    effective_level = config.effective_level_for_release(release_context.release_type)
    original_tables = {
        table_name: [copy.deepcopy(row) for row in rows]
        for table_name, rows in tables.items()
    }
    injected_tables = {
        table_name: [copy.deepcopy(row) for row in rows]
        for table_name, rows in tables.items()
    }
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
            table_row_deltas={table_name: 0 for table_name in tables},
        )
        validation_result = validate_injected_tables(
            original_tables=original_tables,
            injected_tables=injected_tables,
            config=config,
            summary=summary,
        )
        return DataQualityInjectionResult(
            tables=injected_tables,
            manifest_entries=(),
            summary=summary,
            validation_result=validation_result,
        )

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
        issue_type_field_count=defaultdict(int),
        table_row_deltas=defaultdict(int),
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
        table_row_deltas=dict(state.table_row_deltas),
    )
    validation_result = validate_injected_tables(
        original_tables=original_tables,
        injected_tables=injected_tables,
        config=config,
        summary=summary,
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
    issue_type_field_count: dict[str, int]
    table_row_deltas: dict[str, int]


def _apply_table_rules(state: _InjectionState, table_name: str) -> None:
    rule = state.config.table_rules.get(table_name)
    if rule is None or not rule.enabled:
        return

    profile = level_profile(rule.issue_profile or state.effective_level)
    for issue_type in rule.allowed_issue_types:
        if issue_type not in SUPPORTED_ISSUE_TYPES or issue_type in ROW_RATE_ISSUES:
            continue
        rows = state.tables[table_name]
        columns = eligible_columns(table_name, issue_type)
        if not rows or not columns:
            state.issue_type_candidate_rows.setdefault(issue_type, 0)
            continue
        state.issue_type_candidate_rows.setdefault(issue_type, len(rows))
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
        candidates = [
            (row_index, column_name)
            for row_index, row in enumerate(rows)
            for column_name in columns
            if row.get(column_name) is not None
        ]
        rng.shuffle(candidates)
        applied = 0
        for row_index, column_name in candidates:
            if applied >= target_count:
                break
            row = rows[row_index]
            pk_value = row[primary_key_column(table_name)]
            row_key = (table_name, pk_value)
            if state.row_field_counts[row_key] >= state.config.global_limits.max_affected_fields_per_row:
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
                continue
            row[column_name] = injected_value
            state.row_field_counts[row_key] += 1
            state.affected_rows.add(row_key)
            state.issue_type_rows[issue_type].add(row_key)
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


def _apply_duplicate_like_rows(state: _InjectionState) -> None:
    matches_rule = state.config.table_rules.get("matches")
    if matches_rule is None or ISSUE_TYPE_DUPLICATE_LIKE_ROWS not in matches_rule.allowed_issue_types:
        state.issue_type_candidate_rows.setdefault(
            ISSUE_TYPE_DUPLICATE_LIKE_ROWS,
            len(state.tables.get("matches", ())),
        )
        return
    matches = state.tables.get("matches", [])
    if not matches:
        state.issue_type_candidate_rows.setdefault(ISSUE_TYPE_DUPLICATE_LIKE_ROWS, 0)
        return

    profile = level_profile(matches_rule.issue_profile or state.effective_level)
    state.issue_type_candidate_rows.setdefault(ISSUE_TYPE_DUPLICATE_LIKE_ROWS, len(matches))
    target_count = _target_count(
        issue_type=ISSUE_TYPE_DUPLICATE_LIKE_ROWS,
        row_count=len(matches),
        profile=profile,
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
    match_rows = list(matches)
    rng.shuffle(match_rows)

    match_teams = state.tables["match_teams"]
    match_team_players = state.tables["match_team_players"]
    match_games = state.tables["match_games"]
    next_match_id = next_primary_key(matches, "matches")
    next_match_team_id = next_primary_key(match_teams, "match_teams")
    next_match_team_player_id = next_primary_key(match_team_players, "match_team_players")
    next_match_game_id = next_primary_key(match_games, "match_games")

    applied = 0
    for source_match in match_rows:
        if applied >= target_count:
            break
        source_match_id = source_match["id"]
        source_match_teams = [
            row for row in match_teams if row["match_id"] == source_match_id
        ]
        if len(source_match_teams) != 2:
            continue
        source_match_team_ids = {row["id"] for row in source_match_teams}
        source_players = [
            row for row in match_team_players if row["match_team_id"] in source_match_team_ids
        ]
        source_games = [
            row for row in match_games if row["match_id"] == source_match_id
        ]

        team_id_map: dict[int, int] = {}
        new_match = copy.deepcopy(source_match)
        new_match["id"] = next_match_id
        next_match_id += 1

        new_match_teams: list[dict[str, Any]] = []
        for team_row in source_match_teams:
            cloned_team = copy.deepcopy(team_row)
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
            cloned_player = copy.deepcopy(player_row)
            cloned_player["id"] = next_match_team_player_id
            next_match_team_player_id += 1
            cloned_player["match_team_id"] = team_id_map[int(player_row["match_team_id"])]
            new_match_team_players.append(cloned_player)

        new_match_games: list[dict[str, Any]] = []
        for game_row in source_games:
            cloned_game = copy.deepcopy(game_row)
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
