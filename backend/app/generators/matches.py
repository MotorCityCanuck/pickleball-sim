"""Generate monthly matches, match teams, players, and games."""
from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
import random
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.default_configuration import DEFAULT_CONFIG_PAYLOAD
from app.db.session import session_scope
from app.models import (
    Match,
    MatchTeam,
    MatchTeamPlayer,
    MonthlyBatch,
    Player,
    PlayerRatingHistory,
    Team,
    TeamMembership,
)

from .games import games_per_match, generate_match_games
from .players import WeightedSampler, _decimal


@dataclass(frozen=True)
class MatchGenerationConfig:
    """Match generation settings resolved from a configuration payload."""

    matches_per_team_per_month: Decimal
    saturday_weight: Decimal
    sunday_weight: Decimal
    friday_weight: Decimal
    weekday_evening_weight: Decimal
    max_daily_matches_per_team: int
    match_type_weights: tuple[tuple[str, Decimal], ...]
    rating_band_width: dict[str, Decimal]
    matchmaking_noise_factor: Decimal
    locality_weight: Decimal
    games_per_match: dict[str, int]
    game_target_score: int
    win_by_two_rule_enabled: bool
    win_by_two_extension_rate: Decimal
    score_noise_std_dev: Decimal
    upset_probability_boost: Decimal

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "MatchGenerationConfig":
        source = payload or DEFAULT_CONFIG_PAYLOAD
        scheduling = source.get("match_scheduling", {})
        match_types = source.get("match_types", {})
        matchmaking = source.get("matchmaking", {})
        games = source.get("games_and_scores", {})

        max_daily = int(scheduling.get("max_daily_matches_per_team", 2))
        if max_daily < 1:
            raise ValueError("max_daily_matches_per_team must be at least 1")

        game_target_score = int(games.get("game_target_score", 11))
        if game_target_score not in {11, 15, 21}:
            raise ValueError("game_target_score must be 11, 15, or 21")

        return cls(
            matches_per_team_per_month=_positive_decimal(
                scheduling.get("matches_per_team_per_month", 4.0),
                "matches_per_team_per_month",
            ),
            saturday_weight=_positive_decimal(
                scheduling.get("saturday_weight", 2.25),
                "saturday_weight",
            ),
            sunday_weight=_positive_decimal(
                scheduling.get("sunday_weight", 1.85),
                "sunday_weight",
            ),
            friday_weight=_positive_decimal(
                scheduling.get("friday_weight", 1.2),
                "friday_weight",
            ),
            weekday_evening_weight=_positive_decimal(
                scheduling.get("weekday_evening_weight", 1.0),
                "weekday_evening_weight",
            ),
            max_daily_matches_per_team=max_daily,
            match_type_weights=_weighted_probabilities(
                match_types.get(
                    "weights",
                    {
                        "recreational": 0.55,
                        "league": 0.2,
                        "ladder": 0.1,
                        "tournament": 0.1,
                        "challenge": 0.04,
                        "clinic": 0.01,
                    },
                ),
                "match_types.weights",
            ),
            rating_band_width={
                key: _positive_decimal(value, f"rating_band_width.{key}")
                for key, value in matchmaking.get(
                    "rating_band_width",
                    {
                        "recreational": 400,
                        "competitive": 150,
                        "tournament": 100,
                    },
                ).items()
            },
            matchmaking_noise_factor=_probability(
                matchmaking.get("matchmaking_noise_factor", 0.2),
                "matchmaking_noise_factor",
            ),
            locality_weight=_probability(
                matchmaking.get("locality_weight", 0.3),
                "locality_weight",
            ),
            games_per_match={
                key: int(value)
                for key, value in games.get(
                    "games_per_match",
                    {
                        "recreational": 1,
                        "league": 2,
                        "tournament": 3,
                    },
                ).items()
            },
            game_target_score=game_target_score,
            win_by_two_rule_enabled=bool(games.get("win_by_two_rule_enabled", True)),
            win_by_two_extension_rate=_probability(
                games.get("win_by_two_extension_rate", 0.10),
                "win_by_two_extension_rate",
            ),
            score_noise_std_dev=_positive_decimal(
                games.get("score_noise_std_dev", 1.5),
                "score_noise_std_dev",
            ),
            upset_probability_boost=_probability(
                games.get("upset_probability_boost", 0.15),
                "upset_probability_boost",
            ),
        )


@dataclass(frozen=True)
class MatchGenerationResult:
    """Summary of generated match rows."""

    batch_id: int
    match_count: int
    match_team_count: int
    match_team_player_count: int
    game_count: int


@dataclass(frozen=True)
class TeamCandidate:
    """Active team data used by matchmaking."""

    id: int
    team_type: str
    region_id: int | None
    average_rating: Decimal
    players: tuple[tuple[int, int, Decimal], ...]


class MatchGenerator:
    """Generate scheduled matches and games for one monthly batch."""

    def generate_for_batch(
        self,
        *,
        batch_id: int,
        session: Session | None = None,
    ) -> MatchGenerationResult:
        """Generate matches for an existing monthly batch."""
        if session is not None:
            return self._generate_for_batch(batch_id=batch_id, session=session)

        with session_scope() as active_session:
            return self._generate_for_batch(batch_id=batch_id, session=active_session)

    def _generate_for_batch(
        self,
        *,
        batch_id: int,
        session: Session,
    ) -> MatchGenerationResult:
        batch = session.get(MonthlyBatch, batch_id)
        if batch is None:
            raise ValueError(f"Monthly batch {batch_id} does not exist")

        existing_matches = session.scalar(
            select(func.count()).select_from(Match).where(Match.batch_id == batch_id)
        )
        if existing_matches:
            raise ValueError(f"Monthly batch {batch_id} already has matches")

        config = MatchGenerationConfig.from_payload(
            batch.generation_run.parameter_snapshot
            if hasattr(batch, "generation_run") and batch.generation_run
            else _generation_payload(session, batch)
        )
        teams = _active_teams(session, batch.generation_run_id, batch.batch_month)
        if len(teams) < 2:
            raise ValueError("At least two active teams are required")

        target_match_count = int(
            (Decimal(len(teams)) * config.matches_per_team_per_month / Decimal("2"))
            .to_integral_value(rounding=ROUND_HALF_UP)
        )
        rng = random.Random(
            int(batch.generation_run_id) * 1_000_003 + int(batch_id) * 10_007 + 41
        )
        date_sampler = _date_sampler(batch.batch_month, config)
        match_type_sampler = WeightedSampler(config.match_type_weights)
        team_day_counts: dict[tuple[int, date], int] = {}
        matches: list[Match] = []
        pairings: list[tuple[Match, TeamCandidate, TeamCandidate, Decimal]] = []
        attempts = 0
        max_attempts = max(target_match_count * 40, 200)

        while len(matches) < target_match_count and attempts < max_attempts:
            attempts += 1
            match_date = date_sampler.choose(rng)
            match_type = str(match_type_sampler.choose(rng))
            first_team = _choose_team(rng, teams, team_day_counts, match_date, config)
            if first_team is None:
                continue
            second_team = _choose_opponent(
                rng,
                first_team=first_team,
                teams=teams,
                match_date=match_date,
                match_type=match_type,
                team_day_counts=team_day_counts,
                config=config,
            )
            if second_team is None:
                continue

            expected_win_probability = _expected_win_probability(
                first_team.average_rating,
                second_team.average_rating,
            )
            match = Match(
                match_date=match_date,
                region_id=first_team.region_id or second_team.region_id,
                match_type=match_type,
                court_type="standard",
                match_format=_match_format(match_type, config),
                predicted_winning_team_number=(
                    1 if expected_win_probability >= Decimal("0.5") else 2
                ),
                predicted_win_probability=max(
                    expected_win_probability,
                    Decimal("1") - expected_win_probability,
                ),
                expected_competitiveness=_competitiveness(expected_win_probability),
                simulation_noise_factor=_noise_value(rng, config.matchmaking_noise_factor),
                batch_id=batch_id,
            )
            matches.append(match)
            pairings.append((match, first_team, second_team, expected_win_probability))
            team_day_counts[(first_team.id, match_date)] = (
                team_day_counts.get((first_team.id, match_date), 0) + 1
            )
            team_day_counts[(second_team.id, match_date)] = (
                team_day_counts.get((second_team.id, match_date), 0) + 1
            )

        session.add_all(matches)
        session.flush()

        match_teams: list[MatchTeam] = []
        match_team_players: list[MatchTeamPlayer] = []
        games = []
        for match, first_team, second_team, expected_prob in pairings:
            generated_games = generate_match_games(
                rng,
                match=match,
                expected_team_one_win_probability=expected_prob,
                match_type=match.match_type,
                config=config,
            )
            team_one = MatchTeam(
                match_id=match.id,
                team_number=1,
                team_score=generated_games.team_one_games_won,
                expected_win_probability=expected_prob,
                average_team_rating=first_team.average_rating,
            )
            team_two = MatchTeam(
                match_id=match.id,
                team_number=2,
                team_score=generated_games.team_two_games_won,
                expected_win_probability=Decimal("1") - expected_prob,
                average_team_rating=second_team.average_rating,
            )
            match_teams.extend([team_one, team_two])
            games.extend(generated_games.games)
            match.total_points_played = sum(
                game.team_one_score + game.team_two_score
                for game in generated_games.games
            )

        session.add_all(match_teams)
        session.flush()

        for pairing_index, (_, first_team, second_team, _) in enumerate(pairings):
            team_one = match_teams[pairing_index * 2]
            team_two = match_teams[pairing_index * 2 + 1]
            match_team_players.extend(_match_team_players(team_one, first_team))
            match_team_players.extend(_match_team_players(team_two, second_team))
            match = pairings[pairing_index][0]
            winning_match_team = (
                team_one if team_one.team_score > team_two.team_score else team_two
            )
            match.winning_team_id = winning_match_team.id

        session.add_all(match_team_players)
        session.add_all(games)
        session.flush()
        batch.match_count_generated = len(matches)
        session.flush()

        return MatchGenerationResult(
            batch_id=batch_id,
            match_count=len(matches),
            match_team_count=len(match_teams),
            match_team_player_count=len(match_team_players),
            game_count=len(games),
        )


def _generation_payload(session: Session, batch: MonthlyBatch) -> dict[str, Any] | None:
    from app.models import GenerationRun

    generation_run = session.get(GenerationRun, batch.generation_run_id)
    return generation_run.parameter_snapshot if generation_run is not None else None


def _active_teams(
    session: Session,
    generation_run_id: int,
    batch_month: date,
) -> list[TeamCandidate]:
    ratings: dict[int, Decimal] = {}
    for player_id, rating_value in session.execute(
        select(PlayerRatingHistory.player_id, PlayerRatingHistory.rating_value)
        .where(PlayerRatingHistory.rating_date <= batch_month)
        .order_by(PlayerRatingHistory.player_id, PlayerRatingHistory.rating_date.desc())
    ):
        ratings.setdefault(player_id, _decimal(rating_value))

    teams = session.scalars(
        select(Team)
        .where(
            Team.generation_run_id == generation_run_id,
            Team.team_status == "active",
            Team.formation_date <= batch_month,
            or_(Team.dissolution_date.is_(None), Team.dissolution_date > batch_month),
        )
        .order_by(Team.id)
    )
    candidates: list[TeamCandidate] = []
    for team in teams:
        active_memberships = [
            membership
            for membership in team.memberships
            if membership.joined_date <= batch_month
            and (membership.left_date is None or membership.left_date > batch_month)
            and membership.player_id in ratings
        ]
        if len(active_memberships) != 2:
            continue
        players = tuple(
            (
                membership.player_id,
                membership.player_position,
                ratings[membership.player_id],
            )
            for membership in sorted(
                active_memberships,
                key=lambda membership: membership.player_position,
            )
        )
        region_id = session.get(Player, players[0][0]).home_region_id
        average_rating = (players[0][2] + players[1][2]) / Decimal("2")
        candidates.append(
            TeamCandidate(
                id=team.id,
                team_type=team.team_type,
                region_id=region_id,
                average_rating=average_rating,
                players=players,
            )
        )
    return candidates


def _date_sampler(
    batch_month: date,
    config: MatchGenerationConfig,
) -> WeightedSampler[date]:
    _, last_day = monthrange(batch_month.year, batch_month.month)
    weighted_dates = []
    for day in range(1, last_day + 1):
        current_date = date(batch_month.year, batch_month.month, day)
        weekday = current_date.weekday()
        if weekday == 5:
            weight = config.saturday_weight
        elif weekday == 6:
            weight = config.sunday_weight
        elif weekday == 4:
            weight = config.friday_weight
        else:
            weight = config.weekday_evening_weight
        weighted_dates.append((current_date, weight))
    return WeightedSampler(weighted_dates)


def _choose_team(
    rng: random.Random,
    teams: list[TeamCandidate],
    team_day_counts: dict[tuple[int, date], int],
    match_date: date,
    config: MatchGenerationConfig,
) -> TeamCandidate | None:
    candidates = [
        team
        for team in teams
        if team_day_counts.get((team.id, match_date), 0)
        < config.max_daily_matches_per_team
    ]
    if not candidates:
        return None
    return candidates[rng.randrange(len(candidates))]


def _choose_opponent(
    rng: random.Random,
    *,
    first_team: TeamCandidate,
    teams: list[TeamCandidate],
    match_date: date,
    match_type: str,
    team_day_counts: dict[tuple[int, date], int],
    config: MatchGenerationConfig,
) -> TeamCandidate | None:
    candidates = [
        team
        for team in teams
        if team.id != first_team.id
        and team_day_counts.get((team.id, match_date), 0)
        < config.max_daily_matches_per_team
    ]
    if not candidates:
        return None
    band = _rating_band(match_type, config)
    preferred = [
        team
        for team in candidates
        if abs(team.average_rating - first_team.average_rating) <= band
    ]
    if preferred:
        candidates = preferred
    weighted_candidates = [
        (candidate, _opponent_weight(first_team, candidate, band, config, rng))
        for candidate in candidates
    ]
    return WeightedSampler(weighted_candidates).choose(rng)


def _opponent_weight(
    first_team: TeamCandidate,
    candidate: TeamCandidate,
    band: Decimal,
    config: MatchGenerationConfig,
    rng: random.Random,
) -> Decimal:
    rating_gap = abs(candidate.average_rating - first_team.average_rating)
    rating_score = max(Decimal("0.01"), Decimal("1") - rating_gap / (band or 1))
    locality_score = (
        Decimal("1")
        if candidate.region_id == first_team.region_id
        else Decimal("0.25")
    )
    noise = Decimal(str(rng.random())) * config.matchmaking_noise_factor
    return rating_score + locality_score * config.locality_weight + noise


def _rating_band(match_type: str, config: MatchGenerationConfig) -> Decimal:
    if match_type == "tournament":
        return config.rating_band_width.get("tournament", Decimal("100"))
    if match_type in {"league", "ladder", "challenge"}:
        return config.rating_band_width.get("competitive", Decimal("150"))
    return config.rating_band_width.get("recreational", Decimal("400"))


def _match_format(match_type: str, config: MatchGenerationConfig) -> str:
    games = games_per_match(match_type, config)
    return "single_game" if games == 1 else f"best_of_{games}"


def _expected_win_probability(rating_one: Decimal, rating_two: Decimal) -> Decimal:
    exponent = float((rating_two - rating_one) / Decimal("400"))
    probability = Decimal(str(1 / (1 + 10**exponent)))
    return probability.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _competitiveness(expected_win_probability: Decimal) -> Decimal:
    value = Decimal("1") - abs(expected_win_probability - Decimal("0.5")) * 2
    return value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def _noise_value(rng: random.Random, scale: Decimal) -> Decimal:
    return (Decimal(str(rng.random())) * scale).quantize(
        Decimal("0.001"),
        rounding=ROUND_HALF_UP,
    )


def _match_team_players(
    match_team: MatchTeam,
    team: TeamCandidate,
) -> list[MatchTeamPlayer]:
    return [
        MatchTeamPlayer(
            match_team_id=match_team.id,
            player_id=player_id,
            player_position=position,
            player_rating_at_match=rating,
        )
        for player_id, position, rating in team.players
    ]


def _weighted_probabilities(
    value: dict[str, Any],
    name: str,
) -> tuple[tuple[str, Decimal], ...]:
    parsed = tuple((key, _decimal(weight)) for key, weight in value.items())
    if not parsed:
        raise ValueError(f"{name} cannot be empty")
    total = sum(weight for _, weight in parsed)
    if abs(total - Decimal("1")) > Decimal("0.01"):
        raise ValueError(f"{name} must sum to 1.0")
    if any(weight < 0 for _, weight in parsed):
        raise ValueError(f"{name} cannot contain negative weights")
    return parsed


def _positive_decimal(value: Any, name: str) -> Decimal:
    parsed = _decimal(value)
    if parsed <= 0:
        raise ValueError(f"{name} must be positive")
    return parsed


def _probability(value: Any, name: str) -> Decimal:
    parsed = _decimal(value)
    if parsed < 0 or parsed > 1:
        raise ValueError(f"{name} must be between 0 and 1")
    return parsed
