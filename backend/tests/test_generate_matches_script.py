"""Tests for the match generation CLI helpers."""
from pathlib import Path
import sys

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

SCRIPTS_DIR = BACKEND_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from app.generators import MatchGenerationResult  # noqa: E402
from generate_matches import _parse_args, _positive_int, print_generation_result  # noqa: E402


def test_positive_int_accepts_positive_values():
    assert _positive_int("12") == 12


def test_positive_int_rejects_zero():
    with pytest.raises(Exception, match="at least 1"):
        _positive_int("0")


def test_parse_args_accepts_required_cli_options():
    args = _parse_args(["--batch-id", "11"])

    assert args.batch_id == 11


def test_print_generation_result_outputs_summary(capsys):
    print_generation_result(
        MatchGenerationResult(
            batch_id=11,
            match_count=20,
            match_team_count=40,
            match_team_player_count=80,
            game_count=20,
        )
    )

    output = capsys.readouterr().out
    assert "batch_id=11" in output
    assert "match_count=20" in output
    assert "match_team_count=40" in output
    assert "match_team_player_count=80" in output
    assert "game_count=20" in output
