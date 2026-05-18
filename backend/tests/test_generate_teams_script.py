"""Tests for the team generation CLI helpers."""
from datetime import date
from pathlib import Path
import sys

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

SCRIPTS_DIR = BACKEND_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from app.generators import TeamGenerationResult  # noqa: E402
from generate_teams import _parse_args, _positive_int, print_generation_result  # noqa: E402


def test_positive_int_accepts_positive_values():
    assert _positive_int("12") == 12


def test_positive_int_rejects_zero():
    with pytest.raises(Exception, match="at least 1"):
        _positive_int("0")


def test_parse_args_accepts_required_cli_options():
    args = _parse_args(["--generation-run-id", "7", "--batch-id", "11"])

    assert args.generation_run_id == 7
    assert args.batch_id == 11


def test_print_generation_result_outputs_summary(capsys):
    print_generation_result(
        TeamGenerationResult(
            generation_run_id=7,
            batch_id=11,
            batch_month=date(2024, 1, 1),
            eligible_player_count=100,
            target_team_count=35,
            rows_loaded=35,
            membership_rows_loaded=70,
            leftover_player_count=30,
        )
    )

    output = capsys.readouterr().out
    assert "generation_run_id=7" in output
    assert "batch_id=11" in output
    assert "eligible_player_count=100" in output
    assert "rows_loaded=35" in output
    assert "membership_rows_loaded=70" in output
