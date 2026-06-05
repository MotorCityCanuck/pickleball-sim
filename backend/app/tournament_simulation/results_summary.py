"""Standing calculation and tie-break ordering for round-robin results."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib

from .dtos import TeamStanding, TournamentMatchResult, TournamentTeamEntry


@dataclass
class _MutableStanding:
    team: TournamentTeamEntry
    match_wins: int = 0
    match_losses: int = 0
    games_won: int = 0
    games_lost: int = 0
    points_for: int = 0
    points_against: int = 0

    @property
    def game_differential(self) -> int:
        return self.games_won - self.games_lost

    @property
    def point_differential(self) -> int:
        return self.points_for - self.points_against


def summarize_standings(
    *,
    entries: tuple[TournamentTeamEntry, ...],
    matches: tuple[TournamentMatchResult, ...],
    seed: int,
) -> tuple[TeamStanding, ...]:
    """Return ranked standings using configured deterministic tie-breaks."""
    mutable = {entry.id: _MutableStanding(team=entry) for entry in entries}
    for match in matches:
        team_one = mutable[match.team_one_id]
        team_two = mutable[match.team_two_id]

        if match.winning_team_id == match.team_one_id:
            team_one.match_wins += 1
            team_two.match_losses += 1
        else:
            team_two.match_wins += 1
            team_one.match_losses += 1

        team_one.games_won += match.team_one_games_won
        team_one.games_lost += match.team_two_games_won
        team_two.games_won += match.team_two_games_won
        team_two.games_lost += match.team_one_games_won
        team_one.points_for += match.team_one_points
        team_one.points_against += match.team_two_points
        team_two.points_for += match.team_two_points
        team_two.points_against += match.team_one_points

    ordered_ids = _rank_team_ids(tuple(mutable.values()), matches, seed)
    return tuple(
        _to_standing(rank=index + 1, mutable=mutable[team_id])
        for index, team_id in enumerate(ordered_ids)
    )


def _rank_team_ids(
    standings: tuple[_MutableStanding, ...],
    matches: tuple[TournamentMatchResult, ...],
    seed: int,
) -> tuple[int, ...]:
    buckets: dict[int, list[_MutableStanding]] = {}
    for standing in standings:
        buckets.setdefault(standing.match_wins, []).append(standing)

    ordered: list[int] = []
    for match_wins in sorted(buckets.keys(), reverse=True):
        ordered.extend(_break_tie(tuple(buckets[match_wins]), matches, seed))
    return tuple(ordered)


def _break_tie(
    tied: tuple[_MutableStanding, ...],
    matches: tuple[TournamentMatchResult, ...],
    seed: int,
) -> tuple[int, ...]:
    if len(tied) == 1:
        return (tied[0].team.id,)

    tied_ids = {standing.team.id for standing in tied}
    head_to_head_wins = {team_id: 0 for team_id in tied_ids}
    for match in matches:
        if match.team_one_id in tied_ids and match.team_two_id in tied_ids:
            head_to_head_wins[match.winning_team_id] += 1

    return tuple(
        standing.team.id
        for standing in sorted(
            tied,
            key=lambda standing: (
                -head_to_head_wins[standing.team.id],
                -standing.game_differential,
                -standing.point_differential,
                _seeded_tiebreak_token(standing.team.id, seed),
                standing.team.id,
            ),
        )
    )


def _seeded_tiebreak_token(team_id: int, seed: int) -> str:
    value = f"{seed}:{team_id}".encode("ascii")
    return hashlib.sha256(value).hexdigest()


def _to_standing(*, rank: int, mutable: _MutableStanding) -> TeamStanding:
    return TeamStanding(
        team_id=mutable.team.id,
        rank=rank,
        match_wins=mutable.match_wins,
        match_losses=mutable.match_losses,
        games_won=mutable.games_won,
        games_lost=mutable.games_lost,
        points_for=mutable.points_for,
        points_against=mutable.points_against,
        game_differential=mutable.game_differential,
        point_differential=mutable.point_differential,
        selected_by_group_ids=mutable.team.selected_by_group_ids,
    )
