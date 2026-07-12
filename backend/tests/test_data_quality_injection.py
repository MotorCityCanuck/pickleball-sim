"""Tests for export-layer data quality injection rules."""

from collections import defaultdict
from decimal import Decimal
from pathlib import Path
import random
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.exports.data_quality.config import (  # noqa: E402
    ISSUE_TYPE_DUPLICATE_LIKE_ROWS,
    ISSUE_TYPE_MISSING_OPTIONAL_VALUES,
    ISSUE_TYPE_NAME_CASE_VARIANTS,
    ISSUE_TYPE_ROUNDING_VARIANTS,
)
from app.exports.data_quality.injector import (  # noqa: E402
    DataQualityInjectionSummary,
    _InjectionState,
    _apply_duplicate_like_rows,
    _apply_table_rules,
    _candidate_sample_limit,
    _sample_candidate_locations,
)
from app.exports.data_quality.rules import (  # noqa: E402
    eligible_columns,
    numeric_outlier,
    rounding_variant,
)
from app.exports.data_quality.validators import _validate_issue_rates  # noqa: E402
from app.exports.data_quality import build_default_data_quality_config  # noqa: E402


def test_missing_optional_values_do_not_target_required_match_format():
    columns = eligible_columns("matches", ISSUE_TYPE_MISSING_OPTIONAL_VALUES)

    assert "court_type" in columns
    assert "match_format" not in columns


def test_issue_type_candidate_rows_accumulate_across_tables():
    config = build_default_data_quality_config(level="medium")
    state = _InjectionState(
        config=config,
        release_context=type(
            "ReleaseContext",
            (),
            {
                "release_id": "release-1",
                "release_name": "release",
                "release_type": "initial_snapshot",
            },
        )(),
        effective_level="medium",
        tables={
            "clubs": [
                {
                    "id": 1,
                    "club_type": "public",
                    "competitiveness_level": "recreational",
                },
                {
                    "id": 2,
                    "club_type": "private",
                    "competitiveness_level": "competitive",
                },
            ],
            "matches": [
                {
                    "id": 10,
                    "court_type": "indoor",
                    "match_format": "single_game",
                    "match_type": "recreational",
                },
                {
                    "id": 11,
                    "court_type": "outdoor",
                    "match_format": "single_game",
                    "match_type": "league",
                },
                {
                    "id": 12,
                    "court_type": "indoor",
                    "match_format": "best_of_three",
                    "match_type": "tournament",
                },
            ],
        },
        manifest_entries=[],
        row_field_counts={},
        affected_rows=set(),
        issue_type_rows={},
        issue_type_candidate_rows={},
        table_issue_type_rows={},
        table_issue_type_candidate_rows={},
        issue_type_field_count={},
        table_row_deltas={},
    )

    _apply_table_rules(state, "clubs")
    _apply_table_rules(state, "matches")

    assert state.issue_type_candidate_rows[ISSUE_TYPE_MISSING_OPTIONAL_VALUES] == 5
    assert (
        state.table_issue_type_candidate_rows[("clubs", ISSUE_TYPE_MISSING_OPTIONAL_VALUES)]
        == 2
    )
    assert (
        state.table_issue_type_candidate_rows[("matches", ISSUE_TYPE_MISSING_OPTIONAL_VALUES)]
        == 3
    )


def test_decimal_numeric_transforms_produce_mutated_values():
    rounded = rounding_variant(Decimal("1500.12345"), random.Random(1))
    outlier = numeric_outlier(
        "match_games",
        "actual_team_one_score_share",
        Decimal("0.5000"),
        random.Random(1),
    )

    assert isinstance(rounded, Decimal)
    assert rounded != Decimal("1500.12345")
    assert isinstance(outlier, Decimal)
    assert outlier != Decimal("0.5000")


def test_candidate_sampling_bounds_materialized_candidates_deterministically():
    rows = [
        {
            "id": row_id,
            "player_rating_at_match": Decimal("1500.12345") + Decimal(row_id),
        }
        for row_id in range(1, 5001)
    ]
    candidate_count = len(rows)
    sample_limit = _candidate_sample_limit(
        candidate_count=candidate_count,
        target_count=10,
    )

    first_sample = _sample_candidate_locations(
        rows=rows,
        columns=("player_rating_at_match",),
        candidate_count=candidate_count,
        sample_limit=sample_limit,
        rng=random.Random(123),
    )
    second_sample = _sample_candidate_locations(
        rows=rows,
        columns=("player_rating_at_match",),
        candidate_count=candidate_count,
        sample_limit=sample_limit,
        rng=random.Random(123),
    )

    assert 10 < sample_limit < candidate_count
    assert len(first_sample) == sample_limit
    assert first_sample == second_sample
    assert len(set(first_sample)) == sample_limit


def test_issue_apply_instrumentation_reports_applied_and_noop_counts():
    config = build_default_data_quality_config(level="low")
    events = []
    state = _InjectionState(
        config=config,
        release_context=type(
            "ReleaseContext",
            (),
            {
                "release_id": "release-1",
                "release_name": "release",
                "release_type": "initial_snapshot",
            },
        )(),
        effective_level="low",
        tables={
            "match_team_players": [
                {
                    "id": row_id,
                    "player_rating_at_match": Decimal("1500.12345") + Decimal(row_id),
                }
                for row_id in range(1, 401)
            ],
        },
        manifest_entries=[],
        row_field_counts=defaultdict(int),
        affected_rows=set(),
        issue_type_rows=defaultdict(set),
        issue_type_candidate_rows={},
        table_issue_type_rows=defaultdict(set),
        table_issue_type_candidate_rows={},
        issue_type_field_count=defaultdict(int),
        table_row_deltas=defaultdict(int),
        instrumentation_callback=lambda event_name, fields: events.append(
            (event_name, dict(fields))
        ),
    )

    _apply_table_rules(state, "match_team_players")

    apply_events = [
        fields
        for event_name, fields in events
        if event_name == "issue_apply_end"
    ]
    assert len(apply_events) == 1
    apply_event = apply_events[0]
    assert apply_event["issue_type"] == ISSUE_TYPE_ROUNDING_VARIANTS
    assert apply_event["target_count"] == 1
    assert apply_event["applied_count"] == 1
    assert apply_event["output_count"] == 1
    assert apply_event["noop_count"] >= 0
    assert apply_event["skipped_row_limit_count"] >= 0


def test_duplicate_like_rows_uses_bounded_source_match_sample_and_lookup():
    config = build_default_data_quality_config(level="low")
    events = []
    match_count = 5000
    matches = [
        {
            "id": match_id,
            "winning_team_id": (match_id * 2) - 1,
        }
        for match_id in range(1, match_count + 1)
    ]
    match_teams = [
        {
            "id": team_id,
            "match_id": ((team_id - 1) // 2) + 1,
        }
        for team_id in range(1, (match_count * 2) + 1)
    ]
    match_team_players = [
        {
            "id": player_row_id,
            "match_team_id": ((player_row_id - 1) // 2) + 1,
        }
        for player_row_id in range(1, (match_count * 4) + 1)
    ]
    match_games = [
        {
            "id": game_id,
            "match_id": game_id,
        }
        for game_id in range(1, match_count + 1)
    ]
    state = _InjectionState(
        config=config,
        release_context=type(
            "ReleaseContext",
            (),
            {
                "release_id": "release-1",
                "release_name": "release",
                "release_type": "initial_snapshot",
            },
        )(),
        effective_level="low",
        tables={
            "matches": matches,
            "match_teams": match_teams,
            "match_team_players": match_team_players,
            "match_games": match_games,
        },
        manifest_entries=[],
        row_field_counts=defaultdict(int),
        affected_rows=set(),
        issue_type_rows=defaultdict(set),
        issue_type_candidate_rows={},
        table_issue_type_rows=defaultdict(set),
        table_issue_type_candidate_rows={},
        issue_type_field_count=defaultdict(int),
        table_row_deltas=defaultdict(int),
        instrumentation_callback=lambda event_name, fields: events.append(
            (event_name, dict(fields))
        ),
    )

    _apply_duplicate_like_rows(state)

    shuffle_event = next(
        fields
        for event_name, fields in events
        if event_name == "duplicate_like_match_copy_shuffle_end"
    )
    lookup_event = next(
        fields
        for event_name, fields in events
        if event_name == "duplicate_like_lookup_build_end"
    )
    apply_event = next(
        fields
        for event_name, fields in events
        if event_name == "duplicate_like_apply_end"
    )

    assert shuffle_event["issue_type"] == ISSUE_TYPE_DUPLICATE_LIKE_ROWS
    assert shuffle_event["candidate_count"] == match_count
    assert shuffle_event["sampled_count"] < match_count
    assert lookup_event["source_match_count"] == shuffle_event["sampled_count"]
    assert lookup_event["output_count"] < lookup_event["input_count"]
    assert apply_event["applied_count"] == apply_event["target_count"]
    assert state.table_row_deltas["matches"] == apply_event["target_count"]


def test_issue_rate_validation_uses_table_issue_profile_over_release_level():
    config = build_default_data_quality_config(level="medium")
    summary = DataQualityInjectionSummary(
        release_name="release",
        requested_level="medium",
        effective_level="low",
        total_affected_rows=2,
        total_affected_fields=2,
        issue_type_affected_rows={
            ISSUE_TYPE_MISSING_OPTIONAL_VALUES: 1,
            ISSUE_TYPE_NAME_CASE_VARIANTS: 1,
        },
        issue_type_candidate_rows={
            ISSUE_TYPE_MISSING_OPTIONAL_VALUES: 100,
            ISSUE_TYPE_NAME_CASE_VARIANTS: 100,
        },
        table_issue_type_affected_rows={
            "matches": {ISSUE_TYPE_MISSING_OPTIONAL_VALUES: 1},
            "player_master": {ISSUE_TYPE_NAME_CASE_VARIANTS: 1},
        },
        table_issue_type_candidate_rows={
            "matches": {ISSUE_TYPE_MISSING_OPTIONAL_VALUES: 100},
            "player_master": {ISSUE_TYPE_NAME_CASE_VARIANTS: 100},
        },
        table_row_deltas={},
    )

    checks = _validate_issue_rates(
        {
            "matches": 100,
            "player_master": 100,
        },
        config,
        summary,
    )

    failed_names = {check.name for check in checks if check.status != "passed"}
    assert failed_names == set()
