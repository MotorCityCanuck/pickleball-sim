"""Normalize raw seed data into production reference tables."""
from __future__ import annotations

from .base import SeedNormalizeResult
from .first_names import FirstNameNormalizer
from .last_names import LastNameNormalizer
from .metro_areas import MetroAreaNormalizer
from .pickleball_clubs import PickleballClubNormalizer


NORMALIZERS = {
    FirstNameNormalizer.dataset: FirstNameNormalizer,
    LastNameNormalizer.dataset: LastNameNormalizer,
    MetroAreaNormalizer.dataset: MetroAreaNormalizer,
    PickleballClubNormalizer.dataset: PickleballClubNormalizer,
}

SUPPORTED_DATASETS = frozenset(NORMALIZERS)


def normalize_seed_dataset(
    dataset: str,
    *,
    replace_production: bool = False,
    config_payload: dict | None = None,
    session=None,
) -> SeedNormalizeResult:
    """Normalize a supported raw seed dataset into production tables."""
    normalizer_type = NORMALIZERS.get(dataset)
    if normalizer_type is None:
        raise ValueError(f"Unsupported seed normalization dataset: {dataset}")

    normalizer = (
        normalizer_type(config_payload)
        if normalizer_type is PickleballClubNormalizer
        else normalizer_type()
    )

    return normalizer.normalize(
        replace_production=replace_production,
        session=session,
    )


__all__ = [
    "MetroAreaNormalizer",
    "FirstNameNormalizer",
    "LastNameNormalizer",
    "NORMALIZERS",
    "PickleballClubNormalizer",
    "SeedNormalizeResult",
    "SUPPORTED_DATASETS",
    "normalize_seed_dataset",
]
