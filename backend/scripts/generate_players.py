"""Generate initial synthetic players for an existing generation run batch."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.generators import PlayerGenerationResult, PlayerGenerator  # noqa: E402


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
            "Generate initial player and player registration rows for an existing "
            "generation run and monthly batch."
        )
    )
    parser.add_argument(
        "--generation-run-id",
        required=True,
        type=_positive_int,
        help="Existing generation_runs.id to populate.",
    )
    parser.add_argument(
        "--batch-id",
        required=True,
        type=_positive_int,
        help="Existing monthly_batches.id to use for registrations.",
    )
    parser.add_argument(
        "--player-count",
        type=_positive_int,
        help="Optional override for smoke loads. Defaults to the run configuration.",
    )
    return parser.parse_args(argv)


def generate_players(args: argparse.Namespace) -> PlayerGenerationResult:
    return PlayerGenerator().generate_initial_population(
        generation_run_id=args.generation_run_id,
        batch_id=args.batch_id,
        player_count=args.player_count,
    )


def print_generation_result(result: PlayerGenerationResult) -> None:
    print(f"generation_run_id={result.generation_run_id}")
    print(f"batch_id={result.batch_id}")
    print(f"rows_loaded={result.rows_loaded}")
    print(f"active_player_count_start={result.active_player_count_start}")
    print(f"active_player_count_end={result.active_player_count_end}")


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    result = generate_players(args)
    print_generation_result(result)


if __name__ == "__main__":
    main()
