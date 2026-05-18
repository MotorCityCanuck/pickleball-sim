"""Generate synthetic player identity and registration records."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import random
from typing import Any, Iterable, Sequence, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.default_configuration import DEFAULT_CONFIG_PAYLOAD
from app.db.session import session_scope
from app.models import (
    FirstName,
    GenerationRun,
    LastName,
    MonthlyBatch,
    Player,
    PlayerRegistration,
    Region,
    Club,
)


T = TypeVar("T")


@dataclass(frozen=True)
class PlayerGenerationResult:
    """Summary of generated player identity rows."""

    generation_run_id: int
    batch_id: int
    rows_loaded: int
    active_player_count_start: int
    active_player_count_end: int


@dataclass(frozen=True)
class PlayerGenerationConfig:
    """Player generation settings resolved from a configuration payload."""

    player_count: int
    age_min: int
    age_max: int
    age_distribution: tuple[tuple[tuple[int, int], Decimal], ...]
    gender_weights: tuple[tuple[str, Decimal], ...]
    dominant_hand_weights: tuple[tuple[str, Decimal], ...]
    player_status_weights: tuple[tuple[str, Decimal], ...]
    skill_mean: Decimal
    skill_std_dev: Decimal
    skill_lower_bias: Decimal
    skill_min: Decimal
    skill_max: Decimal
    initial_rating_mean: Decimal
    initial_confidence_score: Decimal

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "PlayerGenerationConfig":
        """Build typed player generation settings from JSON payload."""
        source = payload or DEFAULT_CONFIG_PAYLOAD
        simulation = source.get("simulation", {})
        player_config = source.get("player_generation", {})
        ratings = source.get("ratings", {})
        confidence = source.get("confidence", {})
        skill_seed = player_config.get("initial_skill_seed", {})

        player_count = int(
            player_config.get(
                "player_count",
                simulation.get("target_total_players", 0),
            )
        )
        if player_count < 1:
            raise ValueError("player_generation.player_count must be at least 1")

        age_min = int(player_config.get("age_min", 18))
        age_max = int(player_config.get("age_max", 85))
        if age_min < 0 or age_max < age_min:
            raise ValueError("player_generation age bounds are invalid")

        return cls(
            player_count=player_count,
            age_min=age_min,
            age_max=age_max,
            age_distribution=_age_distribution(
                player_config.get("age_distribution", {}),
                age_min=age_min,
                age_max=age_max,
            ),
            gender_weights=_weighted_items(
                player_config.get("gender_weights", {"male": 0.5, "female": 0.5}),
                value_map={"male": "M", "female": "F"},
            ),
            dominant_hand_weights=_weighted_items(
                player_config.get(
                    "dominant_hand_weights",
                    {"right": 0.88, "left": 0.10, "ambidextrous": 0.02},
                ),
                value_map={
                    "right": "RIGHT",
                    "left": "LEFT",
                    "ambidextrous": "AMBID",
                },
            ),
            player_status_weights=_weighted_items(
                player_config.get(
                    "player_status_weights",
                    {
                        "active": 0.94,
                        "injured": 0.02,
                        "retired": 0.02,
                        "inactive": 0.02,
                    },
                ),
                value_map={
                    "active": "ACTIVE",
                    "injured": "INJURED",
                    "retired": "RETIRED",
                    "inactive": "INACTIVE",
                },
            ),
            skill_mean=_decimal(skill_seed.get("mean", 1500)),
            skill_std_dev=_decimal(skill_seed.get("std_dev", 275)),
            skill_lower_bias=_decimal(skill_seed.get("lower_bias", 100)),
            skill_min=_decimal(skill_seed.get("min", 500)),
            skill_max=_decimal(skill_seed.get("max", 3500)),
            initial_rating_mean=_decimal(ratings.get("initial_rating_mean", 1500)),
            initial_confidence_score=_decimal(
                confidence.get("initial_confidence_score", 0.1)
            ),
        )


@dataclass(frozen=True)
class NameCandidate:
    """Weighted name candidate."""

    value: str
    weight: Decimal


class NameIndex:
    """Cached database lookup for first and last name probabilities."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.first_exact: dict[
            tuple[str, str, int, str],
            list[NameCandidate],
        ] = {}
        self.first_country_year: dict[
            tuple[str, int, str],
            list[NameCandidate],
        ] = {}
        self.first_years_by_state_gender: dict[
            tuple[str, str, str],
            set[int],
        ] = {}
        self.first_years_by_country_gender: dict[
            tuple[str, str],
            set[int],
        ] = {}
        self.last_exact: dict[tuple[str, str], list[NameCandidate]] = {}
        self.last_country: dict[str, list[NameCandidate]] = {}

    def choose_first_name(
        self,
        rng: random.Random,
        *,
        country_code: str,
        state_province_code: str,
        birth_year: int,
        gender: str,
    ) -> str:
        """Choose a first name using exact cohort then documented fallbacks."""
        exact_key = (country_code, state_province_code, birth_year, gender)
        candidates = self._first_exact_candidates(exact_key)
        if candidates:
            return weighted_choice(rng, candidates)

        nearest_state_year = _nearest(
            birth_year,
            self._first_state_years(
                country_code,
                state_province_code,
                gender,
            ),
        )
        if nearest_state_year is not None:
            candidates = self._first_exact_candidates(
                (country_code, state_province_code, nearest_state_year, gender)
            )
            return weighted_choice(rng, candidates)

        country_year_key = (country_code, birth_year, gender)
        candidates = self._first_country_year_candidates(country_year_key)
        if candidates:
            return weighted_choice(rng, candidates)

        nearest_country_year = _nearest(
            birth_year,
            self._first_country_years(country_code, gender),
        )
        if nearest_country_year is not None:
            return weighted_choice(
                rng,
                self._first_country_year_candidates(
                    (country_code, nearest_country_year, gender)
                ),
            )

        raise ValueError(
            "No first-name distribution found for "
            f"{country_code}/{state_province_code}/{birth_year}/{gender}"
        )

    def choose_last_name(
        self,
        rng: random.Random,
        *,
        country_code: str,
        state_province_code: str,
    ) -> str:
        """Choose a last name using exact state/province then country fallback."""
        candidates = self._last_exact_candidates(country_code, state_province_code)
        if candidates:
            return weighted_choice(rng, candidates)

        candidates = self._last_country_candidates(country_code)
        if candidates:
            return weighted_choice(rng, candidates)

        raise ValueError(f"No last-name distribution found for {country_code}")

    def _first_exact_candidates(
        self,
        key: tuple[str, str, int, str],
    ) -> list[NameCandidate]:
        if key not in self.first_exact:
            country_code, state_province_code, birth_year, gender = key
            rows = self.session.scalars(
                select(FirstName)
                .where(
                    FirstName.country_code == country_code,
                    FirstName.state_province_code == state_province_code,
                    FirstName.birth_year == birth_year,
                    FirstName.gender == gender,
                )
                .order_by(FirstName.id)
            )
            self.first_exact[key] = [
                NameCandidate(row.first_name, _positive_weight(row.normalized_probability))
                for row in rows
            ]
        return self.first_exact[key]

    def _first_country_year_candidates(
        self,
        key: tuple[str, int, str],
    ) -> list[NameCandidate]:
        if key not in self.first_country_year:
            country_code, birth_year, gender = key
            rows = self.session.scalars(
                select(FirstName)
                .where(
                    FirstName.country_code == country_code,
                    FirstName.birth_year == birth_year,
                    FirstName.gender == gender,
                )
                .order_by(FirstName.id)
            )
            self.first_country_year[key] = [
                NameCandidate(row.first_name, _positive_weight(row.normalized_probability))
                for row in rows
            ]
        return self.first_country_year[key]

    def _first_state_years(
        self,
        country_code: str,
        state_province_code: str,
        gender: str,
    ) -> set[int]:
        key = (country_code, state_province_code, gender)
        if key not in self.first_years_by_state_gender:
            self.first_years_by_state_gender[key] = set(
                self.session.scalars(
                    select(FirstName.birth_year)
                    .where(
                        FirstName.country_code == country_code,
                        FirstName.state_province_code == state_province_code,
                        FirstName.gender == gender,
                    )
                    .distinct()
                )
            )
        return self.first_years_by_state_gender[key]

    def _first_country_years(
        self,
        country_code: str,
        gender: str,
    ) -> set[int]:
        key = (country_code, gender)
        if key not in self.first_years_by_country_gender:
            self.first_years_by_country_gender[key] = set(
                self.session.scalars(
                    select(FirstName.birth_year)
                    .where(
                        FirstName.country_code == country_code,
                        FirstName.gender == gender,
                    )
                    .distinct()
                )
            )
        return self.first_years_by_country_gender[key]

    def _last_exact_candidates(
        self,
        country_code: str,
        state_province_code: str,
    ) -> list[NameCandidate]:
        key = (country_code, state_province_code)
        if key not in self.last_exact:
            rows = self.session.scalars(
                select(LastName)
                .where(
                    LastName.country_code == country_code,
                    LastName.state_province_code == state_province_code,
                )
                .order_by(LastName.id)
            )
            self.last_exact[key] = [
                NameCandidate(row.last_name, _positive_weight(row.normalized_probability))
                for row in rows
            ]
        return self.last_exact[key]

    def _last_country_candidates(self, country_code: str) -> list[NameCandidate]:
        if country_code not in self.last_country:
            rows = self.session.scalars(
                select(LastName)
                .where(LastName.country_code == country_code)
                .order_by(LastName.id)
            )
            self.last_country[country_code] = [
                NameCandidate(row.last_name, _positive_weight(row.normalized_probability))
                for row in rows
            ]
        return self.last_country[country_code]


class ClubIndex:
    """Cached lookup for regional clubs used to anchor registration dates."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.clubs_by_region: dict[int, list[Club]] = {}

    def choose_club(
        self,
        rng: random.Random,
        *,
        region_id: int,
        batch_month: date,
    ) -> Club | None:
        candidates = [
            club
            for club in self._clubs_for_region(region_id)
            if club.founding_date is None or club.founding_date <= batch_month
        ]
        if not candidates:
            return None
        weighted_clubs = [
            (club, Decimal(club.member_capacity or 1))
            for club in candidates
        ]
        return weighted_choice(rng, weighted_clubs)

    def _clubs_for_region(self, region_id: int) -> list[Club]:
        if region_id not in self.clubs_by_region:
            self.clubs_by_region[region_id] = list(
                self.session.scalars(
                    select(Club)
                    .where(Club.region_id == region_id)
                    .order_by(Club.id)
                )
            )
        return self.clubs_by_region[region_id]


class PlayerGenerator:
    """Generate player identity and player registration rows."""

    def generate_initial_population(
        self,
        *,
        generation_run_id: int,
        batch_id: int,
        player_count: int | None = None,
        session: Session | None = None,
    ) -> PlayerGenerationResult:
        """Generate initial players for a generation run and monthly batch."""
        if session is not None:
            return self._generate_initial_population(
                generation_run_id=generation_run_id,
                batch_id=batch_id,
                player_count=player_count,
                session=session,
            )

        with session_scope() as active_session:
            return self._generate_initial_population(
                generation_run_id=generation_run_id,
                batch_id=batch_id,
                player_count=player_count,
                session=active_session,
            )

    def _generate_initial_population(
        self,
        *,
        generation_run_id: int,
        batch_id: int,
        player_count: int | None,
        session: Session,
    ) -> PlayerGenerationResult:
        generation_run = session.get(GenerationRun, generation_run_id)
        if generation_run is None:
            raise ValueError(f"Generation run {generation_run_id} does not exist")

        batch = session.get(MonthlyBatch, batch_id)
        if batch is None:
            raise ValueError(f"Monthly batch {batch_id} does not exist")
        if batch.generation_run_id != generation_run_id:
            raise ValueError("Batch does not belong to the generation run")

        existing_run_players = session.scalar(
            select(func.count()).select_from(Player).where(
                Player.generation_run_id == generation_run_id
            )
        )
        if existing_run_players:
            raise ValueError(
                f"Generation run {generation_run_id} already has players"
            )

        existing_batch_registrations = session.scalar(
            select(func.count()).select_from(PlayerRegistration).where(
                PlayerRegistration.batch_id == batch_id
            )
        )
        if existing_batch_registrations:
            raise ValueError(f"Monthly batch {batch_id} already has registrations")

        config = PlayerGenerationConfig.from_payload(generation_run.parameter_snapshot)
        target_count = player_count if player_count is not None else config.player_count
        if target_count < 1:
            raise ValueError("player_count must be at least 1")

        regions = list(
            session.scalars(
                select(Region)
                .where(Region.country_code.in_(("US", "CA")))
                .order_by(Region.country_code, Region.state_province_code, Region.id)
            )
        )
        if not regions:
            raise ValueError("No production regions are available for player generation")

        name_index = NameIndex(session)
        club_index = ClubIndex(session)
        rng = random.Random(int(generation_run.seed_value))
        active_start = int(existing_run_players or 0)
        registration_month = _month_start(batch.batch_month)
        generated_players: list[Player] = []

        for _ in range(target_count):
            region = choose_region(rng, regions)
            age = choose_age(rng, config)
            birth_date = choose_birth_date(rng, age, registration_month)
            gender = weighted_choice(rng, config.gender_weights)
            first_name = name_index.choose_first_name(
                rng,
                country_code=region.country_code,
                state_province_code=region.state_province_code,
                birth_year=birth_date.year,
                gender=gender,
            )
            last_name = name_index.choose_last_name(
                rng,
                country_code=region.country_code,
                state_province_code=region.state_province_code,
            )
            associated_club = club_index.choose_club(
                rng,
                region_id=region.id,
                batch_month=registration_month,
            )
            registration_date = choose_registration_date(
                rng,
                batch_month=registration_month,
                birth_date=birth_date,
                associated_club=associated_club,
            )
            generated_players.append(
                Player(
                    first_name=first_name,
                    last_name=last_name,
                    gender=gender,
                    birth_date=birth_date,
                    dominant_hand=weighted_choice(rng, config.dominant_hand_weights),
                    home_region_id=region.id,
                    registration_date=registration_date,
                    initial_skill_seed=initial_skill_seed(rng, config),
                    player_status=weighted_choice(rng, config.player_status_weights),
                    generation_run_id=generation_run_id,
                )
            )

        session.add_all(generated_players)
        session.flush()

        registrations = [
            PlayerRegistration(
                player_id=player.id,
                batch_id=batch_id,
                registration_month=registration_month,
                assigned_region_id=player.home_region_id,
                initial_rating_value=config.initial_rating_mean,
                initial_confidence_score=config.initial_confidence_score,
            )
            for player in generated_players
        ]
        session.add_all(registrations)

        batch.active_player_count_start = active_start
        batch.new_player_count = target_count
        batch.active_player_count_end = active_start + target_count
        session.flush()

        return PlayerGenerationResult(
            generation_run_id=generation_run_id,
            batch_id=batch_id,
            rows_loaded=target_count,
            active_player_count_start=active_start,
            active_player_count_end=active_start + target_count,
        )


def choose_region(rng: random.Random, regions: Sequence[Region]) -> Region:
    """Choose a region by normalized selection probability or equal fallback."""
    weighted_regions = [
        (region, _positive_weight(region.selection_probability))
        for region in regions
    ]
    return weighted_choice(rng, weighted_regions)


def choose_age(rng: random.Random, config: PlayerGenerationConfig) -> int:
    """Choose an age from configured age cohorts."""
    low, high = weighted_choice(rng, config.age_distribution)
    low = max(low, config.age_min)
    high = min(high, config.age_max)
    if high < low:
        return config.age_min
    return rng.randint(low, high)


def choose_birth_date(
    rng: random.Random,
    age: int,
    registration_month: date,
) -> date:
    """Choose a birth date that makes the player approximately the sampled age."""
    year = registration_month.year - age
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)
    return date(year, month, day)


def choose_registration_date(
    rng: random.Random,
    *,
    batch_month: date,
    birth_date: date,
    associated_club: Club | None,
) -> date:
    """Choose a realistic registration date no earlier than club founding."""
    latest_date = batch_month
    if associated_club is None or associated_club.founding_date is None:
        return latest_date

    earliest_date = birth_date + timedelta(days=1)
    earliest_date = max(earliest_date, associated_club.founding_date)

    if earliest_date >= latest_date:
        return latest_date

    day_offset = rng.randint(0, (latest_date - earliest_date).days)
    return earliest_date + timedelta(days=day_offset)


def initial_skill_seed(
    rng: random.Random,
    config: PlayerGenerationConfig,
) -> Decimal:
    """Sample bounded initial hidden skill with modest lower-skill bias."""
    sampled = Decimal(str(rng.gauss(float(config.skill_mean), float(config.skill_std_dev))))
    value = sampled - config.skill_lower_bias
    value = max(config.skill_min, min(config.skill_max, value))
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def weighted_choice(
    rng: random.Random,
    weighted_items: Sequence[tuple[T, Decimal] | NameCandidate],
) -> T | str:
    """Choose a value from positive weighted items."""
    if not weighted_items:
        raise ValueError("Cannot choose from an empty weighted item list")

    normalized_items: list[tuple[Any, Decimal]] = []
    for item in weighted_items:
        if isinstance(item, NameCandidate):
            normalized_items.append((item.value, item.weight))
        else:
            normalized_items.append(item)

    total = sum(weight for _, weight in normalized_items)
    if total <= 0:
        return normalized_items[rng.randrange(len(normalized_items))][0]

    target = Decimal(str(rng.random())) * total
    cumulative = Decimal("0")
    for value, weight in normalized_items:
        cumulative += weight
        if target < cumulative:
            return value
    return normalized_items[-1][0]


def _age_distribution(
    value: dict[str, int | float | str],
    *,
    age_min: int,
    age_max: int,
) -> tuple[tuple[tuple[int, int], Decimal], ...]:
    distribution = value or {
        "18_29": 0.08,
        "30_44": 0.18,
        "45_59": 0.32,
        "60_74": 0.34,
        "75_plus": 0.08,
    }
    parsed: list[tuple[tuple[int, int], Decimal]] = []
    for key, weight in distribution.items():
        if key.endswith("_plus"):
            low = int(key.removesuffix("_plus"))
            high = age_max
        else:
            low_text, high_text = key.split("_", 1)
            low, high = int(low_text), int(high_text)
        parsed.append(((max(low, age_min), min(high, age_max)), _decimal(weight)))
    _validate_weights(parsed)
    return tuple(parsed)


def _weighted_items(
    value: dict[str, int | float | str],
    *,
    value_map: dict[str, str] | None = None,
) -> tuple[tuple[str, Decimal], ...]:
    parsed = tuple(
        (
            value_map.get(key, key) if value_map else key,
            _decimal(weight),
        )
        for key, weight in value.items()
    )
    _validate_weights(parsed)
    return parsed


def _validate_weights(weighted_items: Iterable[tuple[Any, Decimal]]) -> None:
    total = sum(weight for _, weight in weighted_items)
    if abs(total - Decimal("1")) > Decimal("0.01"):
        raise ValueError("Configured probability weights must sum to 1.0")
    if any(weight < 0 for _, weight in weighted_items):
        raise ValueError("Configured probability weights cannot be negative")


def _positive_weight(value: Any) -> Decimal:
    weight = _decimal(value or 0)
    return weight if weight > 0 else Decimal("0")


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _nearest(target: int, candidates: set[int]) -> int | None:
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: (abs(candidate - target), candidate))


def _month_start(value: date) -> date:
    return date(value.year, value.month, 1)
