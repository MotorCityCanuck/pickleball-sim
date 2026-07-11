"""Tests for export-layer data quality injection rules."""

from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.exports.data_quality.config import (  # noqa: E402
    ISSUE_TYPE_MISSING_OPTIONAL_VALUES,
    ISSUE_TYPE_NAME_CASE_VARIANTS,
)
from app.exports.data_quality.injector import (  # noqa: E402
    DataQualityInjectionSummary,
    _InjectionState,
    _apply_table_rules,
)
from app.exports.data_quality.rules import eligible_columns  # noqa: E402
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
            "matches": [{} for _ in range(100)],
            "player_master": [{} for _ in range(100)],
        },
        config,
        summary,
    )

    failed_names = {check.name for check in checks if check.status != "passed"}
    assert failed_names == set()
