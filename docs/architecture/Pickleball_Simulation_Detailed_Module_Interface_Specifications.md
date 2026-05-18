**Detailed Module Interface Specifications**

*Pickleball Simulation Platform - Codex Build Specification*

# 1. Document Purpose

This document defines the module-level contracts Codex should use when
implementing the pickleball simulation platform. It converts the
architecture, database design, monthly batch, team formation, club
assignment, player generation, and match/game identification logic into
explicit implementation boundaries.

# 2. Global Contract Principles

- Every generator module must accept an explicit configuration object
  and random seed context; no module may use unmanaged global
  randomness.

- Every write operation must be idempotent by monthly_batch_id or
  simulation_run_id unless explicitly documented as a destructive
  rebuild step.

- Every persisted table must support auditability through created_at,
  updated_at where appropriate, source_batch_id where applicable, and
  deterministic natural keys where needed.

- All modules must return a structured result object containing status,
  inserted_count, updated_count, skipped_count, warning_count,
  error_count, elapsed_seconds, and artifact locations.

- Modules should fail fast on schema/configuration errors but collect
  row-level validation defects into validation tables or structured logs
  when processing batch input files.

- All interfaces must separate pure calculation from persistence so that
  the calculation layer can be unit tested without PostgreSQL.

# 3. Shared Data Structures

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **SimulationConfig**                Typed configuration object resolved
                                      from defaults, database-backed
                                      configuration profile versions,
                                      YAML/JSON imports, environment
                                      variables, UI overrides, and command
                                      arguments. Contains
                                      generation scale, regional
                                      weighting, club distribution,
                                      rating ranges, noise settings,
                                      scheduling rules, export settings,
                                      and validation tolerances.

  **RandomContext**                   Contains master_seed, derived_seed,
                                      module_name, monthly_batch_id, and
                                      deterministic stream identifiers.
                                      All random draws must be generated
                                      through this object.

  **BatchContext**                    Contains simulation_run_id,
                                      monthly_batch_id, batch_month,
                                      previous_month, execution_mode,
                                      input file locations, and target
                                      schema.

  **ModuleResult**                    Uniform return object: module_name,
                                      status, inserted_count,
                                      updated_count, skipped_count,
                                      warnings, errors, metrics,
                                      started_at, completed_at,
                                      elapsed_seconds.

  **ValidationResult**                Structured result containing
                                      validation rule id, severity,
                                      entity type, entity id, field name,
                                      observed value, expected rule, and
                                      remediation hint.

  **ExportManifest**                  Manifest for generated Parquet/CSV
                                      artifacts containing file path, row
                                      count, schema hash, source tables,
                                      batch id, generation timestamp, and
                                      checksum.
  -----------------------------------------------------------------------

# 4. Repository-Level Module Map

- app/config: configuration loading, validation, and defaults.

- app/db: SQLAlchemy engine/session management, ORM schema utilities,
  repository classes, and transaction utilities.

- app/domain: pure domain calculations such as expected score, rating
  deltas, confidence calculations, and distribution sampling.

- app/generators: region, club, player, name, team, schedule, match,
  game, and rating generation modules.

- app/batches: monthly orchestration, new player registration ingestion,
  match-result ingestion, retry behavior, and batch status tracking.

- app/validation: invariant checks, data quality reports, and test
  fixtures.

- app/export: Parquet export, export manifests, and downstream student
  data packages.

- app/ui: lightweight web control surface for generation parameters,
  file picking, and batch execution controls.

# 5. Detailed Module Contracts

## configuration_loader

**Purpose:** Loads configuration from `configuration_profile_versions`
JSONB payloads and optional file or runtime overrides, applies defaults,
validates ranges, and exposes an immutable SimulationConfig to all downstream
modules.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Primary inputs**                  configuration_profile_id or version
                                      id; optional config_file_path;
                                      environment_name; optional override
                                      dictionary

  **Primary outputs**                 SimulationConfig; configuration
                                      validation report; frozen
                                      generation_runs.parameter_snapshot

  **Dependencies**                    None

  **Configuration keys**              master_seed;
                                      monthly_player_growth_rate;
                                      rating_noise_std_dev;
                                      weekend_concentration_bias;
                                      games_per_match
  -----------------------------------------------------------------------

### Required Behavior

- Reject missing required config keys before generation begins.

- Validate numeric ranges including probabilities between 0 and 1,
  positive counts, and rating bounds.

- Expose both effective configuration and source configuration for audit
  comparison.

- Persist the resolved effective configuration to
  `generation_runs.parameter_snapshot` before downstream generation starts.

### Failure Handling and Logging

- Raise ConfigValidationError for invalid schema or unsafe defaults.

- Log all overridden values and all defaulted values.

### Minimum Tests

- Invalid probability values fail validation.

- Same config file produces same normalized SimulationConfig.

- Unknown config keys generate warnings rather than silent acceptance.

## database_session_manager

**Purpose:** Owns SQLAlchemy engine creation, transaction boundaries,
retry rules, and safe unit-of-work handling for batch processing.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Primary inputs**                  database_url; execution_mode;
                                      transaction scope

  **Primary outputs**                 database session; transaction
                                      result; rollback/commit status

  **Dependencies**                    configuration_loader

  **Configuration keys**              db_pool_size;
                                      statement_timeout_seconds;
                                      retry_count
  -----------------------------------------------------------------------

### Required Behavior

- Open one explicit transaction for each bounded module operation unless
  orchestration requests a larger unit of work.

- Never leave a partially committed monthly batch in completed status.

- Use repositories rather than direct ad hoc SQL in generation modules.

### Failure Handling and Logging

- Rollback on exceptions and write batch error state.

- Retry only transient connection errors, not validation or integrity
  failures.

### Minimum Tests

- Rollback leaves no partial rows for a failed module.

- Retry count is honored.

- Session closes after success and failure.

## reference_data_loader

**Purpose:** Loads region, census, name frequency, and baseline lookup
data required for generation.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Primary inputs**                  census files; name frequency files;
                                      region mapping files

  **Primary outputs**                 loaded reference tables; load audit
                                      metrics

  **Dependencies**                    configuration_loader;
                                      database_session_manager

  **Configuration keys**              reference_data_directory;
                                      allow_reference_reload;
                                      state_province_mapping_strategy
  -----------------------------------------------------------------------

### Required Behavior

- Validate required columns before inserts.

- Normalize state/province/country codes consistently.

- Preserve raw frequency values and derived normalized probabilities.

### Failure Handling and Logging

- Reject malformed files.

- Quarantine invalid rows with clear validation messages.

### Minimum Tests

- Frequency totals reconcile to expected totals.

- Malformed row is quarantined.

- Reload mode replaces only intended reference-data scope.

## regional_distribution_engine

**Purpose:** Computes target player counts and relative competitive
strength by region using population, configured multipliers, and
controlled noise.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Primary inputs**                  region population table; target
                                      total player count; competitiveness
                                      multipliers

  **Primary outputs**                 regional allocation rows; regional
                                      target metrics

  **Dependencies**                    reference_data_loader

  **Configuration keys**              region_population_weight;
                                      competitiveness_noise_sigma;
                                      min_players_per_region
  -----------------------------------------------------------------------

### Required Behavior

- Allocate all players without losing count through rounding.

- Apply noise without allowing negative allocation.

- Persist calculation inputs for audit reproducibility.

### Failure Handling and Logging

- Warn when small regions are below configured minimums.

- Fail if allocation cannot reconcile to target count.

### Minimum Tests

- Allocated count equals requested total.

- Same seed yields same allocations.

- Different seeds vary within configured tolerance.

## club_generator

**Purpose:** Creates realistic clubs by region with configurable club
counts, club types, club size distributions, and regional naming
patterns.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Primary inputs**                  regions; club name source list or
                                      naming rules; club distribution
                                      config

  **Primary outputs**                 clubs table rows; club
                                      capacity/size targets

  **Dependencies**                    regional_distribution_engine

  **Configuration keys**              clubs_per_region_strategy;
                                      club_size_distribution;
                                      club_type_weights; club_name_noise
  -----------------------------------------------------------------------

### Required Behavior

- Generate enough clubs to support player assignments without extreme
  overcrowding unless intentionally configured.

- Assign club types such as public park, private club, community center,
  resort, university, and municipal recreation.

- Preserve regional specificity in names and state/province/country
  fields.

### Failure Handling and Logging

- Deduplicate club names within region; append controlled suffix only
  when needed.

- Warn when generated capacity is materially below regional player
  allocation.

### Minimum Tests

- No duplicate club names within a region.

- Club sizes follow intended distribution.

- All generated clubs belong to valid regions.

## player_core_generator

**Purpose:** Creates base player records excluding time-varying ratings
and assessments. Includes player id, region, club, gender, birthdate,
and stable demographic attributes.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Primary inputs**                  regional allocations; club table;
                                      age distribution; gender
                                      distribution

  **Primary outputs**                 players table rows;
                                      player_generation_metrics

  **Dependencies**                    regional_distribution_engine;
                                      club_assignment_engine;
                                      name_assignment_engine

  **Configuration keys**              player_count; age_min; age_max;
                                      gender_weights;
                                      monthly_player_growth_rate
  -----------------------------------------------------------------------

### Required Behavior

- Use birthdate rather than age in player table.

- Do not store ratings or confidence in the player table; ratings belong
  in date-keyed assessment history.

- New players introduced in monthly batches must receive unique stable
  player ids.

### Failure Handling and Logging

- Fail on duplicate generated player ids.

- Warn if region/club distribution drifts outside configured tolerance.

### Minimum Tests

- All players have valid birthdates.

- All players assigned to valid region and club.

- Monthly growth creates expected 2 percent default player growth when
  configured.

## name_assignment_engine

**Purpose:** Assigns realistic first and last names using
census/SSA-style frequency data aligned to region, gender, and birth
year where available.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Primary inputs**                  player shell records; first-name
                                      frequency table; last-name
                                      frequency table

  **Primary outputs**                 named player rows; name assignment
                                      audit metrics

  **Dependencies**                    reference_data_loader

  **Configuration keys**              name_region_fallback_order;
                                      name_gender_mapping;
                                      name_year_bucket_size
  -----------------------------------------------------------------------

### Required Behavior

- Use weighted random sampling from normalized frequencies.

- Fallback from region-specific to country-level distributions when
  sparse.

- Do not require names to be unique.

### Failure Handling and Logging

- Warn when fallback distributions are used.

- Fail if no valid name distribution exists for a required country.

### Minimum Tests

- Name frequencies approximate source distribution.

- Fallback logic is deterministic under seed.

- Birth-year-specific first names are selected when available.

## club_assignment_engine

**Purpose:** Assigns players to clubs after base player creation using
region-specific clubs, club size, club type, distance/fit proxies, and
random noise.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Primary inputs**                  players without clubs or assignment
                                      refresh scope; club table; regional
                                      constraints

  **Primary outputs**                 player_club_assignment rows; club
                                      membership metrics

  **Dependencies**                    club_generator;
                                      player_core_generator

  **Configuration keys**              club_assignment_noise;
                                      club_size_power_law_alpha;
                                      max_club_fill_ratio;
                                      unaffiliated_player_rate;
                                      multi_club_membership_rate;
                                      min_club_memberships_per_affiliated_player;
                                      max_club_memberships_per_player;
                                      secondary_membership_same_region_rate
  -----------------------------------------------------------------------

### Required Behavior

- Perform assignment after player table creation so player identity
  exists before club membership is persisted.

- Respect region boundaries unless cross-region assignment is explicitly
  enabled.

- Bias assignments toward larger clubs but include noise to prevent
  deterministic sorting.

- Leave the configured share of players unaffiliated with no
  `club_memberships` rows.

- Assign exactly one active primary membership to affiliated players.

- Assign secondary memberships only to the configured multi-club share,
  bounded by the configured minimum and maximum membership counts.

### Failure Handling and Logging

- Warn when clubs in a region are exhausted.

- Fail if a player cannot be assigned under mandatory constraints.

### Minimum Tests

- Every active player has exactly one active club assignment.

- Large clubs receive proportionally more players.

- No assignment to a club outside permitted region.

## rating_initialization_engine

**Purpose:** Creates initial rating and confidence records for new
players using distributions, regional competitiveness multipliers, and
optional experience proxies.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Primary inputs**                  new player rows; regional
                                      competitiveness metrics; rating
                                      config

  **Primary outputs**                 player_rating_history rows

  **Dependencies**                    player_core_generator;
                                      regional_distribution_engine

  **Configuration keys**              initial_rating_mean;
                                      initial_rating_std_dev; rating_min;
                                      rating_max;
                                      initial_rating_elite_tail_rate;
                                      initial_rating_elite_min;
                                      initial_rating_elite_max;
                                      initial_confidence_score
  -----------------------------------------------------------------------

### Required Behavior

- Persist ratings in `player_rating_history`, not in `players` or
  `player_assessment_history`.

- Bound ratings to configured min/max.

- Use regional competitiveness to avoid interpreting equal raw ratings
  as equal cross-region skill when configured.

- Ratings should mostly follow the configured initial normal
  distribution, with a small configurable elite tail to represent rare
  highly rated players.

- Initial player confidence should use the configured
  `initial_confidence_score`.

### Failure Handling and Logging

- Warn on excessive clipping at min/max bounds.

- Fail when rating date is missing.

### Minimum Tests

- All new players receive an initial rating history record.

- Ratings are in configured bounds.

- Same seed reproduces exact initial ratings.

## team_assignment_engine

**Purpose:** Determines doubles teams as of a monthly batch point in time,
while allowing configurable churn, partner preference, skill balance,
gender/match type constraints, reactivation of dormant partnerships, and
non-deterministic variation.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Primary inputs**                  eligible player pool; prior team
                                      history as of batch month; match
                                      type config; monthly_batch_id

  **Primary outputs**                 team rows; team membership rows
                                      with joined/left dates; team
                                      continuity metrics

  **Dependencies**                    player_core_generator;
                                      rating_history_repository

  **Configuration keys**              target_team_count;
                                      player_team_participation_rate;
                                      multi_team_player_rate;
                                      max_active_teams_per_player;
                                      same_club_team_rate;
                                      same_region_team_rate;
                                      rating_gap_mean;
                                      rating_gap_std_dev;
                                      rating_gap_max;
                                      team_type_weights;
                                      team_persistence_probability_recreational;
                                      team_persistence_probability_competitive;
                                      dormant_team_reactivation_rate;
                                      retired_team_rate_on_dissolution;
                                      monthly_team_dissolution_rate;
                                      team_chemistry_weight;
                                      team_skill_balance_weight;
                                      team_club_proximity_weight;
                                      team_region_proximity_weight;
                                      team_prior_partnership_weight;
                                      team_noise_factor
  -----------------------------------------------------------------------

### Required Behavior

- Support men pairs, women pairs, mixed pairs, open pairs, and
  configured custom match types.

- Use `player_team_participation_rate` to determine how many eligible
  players participate in active teams for the batch unless an explicit
  `target_team_count` is provided.

- Use `team_type_weights` to allocate newly created teams across team
  types.

- Prefer same-club and same-region pairings according to
  `same_club_team_rate` and `same_region_team_rate`.

- Keep partner rating gaps within configured limits using
  `rating_gap_mean`, `rating_gap_std_dev`, and `rating_gap_max`.

- Use prior team history to preserve consistency across months unless
  churn is configured.

- Determine active teams and active memberships using point-in-time
  `formation_date`, `dissolution_date`, `joined_date`, and `left_date`
  semantics for the current batch month.

- Evaluate existing active teams before creating new teams.

- Dissolve or mark dormant a configured minority of teams during each
  monthly batch, then create replacement teams and teams for newly
  eligible players.

- Reactivate dormant teams when the same player pair reforms instead of
  creating duplicate team identities.

- Ensure no player appears on more than one active team in the same
  scheduling scope unless explicitly configured.

### Failure Handling and Logging

- Quarantine impossible team constraints rather than creating invalid
  teams.

- Warn when leftover players cannot be paired.

### Minimum Tests

- Prior teams persist at configured rate.

- Dormant teams can reform in a later batch with the same team identity.

- Point-in-time queries exclude teams and memberships that are not active
  for the batch month.

- No team has more or fewer than two players.

- Match type constraints are enforced.

## match_scheduler

**Purpose:** Schedules monthly matches across the days of the month with
configurable frequency, weekend concentration bias, regional/club
constraints, and controlled noise.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Primary inputs**                  active teams; batch_month; calendar
                                      config

  **Primary outputs**                 scheduled match shells; date
                                      distribution metrics

  **Dependencies**                    team_assignment_engine

  **Configuration keys**              matches_per_team_per_month;
                                      weekend_concentration_bias;
                                      holiday_bias; weekday_noise;
                                      match_type_weights
  -----------------------------------------------------------------------

### Required Behavior

- Distribute matches across calendar days rather than a single
  processing date.

- Bias toward Friday/Saturday/Sunday where configured while retaining
  weekday matches.

- Avoid overscheduling teams beyond configured max daily matches.

### Failure Handling and Logging

- Warn if configured frequency cannot be achieved.

- Fail on invalid date ranges.

### Minimum Tests

- Weekend dates receive higher match concentration.

- No match scheduled outside batch month.

- Team daily limits are enforced.

## matchmaking_engine

**Purpose:** Pairs teams into matches using rating proximity,
region/club proximity, match type compatibility, frequency targets, and
random perturbation.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Primary inputs**                  scheduled match shells; eligible
                                      teams; rating snapshots

  **Primary outputs**                 match rows with team_a/team_b;
                                      matchmaking metrics

  **Dependencies**                    match_scheduler;
                                      rating_history_repository

  **Configuration keys**              rating_band_width; rematch_penalty;
                                      locality_weight; matchmaking_noise
  -----------------------------------------------------------------------

### Required Behavior

- Prefer balanced matches but intentionally include mismatches according
  to noise settings.

- Avoid excessive repeated opponents within configured window.

- Respect match type compatibility.

### Failure Handling and Logging

- Warn when balanced opponents are unavailable.

- Fail if a match shell cannot be filled under strict constraints.

### Minimum Tests

- Team rating differences cluster near configured band.

- Rematch limits are enforced.

- Noise increases variance without breaking constraints.

## game_generation_engine

**Purpose:** Generates one or more games per match, simulates game-level
scores, and ties each game to a stable match id and monthly batch.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Primary inputs**                  match rows; team rating snapshots;
                                      games per match config

  **Primary outputs**                 game rows; expected score metrics;
                                      actual score metrics

  **Dependencies**                    matchmaking_engine; rating_engine

  **Configuration keys**              games_per_match; score_noise;
                                      upset_probability; win_by_two_rule;
                                      win_by_two_extension_rate
  -----------------------------------------------------------------------

### Required Behavior

- Allow configurable games per match.

- Generate plausible pickleball scores and winners.

- Persist rating-derived expected score share and expected raw scores for
  both teams on each game.

- Include enough stochastic noise to reduce deterministic
  rating-to-score mapping.

- When `win_by_two_rule_enabled` is true, use
  `win_by_two_extension_rate` to control how often generated games extend
  beyond the target score before a team wins by two.

### Failure Handling and Logging

- Fail if game totals do not reconcile to configured match structure.

- Warn on excessive impossible score corrections.

### Minimum Tests

- Every match has the configured number or allowed range of games.

- Scores are legal under configured scoring rules.

- Underdogs win at non-zero configured frequency.

## rating_engine

**Purpose:** Updates player assessment history after each match/game
using expected score, actual performance, K-factor logic, confidence,
and noise controls.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Primary inputs**                  game results; prior rating
                                      snapshot; rating config

  **Primary outputs**                 new rating history records; rating
                                      movement metrics

  **Dependencies**                    game_generation_engine

  **Configuration keys**              k_factor_base; rating_noise_std_dev;
                                      confidence_weight; rating_decay
  -----------------------------------------------------------------------

### Required Behavior

- Process results in chronological order within the monthly batch.

- Compute expected score from the rating-derived game expectations, then
  apply actual score differential.

- Create new rating history records rather than mutating historical
  records.

### Failure Handling and Logging

- Fail on missing prior rating snapshots.

- Warn when rating movement exceeds configured threshold.

### Minimum Tests

- Ratings update monotonically according to wins/losses before noise.

- Chronological processing changes results compared with unordered
  processing.

- Historical records are append-only.

## confidence_engine

**Purpose:** Calculates player rating confidence based on match volume,
recency, opponent quality, score consistency, inactivity, and rating
volatility.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Primary inputs**                  player match history; rating
                                      history; confidence config

  **Primary outputs**                 confidence history records;
                                      confidence metrics

  **Dependencies**                    rating_engine

  **Configuration keys**              confidence_min; confidence_max;
                                      recency_half_life_days;
                                      match_volume_weight
  -----------------------------------------------------------------------

### Required Behavior

- Confidence generally increases with valid recent match volume.

- Confidence decays or stabilizes with inactivity according to
  configuration.

- Confidence should not be equivalent to rating.

### Failure Handling and Logging

- Warn on confidence saturation across too many players.

- Fail on missing effective dates.

### Minimum Tests

- New players begin with low confidence.

- Active players gain confidence.

- Inactive players decay under recency rules.

## monthly_batch_processor

**Purpose:** Coordinates new player registration, match generation, game
generation, rating/confidence updates, validation, export, and batch
state transitions.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Primary inputs**                  BatchContext; SimulationConfig;
                                      input files

  **Primary outputs**                 completed monthly batch; batch
                                      audit report; export manifest

  **Dependencies**                    all generator modules

  **Configuration keys**              batch_retry_policy;
                                      commit_strategy;
                                      validation_strictness
  -----------------------------------------------------------------------

### Required Behavior

- Execute the generation sequence in the authoritative order.

- Set batch status through pending, running, validating, exporting,
  completed, or failed.

- Support rerun behavior by batch id without duplicating facts.

### Failure Handling and Logging

- Rollback failed transactional steps.

- Persist failure state and diagnostic messages.

- Disallow completion if critical validation fails.

### Minimum Tests

- Rerun of completed batch is idempotent or explicitly blocked.

- Failed batch can be diagnosed from audit tables.

- Sequence cannot skip required modules.

## validation_engine

**Purpose:** Runs data-quality and invariant checks after major stages
and before export.

  ------------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- ------------------------------------
  **Primary inputs**                  database connection; batch id;
                                      validation rule catalog

  **Primary outputs**                 validation_result rows; validation
                                      summary

  **Dependencies**                    monthly_batch_processor

  **Configuration keys**              validation_strictness;
                                      allowed_warning_threshold;
                                      sample_size_for_distribution_tests
  ------------------------------------------------------------------------

### Required Behavior

- Validate referential integrity, date bounds, count reconciliation,
  uniqueness, rating bounds, team membership, match/game completeness,
  and export readiness.

- Classify findings as info, warning, error, or blocker.

- Produce machine-readable and human-readable summaries.

### Failure Handling and Logging

- Block completion on blocker-level failures.

- Log all warnings even if batch continues.

### Minimum Tests

- Known invalid fixture produces expected errors.

- Clean fixture passes all blockers.

- Validation summary counts match detail records.

## parquet_exporter

**Purpose:** Exports configured student-facing and instructor-facing
datasets to Parquet with manifests, row counts, checksums, and schema
metadata.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Primary inputs**                  batch id; export table list; output
                                      directory

  **Primary outputs**                 Parquet files; ExportManifest

  **Dependencies**                    validation_engine

  **Configuration keys**              export_directory;
                                      export_partition_strategy;
                                      export_compression_codec;
                                      export_included_table_groups;
                                      export_included_tables
  -----------------------------------------------------------------------

### Required Behavior

- Export only after validation passes required thresholds.

- Partition by month where useful.

- Record schema hash and row count for every artifact.

### Failure Handling and Logging

- Fail on filesystem errors.

- Warn on unexpectedly small or large exports.

### Minimum Tests

- Exported row count equals database count.

- Manifest checksum changes when file changes.

- Parquet schema matches expected schema.

## web_control_service

**Purpose:** Provides a lightweight local control surface for
configuration sliders, file selection, batch execution, status
monitoring, and export links.

  -----------------------------------------------------------------------
  **Field**                           **Specification**
  ----------------------------------- -----------------------------------
  **Primary inputs**                  user-selected parameters; file
                                      paths; batch actions

  **Primary outputs**                 validated config overrides; batch
                                      execution requests; status views

  **Dependencies**                    configuration_loader;
                                      monthly_batch_processor

  **Configuration keys**              ui_enabled; max_preview_rows;
                                      storage_estimator_rules
  -----------------------------------------------------------------------

### Required Behavior

- Never bypass backend validation.

- Estimate storage before execution using current parameter values.

- Expose status without requiring direct database access by students.

### Failure Handling and Logging

- Display validation errors clearly.

- Do not launch duplicate batch execution for same id.

### Minimum Tests

- UI override maps to valid config.

- Storage estimator updates when sliders change.

- Duplicate execution is blocked.

# 6. Cross-Module Invariants

- A player_id is immutable once assigned.

- A player may have many rating/confidence history rows but exactly one
  current effective row for a given assessment type and date.

- A team must contain exactly two players.

- A game must belong to exactly one match.

- A match must have exactly two teams.

- A monthly batch must not create records outside its batch month except
  permitted future export metadata.

- All generated values controlled by randomness must be reproducible
  from master seed, module name, and entity scope.

- Generated noise may change probabilities and scores but must not
  violate hard constraints.

- Every exported dataset must be traceable back to source tables and
  monthly_batch_id.

# 7. Codex Implementation Instructions

- Implement interfaces first using typed dataclasses or Pydantic models
  before implementing generation internals.

- Create unit tests for pure functions before database integration
  tests.

- Use repositories for persistence and keep generators free of direct
  SQL where practical.

- Prefer small composable modules over large scripts.

- Every module should expose a run(context, config) entry point
  returning ModuleResult.

- Include fixtures for a tiny simulation, a medium simulation, and
  validation-failure scenarios.
