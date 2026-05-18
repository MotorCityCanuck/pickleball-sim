"""Generate monthly matches, match teams, players, and games for a batch."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.generators import MatchGenerationResult, MatchGenerator  # noqa: E402


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
            "Generate scheduled matches, participating teams/players, and "
            "game scores for an existing monthly batch."
        )
    )
    parser.add_argument(
        "--batch-id",
        required=True,
        type=_positive_int,
        help="Existing monthly_batches.id to populate with matches.",
    )
    return parser.parse_args(argv)


def generate_matches(args: argparse.Namespace) -> MatchGenerationResult:
    return MatchGenerator().generate_for_batch(batch_id=args.batch_id)


def print_generation_result(result: MatchGenerationResult) -> None:
    print(f"batch_id={result.batch_id}")
    print(f"match_count={result.match_count}")
    print(f"match_team_count={result.match_team_count}")
    print(f"match_team_player_count={result.match_team_player_count}")
    print(f"game_count={result.game_count}")


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    result = generate_matches(args)
    print_generation_result(result)


if __name__ == "__main__":
    main()
