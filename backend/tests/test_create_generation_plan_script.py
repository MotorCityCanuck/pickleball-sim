"""Tests for the generation plan creation CLI helpers."""
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

from create_generation_plan import (  # noqa: E402
    _parse_args,
    _parse_batch_month,
    _parse_parameter_snapshot,
    print_generation_plan,
)


class _GenerationRun:
    id = 7
    generation_name = "cli probe"
    status = "pending"
    seed_value = 123
    simulation_version = "test"


class _MonthlyBatch:
    id = 11
    batch_month = date(2026, 1, 1)
    batch_sequence = 1
    processing_status = "pending"


class _Plan:
    generation_run = _GenerationRun()
    monthly_batches = [_MonthlyBatch()]


def test_parse_batch_month_normalizes_to_first_day():
    assert _parse_batch_month("2026-05-16") == date(2026, 5, 1)


def test_parse_parameter_snapshot_accepts_json_object():
    assert _parse_parameter_snapshot('{"mode": "smoke"}') == {"mode": "smoke"}


def test_parse_parameter_snapshot_rejects_non_object():
    with pytest.raises(Exception, match="JSON object"):
        _parse_parameter_snapshot('["not", "an", "object"]')


def test_parse_args_accepts_required_cli_options():
    args = _parse_args(
        [
            "--generation-name",
            "cli setup",
            "--first-batch-month",
            "2026-01-15",
            "--seed-value",
            "99",
            "--historical-months",
            "6",
            "--parameter-json",
            '{"source": "test"}',
        ]
    )

    assert args.generation_name == "cli setup"
    assert args.first_batch_month == date(2026, 1, 1)
    assert args.seed_value == 99
    assert args.historical_months == 6
    assert args.parameter_json == {"source": "test"}


def test_print_generation_plan_outputs_created_record_summary(capsys):
    print_generation_plan(_Plan())

    output = capsys.readouterr().out
    assert "generation_run_id=7" in output
    assert "monthly_batch_count=1" in output
    assert "monthly_batch=id:11,month:2026-01-01,sequence:1,status:pending" in output
