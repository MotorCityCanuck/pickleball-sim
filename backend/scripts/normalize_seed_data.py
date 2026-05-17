"""Normalize staged raw seed datasets into production reference tables."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.seed_data_normalize import SUPPORTED_DATASETS, normalize_seed_dataset  # noqa: E402


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize raw seed data into ORM-backed production tables."
    )
    parser.add_argument(
        "--dataset",
        required=True,
        choices=sorted(SUPPORTED_DATASETS),
        help="Seed dataset to normalize.",
    )
    parser.add_argument(
        "--replace-production",
        action="store_true",
        help="Required to replace production reference rows for the dataset scope.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    result = normalize_seed_dataset(
        args.dataset,
        replace_production=args.replace_production,
    )

    print(f"dataset={result.dataset}")
    print(f"status={result.status}")
    print(f"rows_read={result.rows_read}")
    print(f"rows_deleted={result.rows_deleted}")
    print(f"rows_loaded={result.rows_loaded}")


if __name__ == "__main__":
    main()
