"""Tests for raw seed ingestion CLI helpers."""
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

SCRIPTS_DIR = BACKEND_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from load_raw_seed_data import _parse_args  # noqa: E402


def test_parse_args_accepts_metro_dataset_and_input_path():
    args = _parse_args(
        [
            "--dataset",
            "metro_areas_us",
            "--input-path",
            "data/raw/metro_areas",
        ]
    )

    assert args.dataset == "metro_areas_us"
    assert args.input_path == Path("data/raw/metro_areas")


def test_parse_args_accepts_club_distribution_dataset():
    args = _parse_args(
        [
            "--dataset",
            "pickleball_club_distributions",
            "--input-path",
            "data/raw/pickleball_clubs/distributions",
        ]
    )

    assert args.dataset == "pickleball_club_distributions"
    assert args.input_path == Path("data/raw/pickleball_clubs/distributions")


def test_parse_args_accepts_club_name_dataset():
    args = _parse_args(
        [
            "--dataset",
            "pickleball_club_names",
            "--input-path",
            "data/raw/pickleball_clubs/names",
        ]
    )

    assert args.dataset == "pickleball_club_names"
    assert args.input_path == Path("data/raw/pickleball_clubs/names")


def test_parse_args_accepts_last_name_dataset():
    args = _parse_args(
        [
            "--dataset",
            "last_names_us",
            "--input-path",
            "data/raw/last_names",
        ]
    )

    assert args.dataset == "last_names_us"
    assert args.input_path == Path("data/raw/last_names")


def test_parse_args_accepts_state_prov_bias_dataset():
    args = _parse_args(
        [
            "--dataset",
            "state_prov_biases_us",
            "--input-path",
            "data/raw/last_names/state_prov_biases",
        ]
    )

    assert args.dataset == "state_prov_biases_us"
    assert args.input_path == Path("data/raw/last_names/state_prov_biases")


def test_parse_args_accepts_first_name_dataset():
    args = _parse_args(
        [
            "--dataset",
            "first_names_ca",
            "--input-path",
            "data/raw/first_names/ca",
        ]
    )

    assert args.dataset == "first_names_ca"
    assert args.input_path == Path("data/raw/first_names/ca")
