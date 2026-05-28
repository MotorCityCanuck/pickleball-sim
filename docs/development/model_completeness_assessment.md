# Model Completeness Assessment

This note compares the current ORM-first schema against the architecture and
generation-design documents.

## Current ORM Scope

The live ORM now defines 37 tables: 25 core platform tables, 8 raw seed-data
staging tables, 2 configuration repository tables, and 2 student dataset
release metadata tables. Before the
`match_games` assessment, the live ORM
defined these 22 core tables:

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

## Current Required Gap

The core persistence path for players, club memberships, teams, matches,
match teams, match players, games, and rating update audit rows is now
implemented. The next required gap is full monthly orchestration across these
modules plus export/validation, not another immediate core table.

The rating update engine consumes `match_games.expected_team_one_score_share`,
expected raw scores, actual scores, and prior `player_rating_history` rows to
append new rating history records and one `ratings_update_log` row per player
per match.

`match_games` is implemented and stores:

- game number within a match
- per-game team scores
- game winner
- target score
- win-by requirement
- expected team-one score share
- actual team-one score share
- expected raw score for both teams
- score-level noise metrics
- chronological game result data used by rating updates

## Existing Coverage

The following documented concepts already have ORM coverage:

- simulation runs: `generation_runs`
- monthly processing: `monthly_batches`, `batch_runs`
- player identity: `players`
- new player intake: `player_registrations`
- rating snapshots and movement: `player_rating_history`
- per-match rating update audit: `ratings_update_log`
- assessment snapshots: `player_assessment_history`
- regions: `regions`
- clubs and memberships: `clubs`, `club_memberships`
- persistent teams and memberships: `teams`, `team_memberships`
- tournaments: `tournaments`
- match shells and match teams: `matches`, `match_teams`,
  `match_team_players`
- match games, expected scores, and actual scores: `match_games`
- consolidated name reference data: `first_names`, `last_names`
- operational metadata: `uploaded_files`, `export_runs`, `validation_results`,
  `job_status`, `job_stage_progress`
- raw seed-data ingestion staging: `raw_seed_load_runs`,
  `raw_seed_load_errors`, `raw_metro_areas`, `raw_pickleball_club_names`,
  `raw_pickleball_club_distributions`, `raw_first_names`, `raw_last_names`,
  `raw_state_prov_biases`
- configuration repository storage: `configuration_profiles`,
  `configuration_profile_versions`
- student dataset release metadata: `student_dataset_releases`,
  `student_dataset_release_files`

## Deferred Optional Gaps

The architecture documents also mention or imply several additional tables that
remain optional or deferred:

- `player_truth_state`: optional instructor-only hidden true-skill state.
- `team_chemistry_history`: useful for partnership analytics, but not required
  to persist legal match and game outcomes.
- `monthly_team_status_snapshots`: useful for team lifecycle analysis, but
  derivable from teams and memberships until the lifecycle engine matures.
- `team_dissolution_events`: useful audit data, but requires firmer lifecycle
  semantics first.
- `partnership_stats`: likely a derived analytics table or materialized view,
  not an immediate core ORM table.
- typed configuration API models: current persistence uses versioned JSONB
  configuration profiles plus frozen `generation_runs.parameter_snapshot`;
  typed loader/service code should be added when the configuration surface
  expands beyond the current payload/profile workflow.

## Completed Follow-Up

1. Regenerate `backend/schema.sql` from ORM metadata.
2. Extend ORM consistency expectations for the new table, indexes,
   constraints, and foreign key.
3. Add a live smoke test proving game score constraints are enforced.

## Recommended Next Reassessment

Reassess monthly orchestration, export validation, team chemistry history,
hidden truth state, session tracking, and tournament bracket tables after the
current players, clubs, teams, matches, games, and rating update path is stable
under end-to-end monthly batch generation.
