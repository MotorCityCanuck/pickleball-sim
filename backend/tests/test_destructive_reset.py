"""Tests for generated-data reset strategies."""
from pathlib import Path
import sys

from sqlalchemy.dialects import postgresql


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.generation.destructive_reset import (  # noqa: E402
    DELETE_MODELS_IN_ORDER,
    ResetProgressEvent,
    TRUNCATE_MODELS,
    reset_progress_message,
    reset_progress_metadata,
    _truncate_statement,
)
from app.models import (  # noqa: E402
    BatchRun,
    ExportRun,
    JobStageProgress,
    Match,
    MatchTeam,
    MatchTeamPlayer,
    MonthlyBatch,
    RatingsUpdateLog,
    StudentDatasetRelease,
    ValidationResult,
)


def test_postgres_truncate_statement_targets_explicit_generated_domain():
    statement = _truncate_statement(TRUNCATE_MODELS, postgresql.dialect())

    assert statement.startswith("TRUNCATE TABLE ")
    assert statement.endswith(" RESTART IDENTITY")
    assert "ratings_update_log" in statement
    assert "match_team_players" in statement
    assert "match_teams" in statement
    assert "matches" in statement


def test_generated_reset_plan_keeps_history_tables_out_of_runtime_reset():
    reset_models = set(DELETE_MODELS_IN_ORDER)

    assert RatingsUpdateLog in reset_models
    assert MatchTeamPlayer in reset_models
    assert MatchTeam in reset_models
    assert Match in reset_models
    assert MonthlyBatch not in reset_models
    assert JobStageProgress not in reset_models
    assert BatchRun not in reset_models
    assert ValidationResult not in reset_models
    assert ExportRun not in reset_models
    assert StudentDatasetRelease not in reset_models


def test_reset_progress_message_and_metadata_identify_truncate_strategy():
    event = ResetProgressEvent(
        model_name="ratings_update_log",
        model_label="RatingsUpdateLog",
        step_index=1,
        total_steps=13,
        status="running",
        reset_strategy="truncate",
    )

    assert reset_progress_message(event) == "Truncating generated data tables (1/13)"
    assert reset_progress_metadata(event, progress_current=0) == {
        "current_model": "ratings_update_log",
        "completed_models": 0,
        "total_models": 13,
        "rows_affected": None,
        "reset_strategy": "truncate",
    }
