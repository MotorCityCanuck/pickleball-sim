"""Load raw seed datasets into staging tables."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Sequence


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.seed_data_ingest import load_raw_seed_dataset  # noqa: E402
from app.seed_data_ingest.metro_areas import SUPPORTED_DATASETS  # noqa: E402


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load raw seed data into ORM-backed staging tables."
    )
    parser.add_argument(
        "--dataset",
        required=True,
        choices=sorted(SUPPORTED_DATASETS),
        help="Raw seed dataset to load.",
    )
    parser.add_argument(
        "--input-path",
        type=Path,
        help=(
            "Optional source file or directory. Defaults to the documented "
            "data/raw path for the dataset."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = _parse_args(argv)
    result = load_raw_seed_dataset(args.dataset, input_path=args.input_path)

    print(f"load_run_id={result.load_run_id}")
    print(f"dataset_type={result.dataset_type}")
    print(f"status={result.status}")
    print(f"source_file_count={result.source_file_count}")
    print(f"rows_read={result.rows_read}")
    print(f"rows_loaded={result.rows_loaded}")
    print(f"rows_rejected={result.rows_rejected}")


if __name__ == "__main__":
    main()
