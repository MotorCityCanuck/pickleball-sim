"""Tests for seed normalization CLI helpers."""
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

SCRIPTS_DIR = BACKEND_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from normalize_seed_data import _parse_args  # noqa: E402
from app.seed_data_normalize import SUPPORTED_DATASETS, normalize_seed_dataset  # noqa: E402


def test_parse_args_accepts_metro_areas_with_replace_flag():
    args = _parse_args(
        [
            "--dataset",
            "metro_areas",
            "--replace-production",
            "--configuration-profile",
            "default",
            "--configuration-version",
            "1",
        ]
    )

    assert args.dataset == "metro_areas"
    assert args.replace_production is True
    assert args.configuration_profile == "default"
    assert args.configuration_version == 1


def test_parse_args_defaults_replace_flag_to_false():
    args = _parse_args(
        [
            "--dataset",
            "metro_areas",
        ]
    )

    assert args.dataset == "metro_areas"
    assert args.replace_production is False


def test_supported_datasets_are_exposed_by_normalization_package():
    assert SUPPORTED_DATASETS == frozenset(
        {"first_names", "last_names", "metro_areas", "pickleball_clubs"}
    )


def test_rejects_unsupported_normalization_dataset():
    try:
        normalize_seed_dataset("unknown", replace_production=True)
    except ValueError as exc:
        assert "Unsupported seed normalization dataset" in str(exc)
    else:
        raise AssertionError("Expected unsupported dataset to raise ValueError")
