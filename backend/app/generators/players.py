"""Generate synthetic player identity and registration records."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from bisect import bisect_left
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
    PlayerRatingHistory,
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
    monthly_player_inactivation_rate: Decimal
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
    initial_rating_std_dev: Decimal
    rating_min: Decimal
    rating_max: Decimal
    initial_rating_elite_tail_rate: Decimal
    initial_rating_elite_min: Decimal
    initial_rating_elite_max: Decimal
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
        monthly_player_inactivation_rate = _decimal(
            player_config.get("monthly_player_inactivation_rate", 0.01)
        )
        if (
            monthly_player_inactivation_rate < 0
            or monthly_player_inactivation_rate > 1
        ):
            raise ValueError(
                "player_generation.monthly_player_inactivation_rate must be between 0 and 1"
            )

        age_min = int(player_config.get("age_min", 18))
        age_max = int(player_config.get("age_max", 85))
        if age_min < 0 or age_max < age_min:
            raise ValueError("player_generation age bounds are invalid")
        rating_min = _decimal(ratings.get("rating_min", 0))
        rating_max = _decimal(ratings.get("rating_max", 5000))
        if rating_min < 0 or rating_max <= rating_min:
            raise ValueError("ratings rating bounds are invalid")
        elite_tail_rate = _decimal(ratings.get("initial_rating_elite_tail_rate", 0))
        if elite_tail_rate < 0 or elite_tail_rate > 1:
            raise ValueError("ratings.initial_rating_elite_tail_rate is invalid")
        elite_min = _decimal(ratings.get("initial_rating_elite_min", 4000))
        elite_max = _decimal(ratings.get("initial_rating_elite_max", 4500))
        if elite_min < rating_min or elite_max > rating_max or elite_max <= elite_min:
            raise ValueError("ratings elite rating bounds are invalid")
        initial_confidence_score = _decimal(
            confidence.get("initial_confidence_score", 0.1)
        )
        if initial_confidence_score < 0 or initial_confidence_score > 1:
            raise ValueError("confidence.initial_confidence_score must be between 0 and 1")

        return cls(
            player_count=player_count,
            monthly_player_inactivation_rate=monthly_player_inactivation_rate,
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
            initial_rating_std_dev=_decimal(
                ratings.get("initial_rating_std_dev", 200)
            ),
            rating_min=rating_min,
            rating_max=rating_max,
            initial_rating_elite_tail_rate=elite_tail_rate,
            initial_rating_elite_min=elite_min,
            initial_rating_elite_max=elite_max,
            initial_confidence_score=initial_confidence_score,
        )


@dataclass(frozen=True)
class NameCandidate:
    """Weighted name candidate."""

    value: str
    weight: Decimal


class WeightedSampler[T]:
    """Precomputed weighted random sampler for repeated draws."""

    def __init__(self, weighted_items: Sequence[tuple[T, Any] | NameCandidate]) -> None:
        if not weighted_items:
            raise ValueError("Cannot choose from an empty weighted item list")

        self.values: list[T | str] = []
        self.cumulative_weights: list[float] = []
        total = 0.0

        for item in weighted_items:
            if isinstance(item, NameCandidate):
                value, weight = item.value, item.weight
            else:
                value, weight = item
            numeric_weight = float(_positive_weight(weight))
            self.values.append(value)
            total += numeric_weight
            self.cumulative_weights.append(total)

        self.total_weight = total

    def choose(self, rng: random.Random) -> T | str:
        """Choose one value using cached cumulative weights."""
        if self.total_weight <= 0:
            return self.values[rng.randrange(len(self.values))]

        target = rng.random() * self.total_weight
        index = bisect_left(self.cumulative_weights, target)
        if index >= len(self.values):
            index = len(self.values) - 1
        return self.values[index]


class NameIndex:
    """Cached database lookup for first and last name probabilities."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.first_exact: dict[
            tuple[str, str, int, str],
            WeightedSampler[str] | None,
        ] = {}
        self.first_country_year: dict[
            tuple[str, int, str],
            WeightedSampler[str] | None,
        ] = {}
        self.first_years_by_state_gender: dict[
            tuple[str, str, str],
            set[int],
        ] = {}
        self.first_years_by_country_gender: dict[
            tuple[str, str],
            set[int],
        ] = {}
        self.last_exact: dict[tuple[str, str], WeightedSampler[str] | None] = {}
        self.last_country: dict[str, WeightedSampler[str] | None] = {}

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
        sampler = self._first_exact_sampler(exact_key)
        if sampler:
            return sampler.choose(rng)

        nearest_state_year = _nearest(
            birth_year,
            self._first_state_years(
                country_code,
                state_province_code,
                gender,
            ),
        )
        if nearest_state_year is not None:
            sampler = self._first_exact_sampler(
                (country_code, state_province_code, nearest_state_year, gender)
            )
            if sampler:
                return sampler.choose(rng)

        country_year_key = (country_code, birth_year, gender)
        sampler = self._first_country_year_sampler(country_year_key)
        if sampler:
            return sampler.choose(rng)

        nearest_country_year = _nearest(
            birth_year,
            self._first_country_years(country_code, gender),
        )
        if nearest_country_year is not None:
            sampler = self._first_country_year_sampler(
                (country_code, nearest_country_year, gender)
            )
            if sampler:
                return sampler.choose(rng)

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
        sampler = self._last_exact_sampler(country_code, state_province_code)
        if sampler:
            return sampler.choose(rng)

        sampler = self._last_country_sampler(country_code)
        if sampler:
            return sampler.choose(rng)

        raise ValueError(f"No last-name distribution found for {country_code}")

    def _first_exact_sampler(
        self,
        key: tuple[str, str, int, str],
    ) -> WeightedSampler[str] | None:
        if key not in self.first_exact:
            country_code, state_province_code, birth_year, gender = key
            rows = self.session.execute(
                select(FirstName.first_name, FirstName.normalized_probability)
                .where(
                    FirstName.country_code == country_code,
                    FirstName.state_province_code == state_province_code,
                    FirstName.birth_year == birth_year,
                    FirstName.gender == gender,
                )
                .order_by(FirstName.id)
            ).all()
            self.first_exact[key] = _sampler_or_none(rows)
        return self.first_exact[key]

    def _first_country_year_sampler(
        self,
        key: tuple[str, int, str],
    ) -> WeightedSampler[str] | None:
        if key not in self.first_country_year:
            country_code, birth_year, gender = key
            rows = self.session.execute(
                select(FirstName.first_name, FirstName.normalized_probability)
                .where(
                    FirstName.country_code == country_code,
                    FirstName.birth_year == birth_year,
                    FirstName.gender == gender,
                )
                .order_by(FirstName.id)
            ).all()
            self.first_country_year[key] = _sampler_or_none(rows)
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

    def _last_exact_sampler(
        self,
        country_code: str,
        state_province_code: str,
    ) -> WeightedSampler[str] | None:
        key = (country_code, state_province_code)
        if key not in self.last_exact:
            rows = self.session.execute(
                select(LastName.last_name, LastName.normalized_probability)
                .where(
                    LastName.country_code == country_code,
                    LastName.state_province_code == state_province_code,
                )
                .order_by(LastName.id)
            ).all()
            self.last_exact[key] = _sampler_or_none(rows)
        return self.last_exact[key]

    def _last_country_sampler(self, country_code: str) -> WeightedSampler[str] | None:
        if country_code not in self.last_country:
            rows = self.session.execute(
                select(LastName.last_name, LastName.normalized_probability)
                .where(LastName.country_code == country_code)
                .order_by(LastName.id)
            ).all()
            self.last_country[country_code] = _sampler_or_none(rows)
        return self.last_country[country_code]


class ClubIndex:
    """Cached lookup for regional clubs used to anchor registration dates."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.clubs_by_region: dict[int, list[tuple[int, date | None, int | None]]] = {}
        self.club_samplers: dict[
            tuple[int, date],
            WeightedSampler[tuple[int, date | None]] | None,
        ] = {}

    def choose_club(
        self,
        rng: random.Random,
        *,
        region_id: int,
        batch_month: date,
    ) -> Club | None:
        sampler = self._club_sampler(region_id, batch_month)
        if sampler is None:
            return None
        club_id, founding_date = sampler.choose(rng)
        return Club(id=club_id, founding_date=founding_date)

    def _club_sampler(
        self,
        region_id: int,
        batch_month: date,
    ) -> WeightedSampler[tuple[int, date | None]] | None:
        key = (region_id, batch_month)
        if key not in self.club_samplers:
            candidates = [
                ((club_id, founding_date), Decimal(capacity or 1))
                for club_id, founding_date, capacity in self._clubs_for_region(region_id)
                if founding_date is None or founding_date <= batch_month
            ]
            self.club_samplers[key] = (
                WeightedSampler(candidates) if candidates else None
            )
        return self.club_samplers[key]

    def _clubs_for_region(self, region_id: int) -> list[tuple[int, date | None, int | None]]:
        if region_id not in self.clubs_by_region:
            self.clubs_by_region[region_id] = [
                (club_id, founding_date, member_capacity)
                for club_id, founding_date, member_capacity in self.session.execute(
                    select(Club.id, Club.founding_date, Club.member_capacity)
                    .where(Club.region_id == region_id)
                    .order_by(Club.id)
                )
            ]
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
        region_by_id = {region.id: region for region in regions}

        name_index = NameIndex(session)
        club_index = ClubIndex(session)
        region_sampler = WeightedSampler(
            [
                (region, _positive_weight(region.selection_probability))
                for region in regions
            ]
        )
        age_sampler = WeightedSampler(config.age_distribution)
        gender_sampler = WeightedSampler(config.gender_weights)
        dominant_hand_sampler = WeightedSampler(config.dominant_hand_weights)
        player_status_sampler = WeightedSampler(config.player_status_weights)
        rng = random.Random(int(generation_run.seed_value))
        active_start = int(existing_run_players or 0)
        registration_month = _month_start(batch.batch_month)
        chunk_size = 5_000

        with session.begin_nested():
            generated_so_far = 0
            while generated_so_far < target_count:
                current_chunk_size = min(chunk_size, target_count - generated_so_far)
                generated_players: list[Player] = []

                for _ in range(current_chunk_size):
                    region = region_sampler.choose(rng)
                    age = choose_age(rng, config, sampler=age_sampler)
                    birth_date = choose_birth_date(rng, age, registration_month)
                    gender = gender_sampler.choose(rng)
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
                            dominant_hand=dominant_hand_sampler.choose(rng),
                            home_region_id=region.id,
                            registration_date=registration_date,
                            initial_skill_seed=initial_skill_seed(rng, config),
                            player_status=player_status_sampler.choose(rng),
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
                session.flush()

                rating_history_rows = [
                    PlayerRatingHistory(
                        player_id=player.id,
                        rating_date=registration_month,
                        rating_type="initial",
                        rating_value=initial_rating_value(
                            generation_run.seed_value,
                            batch_id=batch_id,
                            player_sequence=generated_so_far + index,
                            config=config,
                        ),
                        confidence_score=config.initial_confidence_score,
                        volatility_score=Decimal("1.000"),
                        regional_adjustment_factor=_regional_adjustment_factor(
                            region_by_id.get(player.home_region_id)
                        ),
                        match_count_used=0,
                        calculation_version="initial_v1",
                        batch_id=batch_id,
                    )
                    for index, player in enumerate(generated_players)
                ]
                session.add_all(rating_history_rows)
                session.flush()

                for player in generated_players:
                    session.expunge(player)
                for registration in registrations:
                    session.expunge(registration)
                for rating_history_row in rating_history_rows:
                    session.expunge(rating_history_row)
                generated_so_far += current_chunk_size

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


def choose_age(
    rng: random.Random,
    config: PlayerGenerationConfig,
    *,
    sampler: WeightedSampler[tuple[int, int]] | None = None,
) -> int:
    """Choose an age from configured age cohorts."""
    low, high = (
        sampler.choose(rng)
        if sampler is not None
        else weighted_choice(rng, config.age_distribution)
    )
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


def initial_rating_value(
    seed_value: int,
    *,
    batch_id: int,
    player_sequence: int,
    config: PlayerGenerationConfig,
) -> Decimal:
    """Sample a bounded initial observed rating using a rating-specific seed."""
    rating_rng = random.Random(
        int(seed_value) * 1_000_003 + int(batch_id) * 10_007 + player_sequence
    )
    if (
        config.initial_rating_elite_tail_rate > 0
        and Decimal(str(rating_rng.random())) < config.initial_rating_elite_tail_rate
    ):
        elite_span = config.initial_rating_elite_max - config.initial_rating_elite_min
        value = (
            config.initial_rating_elite_min
            + Decimal(str(rating_rng.random())) * elite_span
        )
        return value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    sampled = Decimal(
        str(
            rating_rng.gauss(
                float(config.initial_rating_mean),
                float(config.initial_rating_std_dev),
            )
        )
    )
    value = max(config.rating_min, min(config.rating_max, sampled))
    return value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


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


def _sampler_or_none(rows: Sequence[tuple[T, Any]]) -> WeightedSampler[T] | None:
    if not rows:
        return None
    return WeightedSampler(rows)


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


def _regional_adjustment_factor(region: Region | None) -> Decimal:
    if region is None:
        return Decimal("1.0000")
    return _decimal(region.competitiveness_multiplier or 1).quantize(
        Decimal("0.0001"),
        rounding=ROUND_HALF_UP,
    )


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _nearest(target: int, candidates: set[int]) -> int | None:
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: (abs(candidate - target), candidate))


def _month_start(value: date) -> date:
    return date(value.year, value.month, 1)
