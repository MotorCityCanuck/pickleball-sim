"""Pure tournament match simulation."""
from __future__ import annotations

import random

from app.generators.games import simulate_match_games
from app.generators.match_outcome_probabilities import (
    tournament_hidden_adjusted_win_probability,
)

from .config import TournamentSimulationConfig
from .dtos import TournamentMatchResult, TournamentTeamEntry


def simulate_tournament_match(
    rng: random.Random,
    *,
    team_one: TournamentTeamEntry,
    team_two: TournamentTeamEntry,
    config: TournamentSimulationConfig,
) -> TournamentMatchResult:
    """Simulate one tournament match without persistence."""
    probability = tournament_hidden_adjusted_win_probability(
        team_one,
        team_two,
        match_date=config.match_date,
        hidden_bias_config=config.hidden_bias_config,
        rng=rng,
    )
    games = simulate_match_games(
        rng,
        expected_team_one_win_probability=probability.final_probability,
        match_type=config.match_type,
        config=config.game_config,
    )
    team_one_wins = games.team_one_games_won > games.team_two_games_won
    team_one_points = sum(game.team_one_score for game in games.games)
    team_two_points = sum(game.team_two_score for game in games.games)

    return TournamentMatchResult(
        team_one_id=team_one.id,
        team_two_id=team_two.id,
        winning_team_id=team_one.id if team_one_wins else team_two.id,
        losing_team_id=team_two.id if team_one_wins else team_one.id,
        team_one_games_won=games.team_one_games_won,
        team_two_games_won=games.team_two_games_won,
        team_one_points=team_one_points,
        team_two_points=team_two_points,
        probability=probability,
        games=games,
    )
