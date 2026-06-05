# Tournament Simulation Implementation Plan

## Purpose

This document is the build plan for adding Monte Carlo and official live
tournament simulation to the pickleball simulation platform.

The product and classroom architecture source is:

- `docs/architecture/NAPA_Monte_Carlo_Tournament_Architecture_v2.md`

This implementation plan translates that architecture into buildable increments,
schema impacts, service boundaries, test gates, and acceptance criteria.

## Core Decisions

- Tournament simulation is instructor-facing application functionality.
- Tournament simulation is independent from monthly synthetic data generation.
- Tournament simulation is independent from student dataset export workflows.
- Tournament simulation may read generated historical data, but must not mutate
  historical matches, generated games, player ratings, monthly batches, or
  student export release data.
- Tournament match and game outcome determination must reuse the existing
  `hidden_performance_bias` configuration and hidden-bias application semantics.
- Monte Carlo trial matches must not be written to `matches`, `match_games`,
  `match_teams`, or `match_team_players`.
- Tournament simulation must not trigger `ratings_update_log` generation.
- Official live tournament results should persist complete match and game
  results in dedicated tournament simulation tables.
- Monte Carlo simulation should persist aggregate outputs by default.
- Teams must have a persisted country identifier.
- Cross-country teams are prohibited.
- Student-facing exports should omit `teams.chemistry_score` and
  `teams.persistence_probability`.

## Initial Classroom Scope

- Six student groups.
- Each student group submits six existing NAPA team IDs.
- Portfolio slots:
  - Canada Men's Doubles
  - Canada Women's Doubles
  - Canada Mixed Doubles
  - USA Men's Doubles
  - USA Women's Doubles
  - USA Mixed Doubles
- Six country/division round-robin tournaments.
- Duplicate team selections collapse to one tournament entry per division.
- All groups selecting a duplicated team receive credit for that team's results.
- Teams are eligible only if active as of the tournament date.
- Tournament date is after the final generated batch date.
- Team strength uses latest `player_rating_history` as of the selected source
  batch.

## Non-Goals

- Do not add tournament trial rows to monthly generation tables.
- Do not update player ratings from tournament results.
- Do not include tournament internals in student dataset exports.
- Do not expose hidden factor formulas, weights, or values to students.
- Do not build elimination or playoff formats in the MVP.
- Do not optimize for the future 36-team-per-division stress target before MVP
  correctness is stable.

## Build Order

1. Team country support and export cleanup.
2. Shared match/game outcome logic.
3. In-memory tournament engine.
4. Eligibility and data loading.
5. Tournament persistence.
6. Service and API layer.
7. Control panel UI.
8. Performance and hardening.

## Increment 1: Team Country Support And Export Cleanup

Goal: make generated teams country-aware and remove hidden/proxy fields from
student-facing team data.

Likely files:

- `backend/app/models/teams.py`
- `backend/app/generators/teams.py`
- `backend/app/exports/student_dataset/projection.py`
- `backend/app/exports/student_dataset/queries.py`
- `backend/app/models/__init__.py`
- `backend/schema.sql`
- `backend/tests/schema_expectations.py`
- `backend/tests/test_team_generator.py`
- `backend/tests/test_student_dataset_projection.py`
- `backend/tests/test_orm_consistency.py`

### Increment 1.1: Add `teams.country_code`

Work:

- Add nullable or non-null ORM column based on compatibility decision.
- Prefer non-null for new generated teams once backfill/legacy behavior is
  handled.
- Add allowed values check constraint for `US` and `CA`.
- Add index if eligibility queries require it.
- Update schema expectations.
- Regenerate `backend/schema.sql` from ORM metadata.

Acceptance criteria:

- ORM consistency tests pass.
- Schema SQL includes the new column and constraints.
- Existing tests do not assume the old `teams` column set.

### Increment 1.2: Update Team Formation

Work:

- Derive team country from player home region country.
- Prevent or reject cross-country pairings.
- Persist `country_code` on each team.
- Ensure inactive/reactivated team logic preserves country.

Acceptance criteria:

- Generated teams have `country_code`.
- No generated team contains players from multiple countries.
- Team formation tests cover same-country success and cross-country rejection.

### Increment 1.3: Update Student Export Projection

Work:

- Include `teams.country_code` in student-facing `teams`.
- Exclude `teams.chemistry_score`.
- Exclude `teams.persistence_probability`.
- Update projection drift expectations.
- Update student dataset tests and data dictionary if needed.

Acceptance criteria:

- Student projection includes team country.
- Student projection omits chemistry and persistence.
- Projection contract tests pass.

## Increment 2: Shared Match/Game Outcome Logic

Goal: tournament simulation and monthly generation share hidden-bias semantics
without coupling tournament code to monthly persistence.

Likely files:

- `backend/app/generators/matches.py`
- `backend/app/generators/games.py`
- `backend/app/generators/hidden_performance_bias.py`
- new `backend/app/match_outcomes/` package or equivalent
- `backend/tests/test_match_generator.py`
- `backend/tests/test_hidden_performance_bias.py`
- new shared outcome tests

### Increment 2.1: Extract Pure Probability Helpers

Work:

- Extract or wrap Elo probability calculation.
- Extract or wrap competitiveness calculation.
- Keep monthly generator behavior unchanged.

Acceptance criteria:

- Existing match generator tests pass.
- New tests cover probability and competitiveness edge cases.

### Increment 2.2: Add Pure Game Result DTOs

Work:

- Define non-ORM game result DTOs.
- Adapt game simulation to produce pure results.
- Keep monthly generator responsible for converting pure results into
  `MatchGame` ORM rows.

Acceptance criteria:

- Monthly match/game persistence remains unchanged from caller perspective.
- Pure game simulation can be used without a database session or ORM model.

### Increment 2.3: Reuse Hidden Performance Bias

Work:

- Expose hidden-adjusted win probability through shared code.
- Reuse `hidden_performance_bias` config.
- Preserve debug behavior where appropriate for monthly generation.

Acceptance criteria:

- Tournament code can call shared outcome logic using team-like DTOs.
- Existing hidden-bias tests still pass.
- Regression tests prove monthly match generation still produces valid matches
  and games.

## Increment 3: In-Memory Tournament Engine

Goal: build deterministic tournament logic before persistence or UI.

Likely new package:

- `backend/app/tournament_simulation/config.py`
- `backend/app/tournament_simulation/round_robin.py`
- `backend/app/tournament_simulation/match_simulator.py`
- `backend/app/tournament_simulation/monte_carlo.py`
- `backend/app/tournament_simulation/student_scoring.py`
- `backend/app/tournament_simulation/results_summary.py`

Likely tests:

- `backend/tests/test_tournament_round_robin.py`
- `backend/tests/test_tournament_scoring.py`
- `backend/tests/test_tournament_monte_carlo.py`

### Increment 3.1: Define Tournament DTOs

Work:

- Define student group DTO.
- Define portfolio slot DTO.
- Define team entry DTO.
- Define division DTO.
- Define scoring config DTO.
- Define tournament result DTOs.

Acceptance criteria:

- DTOs can express all six country/division slots.
- DTOs are independent from ORM models.

### Increment 3.2: Build Round-Robin Scheduler

Work:

- Generate all pairings per country/division.
- Collapse duplicate selected teams into one entry.
- Track all student groups credited for each team entry.

Acceptance criteria:

- `n` unique teams produce `n * (n - 1) / 2` matches.
- Duplicate submissions do not duplicate tournament entries.
- Duplicate submissions preserve group credit mapping.

### Increment 3.3: Simulate One Division

Work:

- Use shared match/game outcome logic.
- Track match wins.
- Track games won/lost.
- Track point differential.
- Track per-team standings.

Acceptance criteria:

- One round-robin division can run entirely in memory.
- Results are deterministic for fixed seed.

### Increment 3.4: Add Tie-Breaks

Tie-break order:

1. Match wins
2. Head-to-head result among tied teams
3. Game differential
4. Point differential
5. Deterministic seeded tiebreak

Acceptance criteria:

- Unit tests cover each tie-break level.
- Seeded tiebreak is reproducible.

### Increment 3.5: Add Student Scoring

Work:

- Add configurable champion points.
- Add configurable runner-up points.
- Add configurable semifinalist/top-four points.
- Add configurable match-win points.
- Award match-win points from round-robin results.
- Keep semifinalist/top-four points inactive unless enabled by format config.

Acceptance criteria:

- Student group score is derived from all six submitted slots.
- Duplicate selected teams credit every selecting group.
- Scoring config changes affect output without code changes.

### Increment 3.6: Add Monte Carlo Aggregation

Work:

- Run repeated tournament simulations.
- Aggregate team championship probability.
- Aggregate medal/top-three probability.
- Aggregate average finish.
- Aggregate win percentage.
- Aggregate upset frequency.
- Aggregate student group expected score and rank distribution.

Acceptance criteria:

- Fixed seed and iteration count produce reproducible aggregates.
- Aggregates are computed without database access inside the simulation loop.

## Increment 4: Eligibility And Data Loading

Goal: safely connect generated data to the in-memory tournament engine.

Likely files:

- `backend/app/tournament_simulation/eligibility.py`
- `backend/app/tournament_simulation/team_loader.py`
- `backend/app/models/team_lifecycle_events.py`
- `backend/app/models/player_rating_history.py`
- `backend/app/models/team_memberships.py`
- new eligibility tests

### Increment 4.1: Load Latest Team/Player Ratings

Work:

- Select latest completed source batch.
- Load latest `player_rating_history` as of selected source batch.
- Load active team memberships as of tournament date.
- Compute team average rating from member ratings.

Acceptance criteria:

- Loader returns team entries with player IDs, ratings, average rating, country,
  division, and required hidden-bias attributes.
- Loader rejects teams with missing rating state.

### Increment 4.2: Validate Submitted Teams

Validation rules:

- Team exists.
- Team country matches portfolio slot.
- Team division matches portfolio slot.
- Team is active as of tournament date.
- Team has required active members.
- Team has required latest ratings.

Acceptance criteria:

- Validation returns field-specific errors suitable for UI display.
- Invalid submissions do not create runnable tournament inputs.

### Increment 4.3: Use Lifecycle History For Active Status

Work:

- Prefer `team_lifecycle_events` for active-as-of checks.
- Fall back to current `teams.team_status` and `dissolution_date` for older runs
  lacking lifecycle history.

Acceptance criteria:

- Active-as-of checks handle reactivation correctly when lifecycle history
  exists.
- Legacy fallback behavior is documented and tested.

## Increment 5: Tournament Persistence

Goal: persist tournament-specific data without touching monthly generation
tables.

Likely files:

- new tournament simulation ORM models
- `backend/app/models/__init__.py`
- `backend/schema.sql`
- `backend/tests/schema_expectations.py`
- `backend/app/exports/student_dataset/projection.py`
- `backend/tests/test_orm_consistency.py`

### Increment 5.1: Add Event And Submission Tables

Recommended tables:

- `tournament_events`
- `tournament_student_groups`
- `tournament_submissions`

Acceptance criteria:

- Event records identify source generation run, source batch, tournament date,
  name, and config snapshot.
- Submission rows are normalized by group and portfolio slot.

### Increment 5.2: Add Simulation Run Tables

Recommended table:

- `tournament_simulation_runs`

Fields should include:

- event ID
- run type: `monte_carlo` or `official`
- status
- seed
- iteration count
- config snapshot
- optional `job_status_id`
- timestamps

Acceptance criteria:

- Runs can be tracked independently from generation runs.
- Runs can be associated with background job status.

### Increment 5.3: Add Aggregate Result Tables

Recommended tables:

- `tournament_team_results`
- `tournament_group_results`
- `tournament_division_results`

Acceptance criteria:

- Monte Carlo aggregate results can be queried without replaying simulations.
- Result rows are keyed by simulation run and division.

### Increment 5.4: Add Official Result Tables

Recommended tables:

- `tournament_official_matches`
- `tournament_official_games`

Acceptance criteria:

- Official live tournament can persist every round-robin match.
- Official live tournament can persist every game inside each match.
- Results can be displayed or replayed without reading historical `matches`.

### Increment 5.5: Update ORM And Schema Contracts

Work:

- Add models and imports.
- Add indexes, foreign keys, check constraints, and unique constraints.
- Add new tables to schema expectations.
- Add new tables to student projection excluded source tables.
- Regenerate `backend/schema.sql`.

Acceptance criteria:

- ORM consistency tests pass.
- Projection coverage tests pass.
- New tournament tables are excluded from student dataset export.

## Increment 6: Service And API Layer

Goal: expose tested tournament behavior through backend services before UI.

Likely files:

- `backend/app/tournament_simulation/service.py`
- `backend/app/tournament_simulation/persistence.py`
- `backend/app/web/routes.py`
- `backend/app/web/control_panel_queries.py`
- new service/route tests

### Increment 6.1: Add Tournament Service

Work:

- Create tournament event.
- Save student groups.
- Save submissions.
- Validate submissions.
- Build in-memory tournament input from persisted submissions.

Acceptance criteria:

- Service can validate and prepare a tournament without running simulation.
- Invalid submissions return actionable errors.

### Increment 6.2: Add Run Service Methods

Work:

- Run Monte Carlo simulation.
- Run official tournament.
- Persist outputs.
- Fetch latest summaries.

Acceptance criteria:

- Monte Carlo run persists aggregate results.
- Official run persists match and game results.
- Runs are reproducible for fixed seed.

### Increment 6.3: Add Routes

Routes should support:

- submission validation
- event creation/update
- Monte Carlo start
- official run start
- latest result summary
- official match/game detail

Acceptance criteria:

- Route tests cover successful and invalid flows.
- Routes call service layer rather than embedding tournament logic.

### Increment 6.4: Add Background Job Support

Work:

- Use existing `BackgroundJobRunner`.
- Use `job_status` for Monte Carlo and official runs.
- Decide whether active tournament jobs block seed/generation/export actions.

Acceptance criteria:

- Long-running tournament jobs have visible status.
- Failed tournament jobs record errors.
- Background execution does not leave partial successful run state.

## Increment 7: Control Panel UI

Goal: add the instructor-facing tournament workflow last.

Likely files:

- `backend/app/templates/control_panel.html`
- new `backend/app/templates/partials/control_tournament_tab.html`
- `backend/app/web/routes.py`
- `backend/app/web/control_panel_queries.py`
- control panel route tests

### Increment 7.1: Add Tournament Tab

Work:

- Add top-level tab.
- Add partial route.
- Add empty state when no generation run is available.

Acceptance criteria:

- Tournament tab loads without affecting existing tabs.
- Existing control panel tests pass.

### Increment 7.2: Add Submission Form

Work:

- Six student groups.
- Six team ID fields per group.
- Validation feedback.

Acceptance criteria:

- Invalid team IDs show field-level errors.
- Valid submissions can be saved.

### Increment 7.3: Add Monte Carlo Controls

Work:

- Select source generation run.
- Select source batch.
- Select tournament date.
- Set iteration count.
- Set seed.
- Start Monte Carlo run.

Acceptance criteria:

- Monte Carlo run can be started from UI.
- Progress/status is visible.
- Results appear after completion.

### Increment 7.4: Add Results Views

Display:

- division standings
- championship probabilities
- medal probabilities
- student leaderboard
- portfolio summaries

Acceptance criteria:

- Results are readable without exposing hidden formulas.
- Duplicate-team credit is visible and understandable.

### Increment 7.5: Add Official Run Display

Display:

- official division winners
- official match results
- official game results
- final group leaderboard

Acceptance criteria:

- Official live tournament can be run and displayed from the control panel.
- Official match/game details come from tournament-specific result tables.

## Increment 8: Performance And Hardening

Goal: optimize only after correctness is stable.

### Increment 8.1: Benchmark MVP Workload

Benchmark:

- 6 country/division tournaments
- up to 6 unique teams per country/division
- 10,000 Monte Carlo iterations

Acceptance criteria:

- Results complete comfortably on instructor hardware.
- Runtime is measured and documented.

### Increment 8.2: Optimize Simulation Loop

Work:

- Avoid ORM inside Monte Carlo loops.
- Preload all team features.
- Keep tournament state in compact DTOs.
- Avoid per-iteration allocation hotspots where practical.

Acceptance criteria:

- Monte Carlo loop remains deterministic after optimization.
- Test suite still passes.

### Increment 8.3: Stress-Test Future Workload

Benchmark:

- up to 36 unique teams per country/division
- 6 country/division tournaments
- 10,000 Monte Carlo iterations

Acceptance criteria:

- Identify bottlenecks before expanding classroom format.
- Decide whether further optimization is required before supporting larger
  tournament fields.

## Test Gates

Before merging team country support:

- ORM consistency tests pass.
- Team generator tests pass.
- Student projection tests pass.
- `backend/schema.sql` is regenerated from ORM metadata.

Before merging shared outcome logic:

- Existing monthly match generator tests pass.
- Hidden performance bias tests pass.
- New pure outcome tests pass.

Before merging tournament engine:

- In-memory round-robin tests pass.
- Tiebreak tests pass.
- Scoring tests pass.
- Monte Carlo determinism tests pass.

Before merging persistence:

- ORM consistency tests pass.
- Projection coverage tests pass.
- Schema expectations include all new tables.
- Tournament persistence tests pass.

Before merging UI:

- Route tests pass.
- Existing control panel tests pass.
- Manual smoke test confirms tab loading, validation, Monte Carlo run, official
  run, and results display.

## Runtime And Data Integrity Risks

- Cross-country team support changes core team formation behavior and may affect
  realism metrics.
- Team active-as-of logic must use lifecycle history where available to avoid
  reintroducing mutable-state audit defects.
- Shared outcome extraction can accidentally change monthly match generation if
  not regression-tested carefully.
- Persisting every Monte Carlo trial match would create unnecessary data volume.
- Exposing `chemistry_score` or `persistence_probability` would weaken the
  student challenge.
- Running tournament jobs concurrently with destructive seed/generation workflows
  could invalidate source data while results are being computed.

## Open Implementation Questions

- Should `teams.country_code` be nullable for legacy generated data, or should a
  backfill/default strategy be implemented immediately?
- Should tournament events be editable after official results are generated, or
  locked once an official run exists?
- Should instructor users be able to run multiple Monte Carlo analyses for the
  same event with different seeds and iteration counts?
- Should official live tournament be allowed to rerun, or should rerun require
  creating a new official simulation run?
- Should tournament result summaries be exportable as an instructor-only package
  separate from the student dataset?

## Definition Of MVP Done

- Teams persist country and cross-country teams are prohibited.
- Student-facing team export includes country and omits chemistry/persistence.
- Tournament engine runs six country/division round robins in memory.
- Tournament engine uses shared hidden-bias match/game outcome semantics.
- Submissions validate country, division, active status, and rating availability.
- Monte Carlo run persists aggregate team and group results.
- Official run persists complete match and game results.
- Control panel can validate submissions, run Monte Carlo, run official
  tournament, and display results.
- No tournament simulation output is written to monthly generation match/game or
  rating tables.
