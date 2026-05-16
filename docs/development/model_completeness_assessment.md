# Model Completeness Assessment

This note compares the current ORM-first schema against the architecture and
generation-design documents.

## Current ORM Scope

Before this assessment, the live ORM defined 22 tables:

1. `generation_runs`
2. `regions`
3. `monthly_batches`
4. `players`
5. `player_rating_history`
6. `player_assessment_history`
7. `player_registrations`
8. `clubs`
9. `club_memberships`
10. `teams`
11. `team_memberships`
12. `tournaments`
13. `matches`
14. `match_teams`
15. `match_team_players`
16. `first_names`
17. `last_names`
18. `batch_runs`
19. `uploaded_files`
20. `export_runs`
21. `validation_results`
22. `job_status`

## Required Gap

`match_games` is the safest next required model.

The generation sequence includes a dedicated "Generate Games and Scores" step
whose outputs are game records and game score metrics. The current schema has
match-level records and match-team records, but it has no normalized child table
for one or more games inside a match.

Without `match_games`, the platform has no stable place to persist:

- game number within a match
- per-game team scores
- game winner
- target score
- win-by requirement
- score-level noise metrics
- chronological game result data used by rating updates

Status: implemented as the 23rd ORM table.

## Existing Coverage

The following documented concepts already have ORM coverage:

- simulation runs: `generation_runs`
- monthly processing: `monthly_batches`, `batch_runs`
- player identity: `players`
- new player intake: `player_registrations`
- rating snapshots and movement: `player_rating_history`
- assessment snapshots: `player_assessment_history`
- regions: `regions`
- clubs and memberships: `clubs`, `club_memberships`
- persistent teams and memberships: `teams`, `team_memberships`
- tournaments: `tournaments`
- match shells and match teams: `matches`, `match_teams`,
  `match_team_players`
- match games and scores: `match_games`
- consolidated name reference data: `first_names`, `last_names`
- operational metadata: `uploaded_files`, `export_runs`, `validation_results`,
  `job_status`

## Deferred Optional Gaps

The architecture documents also mention or imply several additional tables that
should not be implemented before `match_games`:

- `player_truth_state`: optional instructor-only hidden true-skill state.
- `team_chemistry_history`: useful for partnership analytics, but not required
  to persist legal match and game outcomes.
- `monthly_team_status_snapshots`: useful for team lifecycle analysis, but
  derivable from teams and memberships until the lifecycle engine matures.
- `team_dissolution_events`: useful audit data, but requires firmer lifecycle
  semantics first.
- `partnership_stats`: likely a derived analytics table or materialized view,
  not an immediate core ORM table.
- configuration tables: current docs treat run configuration as serialized
  parameter snapshots on `generation_runs`; normalized configuration tables can
  wait until the configuration API stabilizes.

## Recommended Implementation Order

1. Regenerate `backend/schema.sql` from ORM metadata.
2. Extend ORM consistency expectations for the new table, indexes,
   constraints, and foreign key.
3. Add a live smoke test proving game score constraints are enforced.
4. Reassess whether team chemistry or hidden truth state should come next after
   the match simulation pipeline has a complete persistence path.
