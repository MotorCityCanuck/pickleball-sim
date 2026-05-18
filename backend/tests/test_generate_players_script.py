"""Tests for the player generation CLI helpers."""
from pathlib import Path
import sys

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

SCRIPTS_DIR = BACKEND_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from app.generators import PlayerGenerationResult  # noqa: E402
from generate_players import (  # noqa: E402
    _parse_args,
    _positive_int,
    print_generation_result,
)


def test_positive_int_accepts_positive_values():
    assert _positive_int("12") == 12


def test_positive_int_rejects_zero():
    with pytest.raises(Exception, match="at least 1"):
        _positive_int("0")


def test_parse_args_accepts_required_cli_options():
    args = _parse_args(
        [
            "--generation-run-id",
            "7",
            "--batch-id",
            "11",
            "--player-count",
            "50",
        ]
    )

    assert args.generation_run_id == 7
    assert args.batch_id == 11
    assert args.player_count == 50


def test_parse_args_allows_configured_player_count_default():
    args = _parse_args(["--generation-run-id", "7", "--batch-id", "11"])

    assert args.player_count is None


def test_print_generation_result_outputs_summary(capsys):
    print_generation_result(
        PlayerGenerationResult(
            generation_run_id=7,
            batch_id=11,
            rows_loaded=50,
            active_player_count_start=0,
            active_player_count_end=50,
        )
    )

    output = capsys.readouterr().out
    assert "generation_run_id=7" in output
    assert "batch_id=11" in output
    assert "rows_loaded=50" in output
    assert "active_player_count_end=50" in output
