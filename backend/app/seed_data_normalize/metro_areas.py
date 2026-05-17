"""Normalize raw metro areas into production regions."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import RawMetroArea, RawPickleballClubDistribution, Region

from .base import SeedNormalizeResult, run_in_transaction


class MetroAreaNormalizer:
    """Promote raw metro area staging rows into production regions."""

    dataset = "metro_areas"

    def normalize(
        self,
        *,
        replace_production: bool = False,
        session: Session | None = None,
    ) -> SeedNormalizeResult:
        """Replace production region rows from raw metro area staging rows."""
        if not replace_production:
            raise ValueError("Metro area normalization requires --replace-production")

        def _normalize(active_session: Session) -> SeedNormalizeResult:
            raw_rows = list(
                active_session.scalars(
                    select(RawMetroArea).order_by(
                        RawMetroArea.country_code,
                        RawMetroArea.state_province_code,
                        RawMetroArea.metro_area_name,
                        RawMetroArea.id,
                    )
                )
            )
            if not raw_rows:
                raise ValueError("No raw_metro_areas rows are available to normalize")

            countries = sorted({row.country_code for row in raw_rows})
            delete_result = active_session.execute(
                delete(Region).where(Region.country_code.in_(countries))
            )

            metro_areas = aggregate_raw_metro_areas(raw_rows)
            metro_areas.extend(
                fallback_regions_from_club_distributions(active_session, metro_areas)
            )
            regions = [
                Region(
                    country_code=metro_area.country_code,
                    state_province_code=metro_area.state_province_code,
                    region_name=metro_area.metro_area_name,
                    region_type=metro_area.region_type,
                    population=metro_area.population,
                    selection_probability=metro_area.selection_probability,
                )
                for metro_area in metro_areas
            ]
            active_session.add_all(regions)
            active_session.flush()

            return SeedNormalizeResult(
                dataset=self.dataset,
                status="completed",
                rows_read=len(raw_rows),
                rows_deleted=delete_result.rowcount or 0,
                rows_loaded=len(regions),
            )

        return run_in_transaction(_normalize, session=session)


@dataclass
class AggregatedMetroArea:
    """Aggregated production metro-area values."""

    country_code: str
    state_province_code: str
    metro_area_name: str
    region_type: str
    population: int | None
    selection_probability: Decimal


def aggregate_raw_metro_areas(raw_rows: list[RawMetroArea]) -> list[AggregatedMetroArea]:
    """Aggregate raw metro rows that share the production region natural key."""
    aggregated: dict[tuple[str, str, str], AggregatedMetroArea] = {}

    for row in raw_rows:
        key = (
            row.country_code,
            row.state_province_code,
            row.metro_area_name,
        )
        if key not in aggregated:
            aggregated[key] = AggregatedMetroArea(
                country_code=row.country_code,
                state_province_code=row.state_province_code,
                metro_area_name=row.metro_area_name,
                region_type=infer_region_type(row),
                population=row.population,
                selection_probability=row.selection_probability,
            )
            continue

        metro_area = aggregated[key]
        metro_area.population += row.population
        metro_area.selection_probability += row.selection_probability

    return list(aggregated.values())


def infer_region_type(row: RawMetroArea) -> str:
    """Infer a stable production region type from raw metro area data."""
    if row.country_code == "US":
        return "MSA"

    if row.country_code == "CA":
        name = row.metro_area_name.strip()
        if "(CMA)" in name:
            return "CMA"
        if "(CA)" in name:
            return "CA"

    return "metro"


def fallback_regions_from_club_distributions(
    session: Session,
    metro_areas: list[AggregatedMetroArea],
) -> list[AggregatedMetroArea]:
    """Create fallback regions for positive club scopes absent from metro data."""
    existing_scopes = {
        (metro_area.country_code, metro_area.state_province_code)
        for metro_area in metro_areas
    }
    fallback_regions: list[AggregatedMetroArea] = []

    distributions = session.scalars(
        select(RawPickleballClubDistribution)
        .where(RawPickleballClubDistribution.target_club_count > 0)
        .order_by(
            RawPickleballClubDistribution.country_code,
            RawPickleballClubDistribution.state_province_code,
        )
    )
    for distribution in distributions:
        scope = (distribution.country_code, distribution.state_province_code)
        if scope in existing_scopes:
            continue

        fallback_regions.append(
            AggregatedMetroArea(
                country_code=distribution.country_code,
                state_province_code=distribution.state_province_code,
                metro_area_name=distribution.state_province_name,
                region_type="territory",
                population=None,
                selection_probability=Decimal("0.00000000"),
            )
        )
        existing_scopes.add(scope)

    return fallback_regions
