"""Generate synthetic club memberships for an existing generation run."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.generators import (  # noqa: E402
    ClubMembershipGenerationResult,
    ClubMembershipGenerator,
)


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
            "Generate primary and secondary club membership rows for players "
            "in an existing generation run."
        )
    )
    parser.add_argument(
        "--generation-run-id",
        required=True,
        type=_positive_int,
        help="Existing generation_runs.id whose players should receive club memberships.",
    )
    return parser.parse_args(argv)


def generate_club_memberships(
    args: argparse.Namespace,
) -> ClubMembershipGenerationResult:
    return ClubMembershipGenerator().generate_for_run(
        generation_run_id=args.generation_run_id,
    )


def print_generation_result(result: ClubMembershipGenerationResult) -> None:
    print(f"generation_run_id={result.generation_run_id}")
    print(f"players_evaluated={result.players_evaluated}")
    print(f"affiliated_player_count={result.affiliated_player_count}")
    print(f"unaffiliated_player_count={result.unaffiliated_player_count}")
    print(f"multi_club_player_count={result.multi_club_player_count}")
    print(f"rows_loaded={result.rows_loaded}")


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    result = generate_club_memberships(args)
    print_generation_result(result)


if __name__ == "__main__":
    main()
