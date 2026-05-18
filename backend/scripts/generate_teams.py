"""Generate point-in-time doubles teams for an existing monthly batch."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.generators import TeamGenerationResult, TeamGenerator  # noqa: E402


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("value must be an integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return parsed


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate active doubles teams and team memberships for an existing "
            "generation run monthly batch."
        )
    )
    parser.add_argument(
        "--generation-run-id",
        required=True,
        type=_positive_int,
        help="Existing generation_runs.id whose players should be teamed.",
    )
    parser.add_argument(
        "--batch-id",
        required=True,
        type=_positive_int,
        help="Existing monthly_batches.id that defines the point-in-time month.",
    )
    return parser.parse_args(argv)


def generate_teams(args: argparse.Namespace) -> TeamGenerationResult:
    return TeamGenerator().generate_for_batch(
        generation_run_id=args.generation_run_id,
        batch_id=args.batch_id,
    )


def print_generation_result(result: TeamGenerationResult) -> None:
    print(f"generation_run_id={result.generation_run_id}")
    print(f"batch_id={result.batch_id}")
    print(f"batch_month={result.batch_month.isoformat()}")
    print(f"eligible_player_count={result.eligible_player_count}")
    print(f"target_team_count={result.target_team_count}")
    print(f"rows_loaded={result.rows_loaded}")
    print(f"membership_rows_loaded={result.membership_rows_loaded}")
    print(f"leftover_player_count={result.leftover_player_count}")


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    result = generate_teams(args)
    print_generation_result(result)


if __name__ == "__main__":
    main()
