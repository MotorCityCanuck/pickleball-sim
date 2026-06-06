"""Round-robin scheduling and submission normalization."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import replace

from .dtos import PortfolioSlot, TournamentDivision, TournamentTeamEntry


def round_robin_pairings(
    entries: Iterable[TournamentTeamEntry],
) -> tuple[tuple[TournamentTeamEntry, TournamentTeamEntry], ...]:
    """Return every unique pair of entries for a single round robin."""
    ordered_entries = tuple(sorted(entries, key=lambda entry: entry.id))
    return tuple(
        (team_one, team_two)
        for index, team_one in enumerate(ordered_entries)
        for team_two in ordered_entries[index + 1 :]
    )


def build_division_from_submissions(
    *,
    slot: PortfolioSlot,
    submitted_group_team_ids: Iterable[tuple[int, int]],
    teams_by_id: Mapping[int, TournamentTeamEntry],
) -> TournamentDivision:
    """Collapse duplicate team selections into one entry with group credits."""
    selected_groups_by_team_id: dict[int, list[int]] = defaultdict(list)
    for group_id, team_id in submitted_group_team_ids:
        selected_groups_by_team_id[team_id].append(group_id)

    entries: list[TournamentTeamEntry] = []
    for team_id, group_ids in selected_groups_by_team_id.items():
        team = teams_by_id[team_id]
        country_matches = slot.country_code == "ALL" or team.country_code == slot.country_code
        if not country_matches or team.division != slot.division:
            raise ValueError(
                "submitted team does not match portfolio slot "
                f"{slot.country_code}/{slot.division}: {team_id}"
            )
        entries.append(
            replace(
                team,
                selected_by_group_ids=tuple(sorted(group_ids)),
            )
        )

    return TournamentDivision(
        slot=slot,
        entries=tuple(sorted(entries, key=lambda entry: entry.id)),
    )
