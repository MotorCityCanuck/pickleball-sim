"""Raw seed-data ingestion helpers."""

from .base import RawSeedLoadResult
from .metro_areas import RawSeedIngestor
from .pickleball_clubs import (
    PickleballClubDistributionIngestor,
    PickleballClubNameIngestor,
)


def load_raw_seed_dataset(dataset_type, *, input_path=None, session=None):
    """Dispatch a raw seed dataset load to the owning ingestor."""
    if dataset_type in {"metro_areas_us", "metro_areas_ca"}:
        return RawSeedIngestor().load_dataset(
            dataset_type,
            input_path=input_path,
            session=session,
        )
    if dataset_type == "pickleball_club_distributions":
        return PickleballClubDistributionIngestor().load_dataset(
            dataset_type,
            input_path=input_path,
            session=session,
        )
    if dataset_type == "pickleball_club_names":
        return PickleballClubNameIngestor().load_dataset(
            dataset_type,
            input_path=input_path,
            session=session,
        )

    supported = ", ".join(
        sorted(
            {
                "metro_areas_us",
                "metro_areas_ca",
                "pickleball_club_distributions",
                "pickleball_club_names",
            }
        )
    )
    raise ValueError(
        f"Unsupported dataset {dataset_type!r}; supported datasets: {supported}."
    )

__all__ = [
    "RawSeedIngestor",
    "PickleballClubDistributionIngestor",
    "PickleballClubNameIngestor",
    "RawSeedLoadResult",
    "load_raw_seed_dataset",
]
