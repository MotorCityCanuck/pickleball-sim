"""Create a generation run and initial monthly batch control records."""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
import sys
from typing import Any, Sequence


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.generation import GenerationOrchestrator, InitialGenerationPlan  # noqa: E402


def _parse_batch_month(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "first batch month must use YYYY-MM-DD format"
        ) from exc
    return date(parsed.year, parsed.month, 1)


def _parse_parameter_snapshot(value: str | None) -> dict[str, Any] | None:
    if value is None:
        return None

    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(
            f"parameter snapshot must be valid JSON: {exc.msg}"
        ) from exc

    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError("parameter snapshot must be a JSON object")
    return parsed


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a generation run and initial monthly batch control records. "
            "This does not generate players, clubs, matches, ratings, or exports."
        )
    )
    parser.add_argument(
        "--generation-name",
        required=True,
        help="Human-readable name for the generation run.",
    )
    parser.add_argument(
        "--first-batch-month",
        required=True,
        type=_parse_batch_month,
        help="First historical batch month as YYYY-MM-DD. Day is normalized to 01.",
    )
    parser.add_argument(
        "--seed-value",
        type=int,
        help="Optional run seed. Defaults to SIMULATION_DEFAULT_SEED.",
    )
    parser.add_argument(
        "--historical-months",
        type=int,
        help=(
            "Number of initial historical monthly batches. Defaults to "
            "SIMULATION_INITIAL_HISTORICAL_MONTHS."
        ),
    )
    parser.add_argument(
        "--parameter-json",
        type=_parse_parameter_snapshot,
        help="Optional JSON object stored in generation_runs.parameter_snapshot.",
    )
    return parser.parse_args(argv)


def create_generation_plan(args: argparse.Namespace) -> InitialGenerationPlan:
    orchestrator = GenerationOrchestrator()
    return orchestrator.create_initial_generation_plan(
        args.generation_name,
        args.first_batch_month,
        seed_value=args.seed_value,
        parameter_snapshot=args.parameter_json,
        historical_months=args.historical_months,
    )


def print_generation_plan(plan: InitialGenerationPlan) -> None:
    generation_run = plan.generation_run
    print(f"generation_run_id={generation_run.id}")
    print(f"generation_name={generation_run.generation_name}")
    print(f"generation_status={generation_run.status}")
    print(f"seed_value={generation_run.seed_value}")
    print(f"simulation_version={generation_run.simulation_version}")
    print(f"monthly_batch_count={len(plan.monthly_batches)}")
    for batch in plan.monthly_batches:
        print(
            "monthly_batch="
            f"id:{batch.id},"
            f"month:{batch.batch_month.isoformat()},"
            f"sequence:{batch.batch_sequence},"
            f"status:{batch.processing_status}"
        )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    plan = create_generation_plan(args)
    print_generation_plan(plan)


if __name__ == "__main__":
    main()
