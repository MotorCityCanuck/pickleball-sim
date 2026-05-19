# Student-Facing Analytics Dataset Specification

## Status

Proposed specification for review.

## Purpose

This document defines the structure, scope, and governance rules for
student-facing analytical datasets generated from the NAPA simulation platform.

The purpose of the student-facing datasets is to provide realistic,
large-scale sports analytics data suitable for graduate-level data science,
analytics engineering, machine learning, and simulation coursework while
concealing internal simulation mechanics, hidden variables, and operational
implementation details.

The datasets should support:

- analytics projects
- machine learning experimentation
- dashboarding
- statistical analysis
- ranking and prediction models
- Monte Carlo simulations
- tournament forecasting
- player and team performance analysis

The datasets should NOT expose:

- generator configuration internals
- hidden simulation parameters
- internal orchestration metadata
- operational workload metadata
- actual hidden ratings
- privileged simulation state
- generator implementation logic

---

# Dataset Philosophy

The student-facing datasets should resemble operational sports analytics data
that an external consulting organization might realistically receive from a
sports governing body.

Students should receive:

- imperfect but analytically useful data
- longitudinal match history
- observable player outcomes
- rating histories and movement
- realistic noise and variance
- partial visibility into underlying performance

Students should NOT receive:

- direct access to the true simulation model
- perfect skill indicators
- hidden confidence metrics
- exact generation assumptions
- internal causal mechanics

The system should intentionally preserve uncertainty.

---

# Release Structure

The educational dataset release model should include:

## Initial Historical Release

One full historical year of parquet datasets.

Example:

```text
release_2027_01/
```

This release should establish the historical baseline used by students for:

- feature engineering
- model training
- exploratory analysis
- initial rankings
- baseline tournament forecasting

---

## Monthly Incremental Releases

Subsequent monthly parquet releases containing newly generated match activity.

Example:

```text
release_2027_02/
release_2027_03/
release_2027_04/
```

Monthly releases should support:

- incremental ingestion
- longitudinal modeling
- temporal drift analysis
- rolling forecasting
- retraining workflows
- simulation of operational analytics environments

---

# File Format

## Required Format

All student-facing datasets should be released as parquet files.

Reasons:

- columnar efficiency
- fast analytical reads
- compatibility with Spark/Pandas/Polars/DuckDB
- realistic enterprise analytics workflow
- efficient storage size

Compression should use:

```text
snappy
```

unless future benchmarking suggests otherwise.

---

# Recommended Dataset Structure

## Core Release Folder

```text
release_YYYY_MM/
  metadata/
  dimensions/
  facts/
  derived/
  documentation/
```

---

# Metadata Folder

## Purpose

Contains educational metadata and release documentation.

## Allowed Files

### release_manifest.parquet

High-level release metadata.

Allowed fields:

- release_id
- release_month
- release_created_at
- historical_months_included
- match_count
- player_count
- team_count

---

## data_dictionary.parquet

Contains field definitions and dataset descriptions.

Allowed fields:

- table_name
- column_name
- data_type
- description

---

# Dimensions Folder

## dim_players.parquet

Student-visible player reference information.

### Allowed Fields

- player_id
- first_name
- last_name
- country_code
- region_code
- metro_area
- club_id
- dominant_hand
- gender
- age_band
- first_active_month
- current_visible_rating
- current_visible_confidence
- player_status

### Hidden / Excluded Fields

DO NOT expose:

- actual_rating
- hidden_skill_rating
- latent_performance_rating
- generator_noise_coefficients
- injury_probability
- fatigue_recovery_coefficients
- hidden_growth_potential
- hidden_consistency_scores
- internal archetype classifications

---

## dim_clubs.parquet

### Allowed Fields

- club_id
- club_name
- country_code
- region_code
- metro_area
- estimated_member_size_band
- club_type

---

## dim_regions.parquet

### Allowed Fields

- region_code
- region_name
- country_code
- estimated_population_band

---

# Facts Folder

## fact_matches.parquet

Primary analytical match-level dataset.

### Allowed Fields

- match_id
- match_date
- tournament_id
- tournament_type
- event_type
- match_format
- best_of_games
- winning_team_id
- losing_team_id
- winning_team_score
- losing_team_score
- match_duration_band
- surface_type
- environment_type
- crowd_band

### Excluded Fields

DO NOT expose:

- hidden match difficulty
- generated randomness values
- fatigue calculations
- hidden momentum factors
- hidden pressure modifiers
- hidden matchup advantage scores

---

## fact_games.parquet

### Allowed Fields

- game_id
- match_id
- game_sequence
- winning_team_score
- losing_team_score

---

## fact_team_memberships.parquet

### Allowed Fields

- team_id
- player_id
- start_month
- end_month
- partnership_duration_matches
- partnership_duration_months

---

## fact_rating_history.parquet

This dataset is intentionally critical to the educational experience.

Students should observe rating movement over time without access to the
underlying true skill model.

### Allowed Fields

- player_id
- rating_month
- visible_rating
- visible_rating_delta
- visible_confidence
- matches_played_month
- wins_month
- losses_month

### Important Design Principle

The visible rating should NOT equal the actual hidden skill rating.

The visible rating system should intentionally contain:

- observational lag
- bounded noise
- imperfect estimation
- delayed adaptation
- confidence uncertainty

This allows students to:

- reverse-engineer rating behavior
- design alternative rating systems
- compare ranking methodologies
- analyze stability and predictive quality

without directly exposing the underlying simulation truth.

---

# Derived Folder

## Purpose

Contains pre-aggregated analytical helper datasets.

These should reduce unnecessary student engineering overhead while still
requiring meaningful analytical work.

---

## Suggested Derived Datasets

### monthly_player_summary.parquet

Suggested fields:

- player_id
- month
- matches_played
- wins
- losses
- visible_rating
- visible_rating_delta
- partner_count
- opponent_count

---

## monthly_region_summary.parquet

Suggested fields:

- region_code
- month
- active_players
- active_teams
- matches_played
- average_visible_rating

---

# Tournament Data

## tournament_events.parquet

### Allowed Fields

- tournament_id
- tournament_name
- start_date
- end_date
- tournament_type
- region_code
- event_category

---

# Intentionally Concealed Information

The following information should NEVER appear in student-facing datasets.

## Generator Configuration

Do not expose:

- generation configuration payloads
- runtime parameters
- weight distributions
- random seed values
- noise coefficients
- regional weighting logic
- hidden matchmaking rules
- simulation probability models

---

## Operational Metadata

Do not expose:

- generation_runs
- monthly_batches
- export_runs
- job_status
- orchestration logs
- pipeline stage logs
- validation logs
- internal error logs

---

## Hidden Ratings And Truth Signals

Do not expose:

- actual_rating
- hidden_skill_rating
- internal confidence
- projected future growth
- hidden consistency
- hidden injury susceptibility
- latent player archetypes

The system should preserve imperfect observability.

Students should infer patterns rather than receive perfect truth labels.

---

# Rating System Educational Strategy

## Recommended Educational Design

The platform should internally maintain:

```text
actual_hidden_rating
```

while exposing:

```text
visible_rating
```

The visible rating should be a derived approximation.

Potential design characteristics:

- lagged updates
- bounded variance
- confidence adjustments
- rating smoothing
- delayed convergence
- temporary over/underestimation

This creates a more realistic analytics environment.

---

## Optional Educational Variants

The instructor may optionally:

### Variant A

Expose visible ratings only.

Students develop alternative rating methodologies independently.

---

### Variant B

Expose visible ratings and visible deltas.

Students evaluate rating quality and predictive capability.

---

### Variant C

Hide ratings entirely for advanced cohorts.

Students derive ranking methodologies solely from match outcomes.

---

# Data Quality Philosophy

The datasets should intentionally contain realistic imperfections.

Examples:

- missing values
- inconsistent categorical labels
- delayed updates
- sparse edge cases
- small observational noise
- imperfect confidence indicators

The datasets should remain analytically usable while resembling operational
sports data environments.

---

# Release Governance

## Immutable Releases

Published student releases should be immutable.

Do not overwrite released parquet files after publication.

Corrections should generate:

```text
release_YYYY_MM_patch_01/
```

or equivalent.

---

# Documentation Requirements

Each release should include:

- release notes
- data dictionary
- known limitations
- schema descriptions
- analytical assumptions visible to students
- excluded-field explanations where appropriate

---

# Performance Expectations

The datasets should support:

- local DuckDB analysis
- Pandas workflows
- Polars workflows
- PySpark ingestion
- Jupyter notebooks
- Power BI
- Tableau

without requiring distributed infrastructure for standard coursework usage.

---

# Suggested Initial Scope

## Initial Historical Dataset

Recommended scale:

- 250,000+ players
- 12 months of history
- millions of matches
- realistic regional distributions
- realistic club distributions

---

## Monthly Release Scope

Recommended cadence:

- one incremental month per release
- append-style historical progression
- no retroactive historical rewrites

---

# Future Enhancement Backlog

## Educational Enhancements

- hidden advanced challenge datasets
- anomaly-injection scenarios
- synthetic fraud/collusion scenarios
- injury-event analytical datasets
- weather/environmental datasets
- player-travel datasets

---

## Technical Enhancements

- partitioned parquet optimization
- Iceberg/Delta Lake support
- release lineage metadata
- reproducibility manifests
- release signing/checksums

---

## Instructor Enhancements

- instructor-only truth datasets
- hidden benchmark scoring datasets
- automated assignment evaluation datasets
- student leaderboard datasets
- controlled hidden holdout datasets

---


---

# Mandatory Table And Column Coverage Rule

Every table in the simulation database must be explicitly addressed before a
student-facing parquet release can be considered complete.

Each database table must be classified as one of:

```text
included
excluded
instructor_only
future_candidate
```

Definitions:

- `included`: table is exported to the student-facing parquet release.
- `excluded`: table is never exported to students.
- `instructor_only`: table may be exported only to instructor-only validation,
  answer-key, or benchmark bundles.
- `future_candidate`: table is not exported in the first release but may be
  considered for later student-facing releases.

For every table classified as `included`, every column in that table must be
classified as one of:

```text
include
exclude
derived_replace
redacted
```

Definitions:

- `include`: column is exported as-is or with safe formatting.
- `exclude`: column is not exported.
- `derived_replace`: internal column is not exported directly, but a safer
  derived student-facing value may be exported.
- `redacted`: column is removed or replaced with a generalized representation.

No included table may have unclassified columns.

No table may be silently omitted from this review.

Unknown tables or columns must default to:

```text
exclude and fail validation for review
```

Never default to exporting newly discovered tables or columns.

---

# Exclusion Principles

The student-facing release must exclude any column that directly or indirectly
reveals internal simulation truth, generator behavior, privileged configuration,
or operational execution metadata.

The following categories must be excluded from student-facing parquet releases.

## Hidden Skill And Rating Internals

Exclude columns such as:

- actual_rating
- true_skill_rating
- hidden_skill_rating
- latent_rating
- internal_rating
- skill_mean
- skill_sigma
- rating_mu
- rating_sigma
- k_factor
- effective_k_factor
- dynamic_k_factor
- rating_engine_k
- team_k_factor
- rating_confidence_internal
- hidden_confidence
- internal_confidence
- rating_uncertainty_internal
- volatility_internal

Student-facing exports may include only approved visible rating fields, such as:

- visible_rating
- visible_rating_delta
- visible_confidence

These visible fields should be treated as imperfect observational estimates, not
as true skill labels.

## Generator Configuration And Parameters

Exclude columns such as:

- configuration_profile_id, unless used only in instructor-only metadata
- configuration_profile_version_id, unless used only in instructor-only metadata
- parameter_snapshot
- config_payload
- generator_config
- rule_config
- simulation_config
- weighting_config
- distribution_config
- noise_config
- random_seed
- rng_seed
- seed_value
- generator_version_internal

## Operational Execution Metadata

Exclude columns such as:

- generation_run_id, unless replaced with a safe release identifier
- monthly_batch_id, unless replaced with a safe release month
- job_id
- job_type
- job_status
- current_phase
- percent_complete
- current_message
- error_message
- stack_trace
- started_at for internal jobs
- completed_at for internal jobs
- created_by_operator
- internal_export_path
- source_script_name

## Hidden Simulation Mechanics

Exclude columns such as:

- fatigue_score_internal
- injury_probability
- injury_susceptibility
- recovery_rate
- growth_potential
- consistency_factor
- clutch_factor
- pressure_modifier
- partnership_affinity_internal
- matchup_advantage_internal
- regional_bias_factor
- hidden_archetype
- simulated_random_component
- noise_term
- outcome_probability_internal

## Raw Seed And Source Data Fields

Exclude raw seed data tables and columns unless deliberately transformed into
safe dimensions.

Examples to exclude:

- raw source file names
- raw row hashes
- raw load run identifiers
- raw source system fields
- rejected-row details
- normalization error details
- source lineage that reveals generation design

---

# Required Database Table Inventory

The implementation must maintain a table-level export inventory.

This inventory should be version-controlled and reviewed whenever the ORM schema
changes.

Suggested inventory file:

```text
backend/app/export/student_dataset_table_inventory.yaml
```

Required structure:

```yaml
tables:
  table_name:
    classification: included | excluded | instructor_only | future_candidate
    student_export_name: optional_export_file_name
    rationale: explanation of inclusion or exclusion
    columns:
      column_name:
        classification: include | exclude | derived_replace | redacted
        student_column_name: optional_renamed_column
        rationale: explanation
```

The export job must fail validation if:

- a database table is missing from the inventory
- an included table contains an unclassified column
- a protected column is classified as include
- a hidden truth column is present in the student export
- generator configuration fields are present in the student export
- operational metadata fields are present in the student export

---

# Proposed Initial Table Classification

The exact table names should be aligned to the implemented ORM schema. The
following classification establishes the intended first release posture.

## Included Student-Facing Tables

These tables or projections should be included in the student-facing release.

```text
players -> dim_players.parquet
clubs -> dim_clubs.parquet
regions -> dim_regions.parquet
teams -> dim_teams.parquet or fact_team_memberships.parquet
team_memberships -> fact_team_memberships.parquet
matches -> fact_matches.parquet
games -> fact_games.parquet
rating_history -> fact_rating_history.parquet
tournaments -> tournament_events.parquet, if implemented
monthly_player_summary -> monthly_player_summary.parquet, if implemented
monthly_region_summary -> monthly_region_summary.parquet, if implemented
```

## Excluded Operational / Configuration Tables

These tables should be excluded from student-facing releases.

```text
configuration_profiles
configuration_profile_versions
generation_runs
generation_plans
monthly_batches
job_status
raw_seed_load_runs
raw_seed_load_errors
export_runs
validation_runs
pipeline_stage_runs
```

## Excluded Raw Seed Tables

Raw seed tables should not be exported directly to students.

```text
raw_metro_areas_us
raw_metro_areas_ca
raw_first_names_us
raw_first_names_ca
raw_last_names_us
raw_last_names_ca
raw_pickleball_club_distributions
raw_pickleball_club_names
raw_state_prov_biases_us
raw_state_prov_biases_ca
```

Students may receive transformed region, club, and player dimensions, but not
raw seed inputs.

---

# Included Table Column Classification

The following sections define the initial student-facing projection for included
tables. Actual implementation must reconcile these projections against the
current ORM schema.

## players -> dim_players.parquet

### Include

- player_id
- first_name
- last_name
- country_code
- region_code
- metro_area
- club_id
- dominant_hand
- gender
- age_band
- first_active_month
- current_visible_rating
- current_visible_confidence
- player_status

### Exclude

- actual_rating
- true_skill_rating
- hidden_skill_rating
- latent_rating
- internal_rating
- k_factor
- effective_k_factor
- dynamic_k_factor
- hidden_confidence
- rating_uncertainty_internal
- growth_potential
- consistency_factor
- fatigue_score_internal
- injury_probability
- injury_susceptibility
- recovery_rate
- hidden_archetype
- generator_config_id
- generation_run_id
- monthly_batch_id
- random_seed
- created_at_internal
- updated_at_internal

### Derived Replace / Redact

- exact_birthdate -> age_band
- exact_age -> age_band
- internal_club_assignment_reason -> exclude
- internal_region_assignment_weight -> exclude

---

## clubs -> dim_clubs.parquet

### Include

- club_id
- club_name
- country_code
- region_code
- metro_area
- estimated_member_size_band
- club_type

### Exclude

- exact_member_count_internal
- generation_weight
- club_assignment_weight
- raw_source_row_id
- raw_seed_load_run_id
- generator_config_id
- generation_run_id
- created_at_internal
- updated_at_internal

### Derived Replace / Redact

- exact_member_count -> estimated_member_size_band

---

## regions -> dim_regions.parquet

### Include

- region_code
- region_name
- country_code
- estimated_population_band

### Exclude

- exact_population_internal
- regional_generation_weight
- regional_bias_factor
- raw_source_row_id
- raw_seed_load_run_id
- generator_config_id
- created_at_internal
- updated_at_internal

### Derived Replace / Redact

- exact_population -> estimated_population_band

---

## teams -> dim_teams.parquet or fact_team_memberships.parquet

If a separate team dimension is exported, include only stable student-facing
team identifiers and descriptive fields.

### Include

- team_id
- team_type
- event_type
- first_active_month
- last_active_month
- team_status

### Exclude

- partnership_affinity_internal
- hidden_team_strength
- actual_team_rating
- true_team_rating
- team_k_factor
- team_confidence_internal
- generator_config_id
- generation_run_id
- random_seed
- created_at_internal
- updated_at_internal

---

## team_memberships -> fact_team_memberships.parquet

### Include

- team_id
- player_id
- start_month
- end_month
- partnership_duration_matches
- partnership_duration_months

### Exclude

- partnership_affinity_internal
- partnership_generation_reason
- hidden_compatibility_score
- internal_team_assignment_score
- generation_run_id
- monthly_batch_id
- created_at_internal
- updated_at_internal

---

## matches -> fact_matches.parquet

### Include

- match_id
- match_date
- tournament_id
- tournament_type
- event_type
- match_format
- best_of_games
- winning_team_id
- losing_team_id
- winning_team_score
- losing_team_score
- match_duration_band
- surface_type
- environment_type
- crowd_band

### Exclude

- expected_winner_internal
- actual_win_probability
- hidden_match_difficulty
- hidden_match_quality
- simulated_random_component
- noise_term
- fatigue_modifier
- injury_modifier
- pressure_modifier
- matchup_advantage_internal
- rating_gap_internal
- team_actual_rating_before
- team_actual_rating_after
- team_visible_rating_before_internal
- team_visible_rating_after_internal
- generator_config_id
- generation_run_id
- monthly_batch_id
- job_id
- created_at_internal
- updated_at_internal

### Derived Replace / Redact

- exact_match_duration_minutes -> match_duration_band
- exact_crowd_count -> crowd_band

---

## games -> fact_games.parquet

### Include

- game_id
- match_id
- game_sequence
- winning_team_score
- losing_team_score

### Exclude

- point_level_simulation_seed
- rally_model_parameters
- hidden_game_momentum
- simulated_random_component
- generator_config_id
- generation_run_id
- monthly_batch_id
- created_at_internal
- updated_at_internal

---

## rating_history -> fact_rating_history.parquet

### Include

- player_id
- rating_month
- visible_rating
- visible_rating_delta
- visible_confidence
- matches_played_month
- wins_month
- losses_month

### Exclude

- actual_rating
- true_skill_rating
- hidden_skill_rating
- latent_rating
- internal_rating
- rating_before_actual
- rating_after_actual
- rating_before_hidden
- rating_after_hidden
- expected_score_internal
- actual_score_internal
- k_factor
- effective_k_factor
- dynamic_k_factor
- confidence_multiplier_internal
- uncertainty_internal
- volatility_internal
- rating_engine_version_internal
- generator_config_id
- generation_run_id
- monthly_batch_id
- created_at_internal
- updated_at_internal

### Derived Replace / Redact

- detailed_rating_reason -> exclude
- internal_rating_formula_component_json -> exclude

---

## tournaments -> tournament_events.parquet

### Include

- tournament_id
- tournament_name
- start_date
- end_date
- tournament_type
- region_code
- event_category

### Exclude

- hidden_tournament_strength
- draw_generation_seed
- tournament_generation_weight
- generator_config_id
- generation_run_id
- created_at_internal
- updated_at_internal

---

## monthly_player_summary -> monthly_player_summary.parquet

### Include

- player_id
- month
- matches_played
- wins
- losses
- visible_rating
- visible_rating_delta
- partner_count
- opponent_count

### Exclude

- actual_rating
- true_skill_rating
- hidden_skill_rating
- k_factor
- hidden_confidence
- internal_confidence
- generator_config_id
- generation_run_id
- monthly_batch_id
- created_at_internal
- updated_at_internal

---

## monthly_region_summary -> monthly_region_summary.parquet

### Include

- region_code
- month
- active_players
- active_teams
- matches_played
- average_visible_rating

### Exclude

- average_actual_rating
- average_true_skill_rating
- regional_bias_factor
- regional_generation_weight
- hidden_strength_index
- generator_config_id
- generation_run_id
- monthly_batch_id
- created_at_internal
- updated_at_internal

---

# Export Validation Requirements For Full Coverage

The student dataset export process must perform schema coverage validation before
writing parquet files.

Required validation checks:

1. Query the ORM/database metadata for the full list of tables.
2. Confirm every table appears in the export inventory.
3. Confirm every included table has every ORM/database column classified.
4. Confirm no excluded/protected column appears in the export dataframe.
5. Confirm no hidden rating, true skill rating, K-factor, generator
   configuration, or operational metadata column appears in any student-facing
   parquet file.
6. Confirm student-facing parquet schemas match the data dictionary.
7. Confirm instructor-only files are not placed in the student release folder.

A release must fail validation if any table or included-table column is
unclassified.

---

# Codex Implementation Guidance

When implementing the student-facing export system, Codex should not infer safe
exports from table names alone.

The export implementation should be allowlist-driven:

```text
database table
        ↓
classification inventory
        ↓
explicit column projection
        ↓
student-safe dataframe
        ↓
optional data quality injection
        ↓
post-export validation
        ↓
parquet write
```

The default behavior for an unknown table or column must be:

```text
exclude and fail validation for review
```

Never default to exporting newly discovered columns.

# Recommendation

The student-facing datasets should intentionally resemble realistic operational
sports analytics releases rather than perfectly transparent simulation outputs.

The educational objective is not to expose the simulation engine itself, but to
provide a rich analytical environment where students must reason under
uncertainty, derive insight from incomplete observability, and develop
defensible analytical methodologies.
