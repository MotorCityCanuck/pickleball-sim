"""Tests for the club membership generation CLI helpers."""
from pathlib import Path
import sys

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

SCRIPTS_DIR = BACKEND_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from app.generators import ClubMembershipGenerationResult  # noqa: E402
from generate_club_memberships import (  # noqa: E402
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
    args = _parse_args(["--generation-run-id", "7"])

    assert args.generation_run_id == 7


def test_print_generation_result_outputs_summary(capsys):
    print_generation_result(
        ClubMembershipGenerationResult(
            generation_run_id=7,
            players_evaluated=100,
            affiliated_player_count=88,
            unaffiliated_player_count=12,
            multi_club_player_count=6,
            rows_loaded=94,
        )
    )

    output = capsys.readouterr().out
    assert "generation_run_id=7" in output
    assert "players_evaluated=100" in output
    assert "affiliated_player_count=88" in output
    assert "multi_club_player_count=6" in output
    assert "rows_loaded=94" in output
