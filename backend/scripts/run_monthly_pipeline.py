"""Run the end-to-end monthly generation pipeline."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.generation import (  # noqa: E402
    MAX_PIPELINE_MONTHS,
    MonthlyGenerationPipeline,
    MultiMonthPipelineResult,
)


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be an integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return parsed


def _month_count(value: str) -> int:
    parsed = _positive_int(value)
    if parsed > MAX_PIPELINE_MONTHS:
        raise argparse.ArgumentTypeError(
            f"value must be no greater than {MAX_PIPELINE_MONTHS}"
        )
    return parsed


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run setup, match generation, and rating updates for up to 12 "
            "successive monthly batches."
        )
    )
    parser.add_argument(
        "--generation-run-id",
        required=True,
        type=_positive_int,
        help="Existing generation_runs.id to process.",
    )
    parser.add_argument(
        "--months",
        default=1,
        type=_month_count,
        help=f"Number of successive months to process, 1-{MAX_PIPELINE_MONTHS}.",
    )
    parser.add_argument(
        "--start-batch-id",
        type=_positive_int,
        help=(
            "Optional monthly_batches.id to start from. Defaults to the first "
            "batch for the generation run."
        ),
    )
    parser.add_argument(
        "--player-count",
        type=_positive_int,
        help=(
            "Optional initial player count override. Applies only if player "
            "setup is generated in the first processed month."
        ),
    )
    parser.add_argument(
        "--fail-existing",
        action="store_true",
        help="Fail instead of skipping stages that already have rows.",
    )
    return parser.parse_args(argv)


def run_pipeline(args: argparse.Namespace) -> MultiMonthPipelineResult:
    return MonthlyGenerationPipeline().run_months(
        generation_run_id=args.generation_run_id,
        months=args.months,
        start_batch_id=args.start_batch_id,
        player_count=args.player_count,
        skip_existing=not args.fail_existing,
    )


def print_pipeline_result(result: MultiMonthPipelineResult) -> None:
    print(f"generation_run_id={result.generation_run_id}")
    print(f"months_requested={result.months_requested}")
    for batch_result in result.batch_results:
        print(
            "batch="
            f"{batch_result.batch_id},"
            f"{batch_result.batch_month.isoformat()}"
        )
        for step_result in batch_result.step_results:
            detail_text = ",".join(
                f"{key}={value}" for key, value in sorted(step_result.details.items())
            )
            suffix = f",{detail_text}" if detail_text else ""
            print(
                f"  {step_result.step}={step_result.status}"
                f"{suffix}"
            )


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    result = run_pipeline(args)
    print_pipeline_result(result)


if __name__ == "__main__":
    main()
