"""Raw seed-data ingestion helpers."""

from .base import RawSeedLoadResult
from .first_names import FirstNameIngestor
from .last_names import LastNameIngestor
from .metro_areas import RawSeedIngestor
from .pickleball_clubs import (
    PickleballClubDistributionIngestor,
    PickleballClubNameIngestor,
)
from .state_prov_biases import StateProvBiasIngestor

SUPPORTED_RAW_DATASETS = frozenset(
    {
        "metro_areas_us",
        "metro_areas_ca",
        "pickleball_club_distributions",
        "pickleball_club_names",
        "last_names_us",
        "last_names_ca",
        "state_prov_biases_us",
        "state_prov_biases_ca",
        "first_names_us",
        "first_names_ca",
    }
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
    if dataset_type in {"last_names_us", "last_names_ca"}:
        return LastNameIngestor().load_dataset(
            dataset_type,
            input_path=input_path,
            session=session,
        )
    if dataset_type in {"state_prov_biases_us", "state_prov_biases_ca"}:
        return StateProvBiasIngestor().load_dataset(
            dataset_type,
            input_path=input_path,
            session=session,
        )
    if dataset_type in {"first_names_us", "first_names_ca"}:
        return FirstNameIngestor().load_dataset(
            dataset_type,
            input_path=input_path,
            session=session,
        )

    supported = ", ".join(sorted(SUPPORTED_RAW_DATASETS))
    raise ValueError(
        f"Unsupported dataset {dataset_type!r}; supported datasets: {supported}."
    )

__all__ = [
    "RawSeedIngestor",
    "FirstNameIngestor",
    "LastNameIngestor",
    "PickleballClubDistributionIngestor",
    "PickleballClubNameIngestor",
    "StateProvBiasIngestor",
    "RawSeedLoadResult",
    "SUPPORTED_RAW_DATASETS",
    "load_raw_seed_dataset",
]
