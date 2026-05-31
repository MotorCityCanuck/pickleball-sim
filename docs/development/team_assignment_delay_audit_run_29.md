# Team Assignment Delay Audit: Run 29

- Generation run: `29`
- Audit target batch: `314` (`2024-12-01`)
- Snapshot: [run_000029_batch_000314_2024-12-01_20260531T115125Z.json](/home/brett/projects/pickleball-sim/data/realism_audit_snapshots/generation_run_000029/run_000029_batch_000314_2024-12-01_20260531T115125Z.json)

## Context

This note covers the new `team_assignment_delay_summary` realism audit and the related interpretation update for `zero_match_players_by_team_membership`.

Because the simulation is doubles-only, team membership is a prerequisite for match assignment. That means the old `100% zero-match unteamed` finding should be interpreted as a roster-readiness signal, not as a direct scheduling defect.

## Current Live Result

For run `29`, batch `314`:

| Metric | Value |
|---|---:|
| Active players considered | `117,901` |
| Players ever assigned to a team by batch `314` | `116,845` |
| Players still unteamed as of batch `314` | `1,056` |
| Average days from simulated creation to first team assignment | `12.79` |
| Average days unteamed, including unresolved players | `12.80` |
| Maximum days unteamed, including unresolved players | `305` |

## Interpretation

The main result is that team formation latency is not generally large for players who do get rostered:

- average time to first team assignment is about `12.8` days
- the unresolved active unteamed inventory is `1,056` players

That suggests the system is not broadly slow to roster players. The larger concern is the remaining unresolved tail:

- `1,056` active players were still unteamed by the audited December batch
- the longest unresolved duration was `305` days

So the issue is not average team-assignment speed. It is the persistence of a small but real long-unresolved cohort.

## Relationship to the Earlier Zero-Match Finding

Earlier audit work showed:

- all unteamed active players in the audited month had zero matches
- teamed players had very low zero-match rates

That remains logically consistent with doubles-only play.

What this new audit adds is the timing dimension:

- most players who become rostered do so fairly quickly
- the problematic population is the subset that remains unteamed for a long time

## Recommended Next Cut

The next useful audit addition is a segmentation of team-assignment delay by:

1. `initial_batch` vs `later_batch`
2. region
3. club affiliation

That will show whether the unresolved tail is concentrated in:

- late registrations
- sparse or overloaded regions
- unaffiliated players
- another specific lifecycle gap

