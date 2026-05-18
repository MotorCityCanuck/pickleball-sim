"""Generate match-driven rating updates and audit logs for a batch."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.generators import RatingUpdateGenerator, RatingUpdateResult  # noqa: E402


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
            "Generate player rating updates and per-player, per-match rating "
            "audit logs for an existing monthly batch."
        )
    )
    parser.add_argument(
        "--batch-id",
        required=True,
        type=_positive_int,
        help="Existing monthly_batches.id whose matches should update ratings.",
    )
    return parser.parse_args(argv)


def generate_ratings(args: argparse.Namespace) -> RatingUpdateResult:
    return RatingUpdateGenerator().generate_for_batch(batch_id=args.batch_id)


def print_generation_result(result: RatingUpdateResult) -> None:
    print(f"batch_id={result.batch_id}")
    print(f"match_count={result.match_count}")
    print(f"player_update_count={result.player_update_count}")
    print(f"rating_history_count={result.rating_history_count}")
    print(f"log_count={result.log_count}")


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    result = generate_ratings(args)
    print_generation_result(result)


if __name__ == "__main__":
    main()
