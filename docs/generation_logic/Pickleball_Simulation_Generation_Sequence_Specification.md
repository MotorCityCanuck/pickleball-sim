**Generation Sequence Specification**

*Pickleball Simulation Platform - Codex Build Specification*

# 1. Document Purpose

This document defines the authoritative generation and orchestration
sequence for the pickleball simulation platform. It is intended to guide
Codex implementation of the end-to-end pipeline, monthly batch
processor, retry behavior, validation gates, and export flow.

# 2. Execution Model

- The platform generates an initial population and then processes every
  period, including the first historical year, as monthly batches.

- Monthly batches include configurable new player registration and
  monthly match/game generation.

- The default player growth assumption is 2 percent per month, but this
  must remain configurable.

- Ratings and confidence are stored as historical assessment records
  keyed by player_id and effective date.

- All generation steps must be reproducible using master_seed,
  monthly_batch_id, and module-specific derived seeds.

- Noise is mandatory in match scheduling, matchmaking, scoring, and
  selected distribution steps to reduce unrealistic determinism.

# 3. High-Level Sequence Overview

1.  Initialize run and load configuration.

2.  Prepare database schema and reference data.

3.  Generate or load regions and regional weighting.

4.  Generate clubs by region.

5.  Generate initial player population or monthly new player
    registration.

6.  Assign names, demographics, birthdates, regions, and clubs.

7.  Initialize or update rating and confidence history.

8.  Create teams with cross-month consistency rules.

9.  Schedule monthly matches across calendar days with weekend
    concentration bias.

10. Pair teams into matches using match type, rating proximity,
    region/club proximity, and noise.

11. Generate games and scores per match.

12. Apply game outcomes to ratings and confidence chronologically.

13. Validate data quality and invariants.

14. Export configured datasets to Parquet and produce manifests.

15. Finalize batch status and audit report.

# 4. Batch State Machine

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **pending**                         Batch row exists but no generation
                                      has started.

  **running**                         At least one generation step is
                                      executing.

  **validating**                      Generation is complete and
                                      validation gates are running.

  **exporting**                       Validation has passed required
                                      thresholds and export is in
                                      progress.

  **completed**                       All required generation,
                                      validation, export, and audit steps
                                      completed successfully.

  **failed**                          A blocker failure occurred. The
                                      batch must include failed_step,
                                      error_class, error_message, and
                                      diagnostic artifact references.

  **superseded**                      Optional status for a batch
                                      intentionally replaced by a later
                                      rerun when destructive rerun is
                                      permitted.
  -----------------------------------------------------------------------

# 5. Detailed Generation Sequence

## 1. Create Simulation Run

**Purpose:** Create the parent simulation_run record and establish
run-level seed, version, target scale, and output directory.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Inputs**                          run name; master seed; environment;
                                      initial player count

  **Outputs**                         simulation_run_id; run audit row

  **Must run after**                  Start of workflow

  **Success criteria**                Run status is initialized and
                                      master seed is recorded.
  -----------------------------------------------------------------------

### Validation Gates

- simulation_run_id is unique.

- Master seed is non-null.

- Output directory is writable.

## 2. Load and Validate Configuration

**Purpose:** Load all configuration sources, apply defaults, validate
ranges, and freeze the effective configuration for the run.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Inputs**                          configuration profile version;
                                      optional configuration file;
                                      optional UI overrides; environment
                                      variables

  **Outputs**                         effective SimulationConfig;
                                      configuration audit report

  **Must run after**                  Create Simulation Run

  **Success criteria**                Configuration is valid and the
                                      resolved effective payload is
                                      persisted to
                                      generation_runs.parameter_snapshot.
  -----------------------------------------------------------------------

### Validation Gates

- All probabilities are 0 through 1.

- All required keys exist.

- Defaults and overrides are recorded.

## 3. Prepare Schema

**Purpose:** Recreate or verify the development schema from ORM metadata and
confirm the schema matches the application code.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Inputs**                          database URL; SQLAlchemy ORM metadata

  **Outputs**                         current schema; schema audit

  **Must run after**                  Load and Validate Configuration

  **Success criteria**                Database schema is current before
                                      any generation writes occur.
  -----------------------------------------------------------------------

### Validation Gates

- Schema version equals expected version.

- Core tables are available.

- Migrations are not partially applied.

## 4. Load Reference Data

**Purpose:** Load or verify census, regional population, first-name
frequency, last-name frequency, and optional club-name seed data.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Inputs**                          reference files; schema mapping
                                      config

  **Outputs**                         reference tables; reference load
                                      metrics

  **Must run after**                  Prepare Schema and Migrations

  **Success criteria**                All required reference domains are
                                      available for generation.
  -----------------------------------------------------------------------

### Validation Gates

- Required columns exist.

- Frequency values are positive.

- Country/state/province codes are normalized.

## 5. Generate Regional Allocation

**Purpose:** Calculate how many players belong in each region using
population, configured competitiveness, and allocation noise.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Inputs**                          target player count; region
                                      population table; competitiveness
                                      multipliers

  **Outputs**                         regional_allocation records

  **Must run after**                  Load Reference Data

  **Success criteria**                Regional player targets reconcile
                                      exactly to the target population.
  -----------------------------------------------------------------------

### Validation Gates

- Total allocation equals target player count.

- No region has negative allocation.

- Small-region minimums are honored or flagged.

## 6. Generate Regional Clubs

**Purpose:** Generate clubs for every region using configured club
counts, club type weights, size distributions, naming rules, and noise.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Inputs**                          regional_allocation records; club
                                      naming config

  **Outputs**                         club records; club size targets

  **Must run after**                  Generate Regional Allocation

  **Success criteria**                Every region has enough club
                                      capacity for assignment.
  -----------------------------------------------------------------------

### Validation Gates

- No duplicate club name within a region.

- All clubs have valid type and region.

- Capacity is within tolerance.

## 7. Open Monthly Batch

**Purpose:** Create a monthly_batch record for the month being processed
and place it into running status.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Inputs**                          simulation_run_id; batch_month;
                                      previous batch status

  **Outputs**                         monthly_batch_id; batch audit row

  **Must run after**                  Generate Regional Clubs for initial
                                      run OR prior completed batch for
                                      subsequent months

  **Success criteria**                Batch is registered and eligible
                                      for processing.
  -----------------------------------------------------------------------

### Validation Gates

- Batch month is unique per run.

- Previous required batch is completed.

- Rerun policy is enforced.

## 8. Generate New Player Registration Scope

**Purpose:** Determine new player count for the month, defaulting to
configured monthly growth such as 2 percent, and generate player shells
for new entrants.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Inputs**                          active player count; monthly growth
                                      rate; regional allocation strategy

  **Outputs**                         new player registration records;
                                      player shell records

  **Must run after**                  Open Monthly Batch

  **Success criteria**                New player count and regional
                                      distribution are calculated.
  -----------------------------------------------------------------------

### Validation Gates

- New count matches configured growth within rounding rule.

- New player ids are unique.

- New players are assigned to valid regions.

## 9. Assign Names and Demographics

**Purpose:** Assign first names, last names, gender, birthdate, and
stable demographic fields to new players using weighted reference data.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Inputs**                          player shell records; name
                                      frequencies; birthdate distribution

  **Outputs**                         complete player records

  **Must run after**                  Generate New Player Registration
                                      Scope

  **Success criteria**                New players have complete
                                      non-rating identity attributes.
  -----------------------------------------------------------------------

### Validation Gates

- Birthdates produce ages within configured range.

- Name fallback usage is recorded.

- Gender values align to configured domain.

## 10. Assign Clubs to Players

**Purpose:** Assign affiliated players to one or more clubs using
region, club size, type, capacity, and randomized preference noise.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Inputs**                          new player records; clubs; club
                                      assignment config

  **Outputs**                         club_memberships records

  **Must run after**                  Assign Names and Demographics

  **Success criteria**                Affiliated players have valid
                                      active club memberships;
                                      configured unaffiliated players
                                      remain without memberships.
  -----------------------------------------------------------------------

### Validation Gates

- Exactly one primary active club membership per affiliated player.

- Some players may remain unaffiliated according to
  `unaffiliated_player_rate` or because their region has no eligible
  clubs.

- A configured minority of affiliated players may hold secondary
  memberships, bounded by
  `max_club_memberships_per_player`.

- No invalid cross-region assignment.

- Club size distribution remains within tolerance.

## 11. Initialize New Player Ratings and Confidence

**Purpose:** Create initial rating history records for new players,
using configured rating distribution, elite-tail controls, and regional
competitiveness.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Inputs**                          new players; regional
                                      competitiveness; rating config

  **Outputs**                         player_rating_history records

  **Must run after**                  Assign Clubs to Players

  **Success criteria**                Each new player has a current
                                      rating and confidence record.
  -----------------------------------------------------------------------

### Validation Gates

- Rating bounds are enforced.

- Confidence bounds are enforced.

- Rating effective date belongs to batch month.

- Initial ratings are persisted in `player_rating_history`, not in
  `players` or `player_assessment_history`.

## 12. Build Monthly Eligible Player Pool

**Purpose:** Determine which players are active and eligible for team
formation in the current month.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Inputs**                          active players; club memberships;
                                      rating snapshots; eligibility
                                      config

  **Outputs**                         eligible player pool

  **Must run after**                  Initialize New Player Ratings and
                                      Confidence

  **Success criteria**                Eligible pool is complete and
                                      filtered by configured rules.
  -----------------------------------------------------------------------

### Validation Gates

- Inactive players are excluded.

- Missing rating snapshots are blockers.

- Eligibility counts are logged by region and club.

## 13. Determine Teams as of Batch Month

**Purpose:** Determine the valid doubles team set as of the monthly batch
month, preserving prior partnerships when configured, dissolving or
marking dormant a configured minority of teams, reactivating dormant
teams when partnerships reform, and creating new teams as required.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Inputs**                          eligible player pool; prior team
                                      and membership history as of batch
                                      month; match type config

  **Outputs**                         team records; team membership
                                      records with joined/left dates;
                                      team lifecycle metrics

  **Must run after**                  Build Monthly Eligible Player Pool

  **Success criteria**                Teams are valid for the batch month
                                      and match type scope.
  -----------------------------------------------------------------------

### Validation Gates

- Every team has exactly two players.

- No duplicate active team membership in same scope.

- Active teams and memberships are evaluated using point-in-time
  date-window logic.

- Team persistence rate is measured.

- Team dissolution, dormancy, reactivation, and newly created team counts
  are logged.

## 14. Create Monthly Match Schedule

**Purpose:** Spread monthly matches across dates in the month with a
configurable concentration bias toward weekend dates.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Inputs**                          active teams; batch calendar; match
                                      frequency config

  **Outputs**                         match schedule shells

  **Must run after**                  Determine Teams as of Batch Month

  **Success criteria**                Match shell dates are distributed
                                      across the month.
  -----------------------------------------------------------------------

### Validation Gates

- No date is outside batch month.

- Weekend share reflects configured bias within tolerance.

- Team daily match limits are enforced.

## 15. Pair Teams into Matches

**Purpose:** Assign teams to scheduled match shells using skill
proximity, locality, match type compatibility, rematch penalties, and
controlled noise.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Inputs**                          match schedule shells; teams;
                                      rating snapshots

  **Outputs**                         match records

  **Must run after**                  Create Monthly Match Schedule

  **Success criteria**                Each scheduled match has two
                                      compatible teams.
  -----------------------------------------------------------------------

### Validation Gates

- No team plays itself.

- Match type compatibility is enforced.

- Repeated opponent limits are enforced or warned.

## 16. Generate Games and Scores

**Purpose:** Generate configured games per match, including plausible
score lines, rating-derived expected scores, outcomes, win-by-two
extensions, upset probability, and score noise.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Inputs**                          match records; team ratings; game
                                      config

  **Outputs**                         game records; expected score metrics;
                                      actual score metrics

  **Must run after**                  Pair Teams into Matches

  **Success criteria**                Each match has complete game rows
                                      and legal scores.
  -----------------------------------------------------------------------

### Validation Gates

- Games per match matches config or allowed range.

- Scores are legal.

- Winner and score are consistent.

- Expected raw scores and expected score share are populated for each
  game before actual score noise is applied.

## 17. Apply Rating Updates Chronologically

**Purpose:** Process match results by date and sequence, calculate
expected results, apply actual outcomes, append rating history, and write
per-player rating update audit rows.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Inputs**                          match games; match teams; match
                                      players; prior ratings; rating
                                      update config

  **Outputs**                         player_rating_history rows;
                                      ratings_update_log rows

  **Must run after**                  Generate Games and Scores

  **Success criteria**                Ratings reflect all completed
                                      matches in chronological order,
                                      with one audit row per player per
                                      match.
  -----------------------------------------------------------------------

### Validation Gates

- No historical rating row is overwritten.

- Rating deltas are within tolerance.

- Missing prior rating is blocker.

- `ratings_update_log` row count equals the number of player-match
  participant rows processed.

- `rating_delta` equals `rating_after - rating_before` within numeric
  rounding tolerance.

## 18. Update Confidence History

**Purpose:** Recalculate confidence based on match count, recency,
opponent quality, volatility, and inactivity effects.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Inputs**                          rating history; match history;
                                      confidence config

  **Outputs**                         confidence history updates

  **Must run after**                  Apply Rating Updates
                                      Chronologically

  **Success criteria**                Confidence records are current
                                      through the batch month.
  -----------------------------------------------------------------------

### Validation Gates

- Confidence is bounded.

- New and inactive players behave according to rules.

- Confidence is not stored in player table.

## 19. Run Validation Gates

**Purpose:** Run referential, distributional, count, date, rating, team,
match, game, and export-readiness validations.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Inputs**                          monthly_batch_id; validation
                                      catalog

  **Outputs**                         validation results; validation
                                      summary

  **Must run after**                  Update Confidence History

  **Success criteria**                No blocker validation defects
                                      remain.
  -----------------------------------------------------------------------

### Validation Gates

- All generated rows reference valid parent rows.

- Counts reconcile to batch metrics.

- No hard invariant is violated.

## 20. Export Parquet Artifacts

**Purpose:** Export configured datasets to Parquet, partition where
appropriate, and generate export manifests with schema and checksum
metadata.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Inputs**                          validated tables; export config

  **Outputs**                         Parquet files; ExportManifest

  **Must run after**                  Run Validation Gates

  **Success criteria**                Export files and manifest are
                                      complete and internally consistent.
  -----------------------------------------------------------------------

### Validation Gates

- Export row counts equal database counts.

- Checksums are present.

- Schema hashes are recorded.

## 21. Finalize Batch and Audit Report

**Purpose:** Set batch status to completed, write summary metrics, and
preserve audit artifacts for review and debugging.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Inputs**                          validation summary; export
                                      manifest; module results

  **Outputs**                         completed monthly batch; audit
                                      report

  **Must run after**                  Export Parquet Artifacts

  **Success criteria**                Batch is complete, auditable, and
                                      ready for downstream use.
  -----------------------------------------------------------------------

### Validation Gates

- Completed status only after export success.

- All module results are attached.

- Elapsed time and key metrics are recorded.

# 6. Retry and Rerun Rules

- A failed batch may be retried from the failed step only if prior steps
  are immutable and validation confirms their outputs are complete.

- If destructive rerun is enabled, prior generated rows for the
  monthly_batch_id must be removed or superseded before regeneration.

- A completed batch should not be rerun silently; require explicit rerun
  mode.

- Transient database and filesystem failures may be retried according to
  configuration.

- Validation blockers require data/configuration correction rather than
  blind retry.

- Every retry must append an audit entry identifying prior status,
  requested action, timestamp, and result.

# 7. Noise and Determinism Rules

- Hard constraints must never be violated by noise.

- Noise should be applied through seeded random streams named by module
  and entity scope.

- Weekend scheduling bias changes probability weights but should not
  force all matches to weekends.

- Matchmaking noise should allow rating mismatches, rematches within
  tolerance, and upsets without destroying realism.

- Score noise should be applied after expected performance calculation
  and then corrected to legal score formats.

- Same master seed, same config, and same inputs must reproduce the same
  outputs.

# 8. Minimum End-to-End Test Scenarios

- Tiny smoke test: 2 regions, 4 clubs, 40 players, 1 month, 1 game per
  match.

- Historical run test: 12 monthly batches with new players each month
  and rating history growth.

- Weekend bias test: verify match dates concentrate on weekends without
  eliminating weekdays.

- Team continuity test: verify prior teams are reused at configured
  persistence rate.

- Rerun test: rerunning a failed batch does not duplicate players,
  teams, matches, games, or assessment history.

- Validation failure test: intentionally remove a rating snapshot and
  confirm validation blocks completion.

- Export test: Parquet row counts equal database row counts and manifest
  checksums are present.

# 9. Codex Implementation Guidance

- Implement the orchestrator as a clear state machine rather than a
  loose script.

- Implement each sequence step as an independently testable service with
  a typed input and ModuleResult output.

- Build a small deterministic fixture first, then scale to full-size
  generation.

- Keep generated data and reference data separate.

- Make distribution tolerances configurable for tests versus
  production-scale runs.

- Create command-line entry points for init-run, process-month,
  validate-batch, export-batch, and run-all-history.
