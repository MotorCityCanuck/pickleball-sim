"""Normalize raw pickleball club seed data into production clubs."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from hashlib import sha256
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.default_configuration import DEFAULT_CONFIG_PAYLOAD
from app.models import Club, RawPickleballClubDistribution, RawPickleballClubName, Region

from .base import SeedNormalizeResult, run_in_transaction


CLUB_TYPE_MAP = {
    "Community Recreation Club": "community_center",
    "Competitive Training Club": "dedicated_facility",
    "Indoor Facility Club": "dedicated_facility",
    "League Organization": "municipal_recreation",
    "Private Athletic Club": "private_club",
    "Public Park Club": "public_park",
    "Retirement Community Club": "community_center",
    "Social Club": "community_center",
    "Tournament Club": "dedicated_facility",
}

CAPACITY_RANGES = {
    "Tiny": (10, 30),
    "Small": (31, 75),
    "Medium": (76, 200),
    "Large": (201, 500),
    "Mega": (501, 1000),
}

COURT_RANGES = {
    "Tiny": (1, 2),
    "Small": (2, 4),
    "Medium": (4, 8),
    "Large": (8, 16),
    "Mega": (16, 32),
}

DEFAULT_INDOOR_COURT_RATIOS = {
    "dedicated_facility": Decimal("0.75"),
    "public_park": Decimal("0.00"),
    "private_club": Decimal("0.45"),
    "municipal_recreation": Decimal("0.35"),
    "default": Decimal("0.30"),
}


@dataclass(frozen=True)
class ClubGenerationConfig:
    """Configuration values used by club normalization."""

    capacity_ranges: dict[str, tuple[int, int]]
    court_ranges: dict[str, tuple[int, int]]
    indoor_court_ratios: dict[str, Decimal]

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None = None) -> "ClubGenerationConfig":
        """Build club-generation config from a JSON payload."""
        source = payload or DEFAULT_CONFIG_PAYLOAD
        club_config = source.get("club_generation", {})
        return cls(
            capacity_ranges=_range_map(
                club_config.get("capacity_ranges"),
                CAPACITY_RANGES,
            ),
            court_ranges=_range_map(
                club_config.get("court_ranges"),
                COURT_RANGES,
            ),
            indoor_court_ratios=_decimal_map(
                club_config.get("indoor_court_ratios"),
                DEFAULT_INDOOR_COURT_RATIOS,
            ),
        )


class PickleballClubNormalizer:
    """Promote raw club names and distributions into production clubs."""

    dataset = "pickleball_clubs"

    def __init__(self, config_payload: dict[str, Any] | None = None) -> None:
        self.config = ClubGenerationConfig.from_payload(config_payload)

    def normalize(
        self,
        *,
        replace_production: bool = False,
        session: Session | None = None,
    ) -> SeedNormalizeResult:
        """Replace production clubs from raw club names and distributions."""
        if not replace_production:
            raise ValueError("Pickleball club normalization requires --replace-production")

        def _normalize(active_session: Session) -> SeedNormalizeResult:
            rows_read = active_session.scalar(
                select(func.count()).select_from(RawPickleballClubDistribution)
            )
            if not rows_read:
                raise ValueError(
                    "No raw_pickleball_club_distributions rows are available to normalize"
                )

            distributions = list(
                active_session.scalars(
                    select(RawPickleballClubDistribution).order_by(
                        RawPickleballClubDistribution.country_code,
                        RawPickleballClubDistribution.state_province_code,
                    )
                )
            )
            names_by_scope = load_names_by_scope(active_session)
            regions_by_scope = load_regions_by_scope(active_session)
            validate_distributions(distributions, regions_by_scope)

            delete_result = active_session.execute(delete(Club))

            clubs: list[Club] = []
            for distribution in distributions:
                if distribution.target_club_count == 0:
                    continue

                scope = (
                    distribution.country_code,
                    distribution.state_province_code,
                )
                candidates = names_by_scope.get(scope, [])
                regions = regions_by_scope[scope]

                for index in range(distribution.target_club_count):
                    candidate = (
                        candidates[index]
                        if index < len(candidates)
                        else placeholder_candidate(distribution, index)
                    )
                    region = choose_region(
                        regions,
                        seed=f"{candidate.club_seed}|{distribution.country_code}|"
                        f"{distribution.state_province_code}|{index}",
                    )
                    club_type = map_club_type(candidate.club_type)
                    member_capacity = capacity_for(
                        candidate.size_tier,
                        candidate.club_seed,
                        self.config,
                    )
                    indoor_courts, outdoor_courts = court_counts_for(
                        club_type,
                        candidate.size_tier,
                        candidate.club_seed,
                        self.config,
                    )
                    clubs.append(
                        Club(
                            club_name=candidate.club_name,
                            region_id=region.id,
                            club_type=club_type,
                            competitiveness_level=competitiveness_level_for(
                                candidate.club_type,
                                candidate.size_tier,
                            ),
                            member_capacity=member_capacity,
                            founding_date=founding_date_for(
                                club_type,
                                candidate.size_tier,
                                candidate.club_seed,
                            ),
                            indoor_court_count=indoor_courts,
                            outdoor_court_count=outdoor_courts,
                        )
                    )

            active_session.add_all(clubs)
            active_session.flush()

            return SeedNormalizeResult(
                dataset=self.dataset,
                status="completed",
                rows_read=rows_read,
                rows_deleted=delete_result.rowcount or 0,
                rows_loaded=len(clubs),
            )

        return run_in_transaction(_normalize, session=session)


@dataclass(frozen=True)
class ClubCandidate:
    """Selected raw club candidate values."""

    club_seed: int
    club_name: str
    club_type: str | None
    size_tier: str | None


def load_names_by_scope(session: Session) -> dict[tuple[str, str], list[ClubCandidate]]:
    """Load staged club candidates keyed by country and state/province."""
    names_by_scope: dict[tuple[str, str], list[ClubCandidate]] = {}
    rows = session.scalars(
        select(RawPickleballClubName).order_by(
            RawPickleballClubName.country_code,
            RawPickleballClubName.state_province_code,
            RawPickleballClubName.club_seed,
        )
    )
    for row in rows:
        scope = (row.country_code, row.state_province_code)
        names_by_scope.setdefault(scope, []).append(
            ClubCandidate(
                club_seed=row.club_seed,
                club_name=row.club_name,
                club_type=row.club_type,
                size_tier=row.size_tier,
            )
        )
    return names_by_scope


def load_regions_by_scope(session: Session) -> dict[tuple[str, str], list[Region]]:
    """Load production regions keyed by country and state/province."""
    regions_by_scope: dict[tuple[str, str], list[Region]] = {}
    rows = session.scalars(
        select(Region)
        .where(
            Region.country_code.in_(("US", "CA")),
            Region.state_province_code.is_not(None),
        )
        .order_by(
            Region.country_code,
            Region.state_province_code,
            Region.region_name,
            Region.id,
        )
    )
    for row in rows:
        scope = (row.country_code, row.state_province_code)
        regions_by_scope.setdefault(scope, []).append(row)
    return regions_by_scope


def validate_distributions(
    distributions: list[RawPickleballClubDistribution],
    regions_by_scope: dict[tuple[str, str], list[Region]],
) -> None:
    """Validate distribution rows can be assigned to production regions."""
    missing_region_scopes = [
        (row.country_code, row.state_province_code)
        for row in distributions
        if row.target_club_count > 0
        and (row.country_code, row.state_province_code) not in regions_by_scope
    ]
    if missing_region_scopes:
        sample = ", ".join(
            f"{country}/{state}" for country, state in missing_region_scopes[:5]
        )
        raise ValueError(f"Club distributions have no eligible production regions: {sample}")


def placeholder_candidate(
    distribution: RawPickleballClubDistribution,
    index: int,
) -> ClubCandidate:
    """Return a visible placeholder candidate when staged names are short."""
    seed = deterministic_int(
        f"placeholder|{distribution.country_code}|"
        f"{distribution.state_province_code}|{index}"
    )
    return ClubCandidate(
        club_seed=seed,
        club_name=f"Not Enough Club Names {distribution.state_province_code}-{index + 1}",
        club_type="Community Recreation Club",
        size_tier="Tiny",
    )


def choose_region(regions: list[Region], *, seed: str) -> Region:
    """Choose one eligible region with deterministic weighted selection."""
    weights = [
        Decimal(region.selection_probability or 0)
        for region in regions
    ]
    total_weight = sum(weights)
    if total_weight <= 0:
        weights = [Decimal(1) for _ in regions]
        total_weight = Decimal(len(regions))

    target = deterministic_fraction(seed) * total_weight
    cumulative = Decimal(0)
    for region, weight in zip(regions, weights, strict=True):
        cumulative += weight
        if target < cumulative:
            return region
    return regions[-1]


def map_club_type(raw_club_type: str | None) -> str:
    """Map staged club type labels into the production club_type enum."""
    if raw_club_type in CLUB_TYPE_MAP:
        return CLUB_TYPE_MAP[raw_club_type]
    return "community_center"


def competitiveness_level_for(raw_club_type: str | None, size_tier: str | None) -> str:
    """Derive a deterministic broad competitiveness level."""
    if raw_club_type in {"Tournament Club", "Competitive Training Club"}:
        if size_tier in {"Large", "Mega"}:
            return "elite"
        return "competitive"
    if raw_club_type in {"League Organization", "Indoor Facility Club", "Private Athletic Club"}:
        return "mixed"
    return "recreational"


def capacity_for(
    size_tier: str | None,
    seed: int,
    config: ClubGenerationConfig | None = None,
) -> int:
    """Derive deterministic member capacity from raw size tier."""
    active_config = config or ClubGenerationConfig.from_payload()
    low, high = active_config.capacity_ranges.get(
        size_tier or "",
        active_config.capacity_ranges["Small"],
    )
    return low + deterministic_int(str(seed)) % (high - low + 1)


def founding_date_for(club_type: str, size_tier: str | None, seed: int) -> date:
    """Derive a plausible deterministic founding date."""
    if club_type in {"dedicated_facility", "resort"}:
        start_year, end_year = 2008, 2024
    elif club_type in {"public_park", "community_center", "municipal_recreation"}:
        start_year, end_year = 1980, 2020
    else:
        start_year, end_year = 1990, 2022

    if size_tier in {"Large", "Mega"}:
        start_year = max(1970, start_year - 10)

    span = end_year - start_year + 1
    value = deterministic_int(f"founding|{seed}|{club_type}|{size_tier}")
    year = start_year + value % span
    month = 1 + (value // 32) % 12
    day = 1 + (value // 512) % 28
    return date(year, month, day)


def court_counts_for(
    club_type: str,
    size_tier: str | None,
    seed: int,
    config: ClubGenerationConfig | None = None,
) -> tuple[int, int]:
    """Derive deterministic indoor and outdoor court counts."""
    active_config = config or ClubGenerationConfig.from_payload()
    low, high = active_config.court_ranges.get(
        size_tier or "",
        active_config.court_ranges["Small"],
    )
    total_courts = low + deterministic_int(f"courts|{seed}") % (high - low + 1)

    ratio = active_config.indoor_court_ratios.get(
        club_type,
        active_config.indoor_court_ratios["default"],
    )
    indoor = round(total_courts * ratio)
    if club_type == "dedicated_facility" and total_courts > 0:
        indoor = max(1, indoor)

    indoor = min(total_courts, indoor)
    return indoor, total_courts - indoor


def deterministic_fraction(seed: str) -> Decimal:
    """Return a deterministic fraction in [0, 1)."""
    value = deterministic_int(seed)
    return Decimal(value) / Decimal(2**64)


def deterministic_int(seed: str) -> int:
    """Return a deterministic integer from a seed string."""
    return int(sha256(seed.encode("utf-8")).hexdigest()[:16], 16)


def _range_map(
    value: dict[str, list[int] | tuple[int, int]] | None,
    fallback: dict[str, tuple[int, int]],
) -> dict[str, tuple[int, int]]:
    if value is None:
        return dict(fallback)

    ranges: dict[str, tuple[int, int]] = {}
    for key, bounds in value.items():
        if len(bounds) != 2:
            raise ValueError(f"{key} range must contain exactly two values")
        low, high = int(bounds[0]), int(bounds[1])
        if low < 0 or high < low:
            raise ValueError(f"{key} range must be non-negative and ordered")
        ranges[key.title()] = (low, high)

    for key, bounds in fallback.items():
        ranges.setdefault(key, bounds)
    return ranges


def _decimal_map(
    value: dict[str, int | float | str] | None,
    fallback: dict[str, Decimal],
) -> dict[str, Decimal]:
    if value is None:
        return dict(fallback)

    ratios = dict(fallback)
    for key, ratio in value.items():
        parsed = Decimal(str(ratio))
        if parsed < 0 or parsed > 1:
            raise ValueError(f"{key} ratio must be between 0 and 1")
        ratios[key] = parsed
    return ratios
