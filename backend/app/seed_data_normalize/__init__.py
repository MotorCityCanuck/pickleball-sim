"""Normalize raw seed data into production reference tables."""
from __future__ import annotations

from .base import SeedNormalizeResult
from .metro_areas import MetroAreaNormalizer


NORMALIZERS = {
    MetroAreaNormalizer.dataset: MetroAreaNormalizer,
}

SUPPORTED_DATASETS = frozenset(NORMALIZERS)


def normalize_seed_dataset(
    dataset: str,
    *,
    replace_production: bool = False,
    session=None,
) -> SeedNormalizeResult:
    """Normalize a supported raw seed dataset into production tables."""
    normalizer_type = NORMALIZERS.get(dataset)
    if normalizer_type is None:
        raise ValueError(f"Unsupported seed normalization dataset: {dataset}")

    return normalizer_type().normalize(
        replace_production=replace_production,
        session=session,
    )


__all__ = [
    "MetroAreaNormalizer",
    "NORMALIZERS",
    "SeedNormalizeResult",
    "SUPPORTED_DATASETS",
    "normalize_seed_dataset",
]
