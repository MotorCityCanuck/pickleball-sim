# Student-Facing Analytics Dataset Specification

## Status

Proposed specification for review.

## Purpose

This document defines the structure, scope, and governance rules for
student-facing analytical datasets generated from the NAPA simulation database.

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
- student-built dimensional modeling and analytical mart creation

The datasets should NOT expose:

- generator configuration internals
- hidden simulation parameters
- internal orchestration metadata
- operational workload metadata
- actual hidden ratings
- privileged simulation state
- generator implementation logic
- instructor-only benchmark or answer-key fields

---

# Dataset Philosophy

The student-facing datasets should resemble operational sports analytics data
that an external consulting organization might realistically receive from a
sports governing body.

The student release should mirror the approved operational database tables as
closely as possible, excluding only those tables and columns that are internal
to the data generator, privileged to the instructor, unsafe for student access,
or not intended for release.

The export should not pre-build a clean dimensional model for students. Instead,
students should receive operational-style table extracts and be expected to
perform their own data engineering work, including:

- schema inspection
- relationship discovery
- data profiling
- data quality assessment
- entity understanding
- dimensional model design
- fact and dimension construction
- analytical feature engineering
- business-friendly data mart creation

Students should receive:

- imperfect but analytically useful data in parquet format
- database-like table structures
- longitudinal match history
- observable player outcomes
- rating histories and movement
- realistic noise and variance
- partial visibility into underlying performance
- enough normalized source structure to require meaningful data engineering

Students should NOT receive:

- direct access to the true simulation model
- perfect skill indicators
- hidden confidence metrics
- exact generation assumptions
- internal causal mechanics
- pre-modeled dimensional marts that remove the need for student pipeline design

The system should intentionally preserve uncertainty and require students to
create analytical structures rather than simply consume pre-aggregated outputs.

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
- data quality assessment
- business objectives validation
- model training
- exploratory analysis
- initial rankings
- baseline tournament forecasting
- development of student-owned dimensional models and analytical marts

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
- incremental data engineering pipeline execution

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
- strong fit for local analytical database workflows

Compression should use:

```text
snappy
```

unless future benchmarking suggests otherwise.

---

# Recommended Dataset Structure

## Core Release Folder

The release folder should avoid pre-labeled `dimensions`, `facts`, and `derived`
folders because those classifications are part of the student data engineering
assignment. Instead, released tables should be organized as operational table
extracts with supporting metadata and documentation.

```text
release_YYYY_MM/
  metadata/
  tables/
  documentation/
```

## Tables Folder

The `tables/` folder contains student-approved parquet exports that mirror the
approved operational database tables.

Example:

```text
release_2027_01/
  tables/
    players.parquet
    clubs.parquet
    regions.parquet
    teams.parquet
    team_memberships.parquet
    matches.parquet
    games.parquet
    rating_history.parquet
    tournaments.parquet
```

The file name should normally match the source database table name unless a
safe rename is required for clarity or to avoid exposing internal naming.

## Design Rule

Do not export instructor-prepared analytical constructs such as:

- `dim_players.parquet`
- `dim_clubs.parquet`
- `dim_regions.parquet`
- `dim_teams.parquet`
- `fact_matches.parquet`
- `fact_games.parquet`
- `fact_rating_history.parquet`
- `monthly_player_summary.parquet`
- `monthly_region_summary.parquet`

Students should create those dimensional, fact, and summary structures as part
of their own data engineering pipeline.

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
- table_count
- match_count
- player_count
- team_count
- release_type

### data_dictionary.parquet

Contains field definitions and dataset descriptions.

Allowed fields:

- table_name
- column_name
- data_type
- description
- nullable_indicator
- student_visibility_notes

### table_relationships.parquet

Contains a student-visible relationship guide without giving away analytical
modeling choices.

Allowed fields:

- source_table
- source_column
- target_table
- target_column
- relationship_type
- notes

This file may identify operational foreign-key-style relationships, but it
should not prescribe a final star schema or dimensional model.

---

# Student Analytical Modeling Expectation

The released dataset should intentionally require students to build analytical
structures from operational-style inputs.

Students are expected to determine how to model:

- player dimensions
- club dimensions
- region dimensions
- tournament dimensions
- team dimensions
- match facts
- game facts
- rating history facts
- monthly player summaries
- monthly region summaries
- performance features
- forecasting features

The instructor-provided release should therefore expose clean enough operational
data to support the assignment, but not so much pre-modeled structure that the
student data engineering challenge is removed.

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

## Hidden Ratings And Truth Signals

Do not expose:

- actual_rating
- true_skill_rating
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

## Optional Educational Variants

The instructor may optionally:

### Variant A

Expose visible ratings only.

Students develop alternative rating methodologies independently.

### Variant B

Expose visible ratings and visible deltas.

Students evaluate rating quality and predictive capability.

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
- inconsistent operational coding that students must standardize

The datasets should remain analytically usable while resembling operational
sports data environments.

Data quality issues should be injected into student-facing parquet outputs only
after high-quality source data has been generated in the database. Data quality
issue injection must not violate database ORM rules, primary-key uniqueness, or
foreign-key referential integrity.

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
- operational table relationship notes
- analytical assumptions visible to students
- excluded-field explanations where appropriate
- clear statement that students are responsible for building dimensional and analytical marts

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

DuckDB is the recommended student analysis engine because it can query parquet
files directly, supports SQL-oriented data engineering workflows, and provides a
realistic local analytical database experience without requiring server-based
infrastructure.

---

# Suggested Initial Scope

## Initial Historical Dataset

Recommended scale:

- 250,000+ players
- 12 months of history
- millions of matches
- realistic regional distributions
- realistic club distributions
- operational-style table extracts rather than pre-modeled dimensional outputs

## Monthly Release Scope

Recommended cadence:

- one incremental month per release
- append-style historical progression
- no retroactive historical rewrites
- schema compatibility across monthly releases whenever possible

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
safe student-facing operational tables.

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
    mirror_source_table: true | false
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
- a table is renamed into a dimensional or fact naming pattern without explicit approval

---

# Proposed Initial Table Classification

The exact table names should be aligned to the implemented ORM schema. The
following classification establishes the intended first release posture.

## Included Student-Facing Tables

These approved operational database tables should be included in the
student-facing release. Export file names should generally mirror the source
database table names.

```text
players -> players.parquet
clubs -> clubs.parquet
regions -> regions.parquet
teams -> teams.parquet
team_memberships -> team_memberships.parquet
matches -> matches.parquet
games -> games.parquet
rating_history -> rating_history.parquet
tournaments -> tournaments.parquet, if implemented
```

## Not Included As Prebuilt Student Outputs

The following tables/files should not be provided as instructor-created parquet
outputs because students should create these structures themselves as part of
their data engineering pipeline.

```text
dim_players
dim_clubs
dim_regions
dim_teams
fact_matches
fact_games
fact_rating_history
fact_team_memberships
monthly_player_summary
monthly_region_summary
other pre-aggregated analytical marts
```

If these structures exist internally for instructor testing, benchmarking, or
solution validation, they must be classified as `instructor_only` and excluded
from student release folders.

## Excluded Operational / Configuration Tables

These tables should be excluded from student-facing releases.

```text
configuration_profiles
configuration_profile_versions
generation_runs
monthly_batches
job_status
raw_seed_load_runs
raw_seed_load_errors
export_runs
validation_runs
pipeline_stage_runs
student_dataset_releases
student_dataset_release_files
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

Students may receive transformed operational tables such as players, clubs, and
regions, but not raw seed inputs.

---

# Included Table Column Classification

The following sections define the initial student-facing projection for included
operational tables. Actual implementation must reconcile these projections
against the current ORM schema.

## players -> players.parquet

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

## clubs -> clubs.parquet

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

## regions -> regions.parquet

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

## teams -> teams.parquet

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

## team_memberships -> team_memberships.parquet

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

## matches -> matches.parquet

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

## games -> games.parquet

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

## rating_history -> rating_history.parquet

This table is intentionally critical to the educational experience.

Students should observe rating movement over time without access to the
underlying true skill model.

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

## tournaments -> tournaments.parquet

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

# Export Validation Requirements For Full Coverage

The student dataset export process must perform schema coverage validation before
writing parquet files.

Required validation checks:

1. Confirm release readiness checks passed before projection, data quality
   injection, or parquet writing begins.
2. Confirm the source generation run is current and has succeeded.
3. Confirm all monthly batches in the selected release scope have
   `processing_status = succeeded`.
4. Confirm no generation, seed ingest, seed normalization, or other write-heavy
   job is running.
5. Query the ORM/database metadata for the full list of tables.
6. Confirm every table appears in the export inventory.
7. Confirm every included table has every ORM/database column classified.
8. Confirm no excluded/protected column appears in the export dataframe.
9. Confirm no hidden rating, true skill rating, K-factor, generator
   configuration, or operational metadata column appears in any student-facing
   parquet file.
10. Confirm student-facing parquet schemas match the data dictionary.
11. Confirm instructor-only files are not placed in the student release folder.
12. Confirm no prebuilt dimensional, fact, or summary mart file is exported to
   the student release unless explicitly approved as part of a later assignment
   variant.
13. Confirm exported parquet file names align to approved operational table names
   or explicitly approved safe aliases.

A release must fail validation if any table or included-table column is
unclassified, any protected field scan fails, any validation blocker is present,
or any write-heavy operational job is active.

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
parquet write using approved operational table name
```

The default behavior for an unknown table or column must be:

```text
exclude and fail validation for review
```

Never default to exporting newly discovered columns.

Codex should also avoid generating instructor-prepared dimensional marts,
fact-table projections, or monthly summary outputs for the student release. If
those structures are needed for instructor validation, they should be written to
an instructor-only location and excluded from the student release package.

---



---

# Data Quality Injection Strategy

## Purpose

Prior to creation of student-facing parquet files, the export pipeline should
intentionally inject realistic data quality issues into approved student-facing
datasets.

The purpose of this process is to simulate realistic operational analytics
environments where data is often incomplete, inconsistent, delayed, noisy, or
imperfectly governed.

The data quality injection process is intended to strengthen the educational
value of the datasets by requiring participants to:
- identify data quality problems
- implement cleansing and validation logic
- develop robust analytical pipelines
- assess trustworthiness of data
- manage uncertainty
- design resilient analytical workflows

The student-facing datasets should remain analytically usable while reflecting
realistic enterprise data quality conditions.

---

# Injection Timing

Data quality injection should occur only after:

```text
simulation generation complete
        ↓
ORM/database validation complete
        ↓
student-safe export projection complete
        ↓
data quality injection
        ↓
parquet file creation
```

This design is intentional.

The operational simulation database should remain internally consistent and
fully valid. Data quality issues should be introduced only into the
student-facing analytical release artifacts.

This approach preserves:
- ORM integrity
- referential integrity
- simulation consistency
- operational reproducibility
- instructor-side truth validation

while still providing realistic analytical challenges for participants.

---

# Data Quality Injection Principles

Injected issues must:
- preserve parquet readability
- preserve basic analytical usability
- avoid catastrophic corruption
- avoid breaking foreign-key relationships
- avoid invalidating historical chronology
- avoid creating impossible match outcomes
- avoid exposing hidden simulation mechanics

Injected issues should resemble realistic operational sports analytics problems
that might occur in decentralized and manually managed competitive environments.

---

# Configurable Injection Levels

The export process should support configurable data quality severity levels.

Suggested levels:

```text
low
medium
high
very_high
```

Higher severity levels should increase:
- frequency of issues
- breadth of affected datasets
- ambiguity of values
- inconsistency rates
- delayed data visibility
- observational uncertainty

The instructor should be able to configure injection levels independently for:
- development environments
- coursework releases
- advanced cohorts
- challenge datasets

---

# High-Level Categories Of Injected Data Quality Issues

## Missing Values

Examples:
- missing club assignments
- incomplete demographic values
- missing crowd classifications
- missing environment labels
- delayed tournament metadata

Purpose:
Simulates incomplete operational reporting and delayed manual data entry.

---

## Inconsistent Categorical Values

Examples:
- inconsistent capitalization
- abbreviated region names
- alternate tournament labels
- inconsistent gender encoding
- mixed formatting conventions

Purpose:
Simulates decentralized data entry practices across independently managed clubs
and tournament organizations.

---

## Delayed Updates

Examples:
- delayed rating updates
- late-arriving tournament records
- delayed partnership changes
- postponed status changes

Purpose:
Simulates operational lag and asynchronous reporting cycles commonly found in
real-world sports organizations.

---

## Duplicate And Near-Duplicate Records

Examples:
- duplicate tournament registrations
- duplicate player records
- near-duplicate club names
- repeated match submissions

Purpose:
Simulates fragmented operational systems lacking centralized master-data
governance.

---

## Observational Noise

Examples:
- small score inconsistencies
- approximate duration bands
- coarse classifications
- imprecise environmental descriptors

Purpose:
Simulates imperfect observational capture and human-entered operational data.

---

## Sparse Edge Cases

Examples:
- regions with minimal activity
- infrequent tournament formats
- low-frequency partnership combinations
- rare event categories

Purpose:
Encourages robust analytical design capable of handling sparse and imbalanced
data distributions.

---

## Slowly Drifting Reference Values

Examples:
- evolving club classifications
- changing region descriptions
- revised tournament naming conventions
- gradual operational standardization changes

Purpose:
Simulates real organizations where operational definitions evolve over time.

---

# Explicitly Prohibited Data Quality Injection

The export process must never inject issues that:
- break parquet readability
- break referential integrity
- create impossible score outcomes
- expose hidden truth labels
- reveal generator configuration
- corrupt chronological sequencing
- invalidate match relationships
- create structurally unreadable datasets

The educational objective is controlled realism, not unusable corruption.

---

# Instructor Configuration Guidance

The export pipeline should support configuration-driven control over:
- issue categories enabled
- issue frequency
- affected datasets
- affected columns
- temporal distribution of issues
- deterministic versus randomized injection
- release-specific injection profiles

Suggested future configuration location:

```text
backend/app/export/student_dataset_dq_profiles.yaml
```




---

# Operational Dataset Scope Configuration

## Configurable Historical Scope

The operational date ranges and duration of the student-facing analytical
datasets should be controlled through configurable export settings rather than
hardcoded logic.

The export process should support configuration of:
- historical start dates
- historical end dates
- number of historical months included
- monthly release cadence
- incremental release windows
- rolling retention periods
- future release scheduling

This allows instructors and administrators to:
- create smaller pilot datasets
- generate large enterprise-scale historical releases
- support phased coursework progression
- simulate long-running operational environments
- vary analytical complexity between cohorts

Example configurable scenarios may include:
- 3-month introductory datasets
- 12-month historical enterprise datasets
- multi-year advanced analytical datasets
- rolling operational release windows

Suggested future configuration location:

```text
backend/app/export/student_dataset_release_profiles.yaml
```

---

# Export Process Orchestration

The parquet generation and export process should be initiated through the data
generation orchestration web application.

The orchestration interface should allow authorized users to:
- select export profiles
- configure release scope
- configure data quality injection severity
- select included release periods
- trigger export generation
- monitor export status
- review validation outcomes
- review export statistics
- publish finalized student-facing releases

The orchestration workflow should conceptually follow:

```text
simulation generation orchestration
        ↓
operational database validation
        ↓
student-safe export projection
        ↓
data quality injection
        ↓
parquet file generation
        ↓
release validation
        ↓
release publication
```

Before parquet generation begins, the orchestration workflow must verify release
readiness.

Required release readiness checks:

- the source generation run is the current generation run
- the source generation run has succeeded
- all monthly batches in the selected release scope have `processing_status = succeeded`
- no generation, seed ingest, seed normalization, or other write-heavy job is running
- seed/reference readiness checks pass
- the student-facing table and column projection inventory is complete
- every included table has every exported column classified
- no unclassified table or column is allowed in the release
- protected-field scan passes before parquet writing
- hidden rating, generator configuration, seed, operational metadata, and job/log fields are absent from projected export dataframes
- projected student-facing tables preserve required referential integrity
- no validation blockers are present

If any readiness check fails, parquet generation must not begin.

The orchestration layer should provide centralized operational visibility and
administrative control over the educational dataset release lifecycle.




---

# Referential Integrity Requirements

The student-facing datasets must preserve referential integrity across all
approved exposed tables.

Although data quality issues may be intentionally injected into the parquet
releases, the export process must ensure that exposed relational structures
remain joinable and analytically usable.

This requirement is critical because participants will be expected to:
- join datasets across multiple entities
- construct analytical pipelines
- build dimensional models
- create feature engineering workflows
- generate reporting datasets
- perform longitudinal analysis
- develop predictive models
- support tournament forecasting and simulation

Examples of required preserved relationships include:
- matches to teams
- teams to players
- players to clubs
- clubs to regions
- games to matches
- tournaments to regions
- rating history to players

The export process must therefore ensure:
- valid exposed foreign-key relationships
- stable identifiers across releases
- consistent entity references
- reproducible joins
- chronologically coherent relationships

Data quality injection may introduce realistic analytical imperfections, but it
must not create structurally unusable datasets.

The educational objective is to simulate realistic enterprise analytical
environments where data may be imperfect but remains operationally usable.

---

# Bronze Layer Educational Positioning

The student-facing parquet releases should conceptually represent the bronze
(raw) layer of the participant analytical environment.

The datasets are intentionally designed to resemble operational raw analytical
extracts rather than fully curated enterprise reporting models.

Participants are therefore expected to perform downstream analytical engineering
activities including:
- data profiling
- data quality assessment
- cleansing and standardization
- schema harmonization
- entity resolution
- dimensional modeling
- feature engineering
- aggregation design
- analytical transformation
- gold-layer analytical dataset construction

The student-facing releases should not provide fully curated dimensional models,
prebuilt star schemas, or highly aggregated analytical outputs beyond limited
educational convenience datasets explicitly approved for release.

This design is intentional.

The educational objective is to require participants to construct meaningful
data engineering and analytical workflows similar to those expected within
modern enterprise analytics environments.

The bronze-layer positioning also supports:
- medallion architecture education
- incremental pipeline design
- reproducible transformation workflows
- operational data engineering practices
- analytical governance concepts
- lineage and traceability exercises

Participants should therefore treat the parquet releases as operational raw
analytical inputs rather than finalized reporting-ready datasets.


# Recommendation

The student-facing datasets should intentionally resemble realistic operational
sports analytics releases rather than perfectly transparent simulation outputs
or prebuilt analytical marts.

The educational objective is not to expose the simulation engine itself, nor to
provide students with an already-modeled dimensional warehouse. The objective is
to provide a rich operational data environment where students must reason under
uncertainty, design their own analytical data structures, derive insight from
incomplete observability, and develop defensible analytical methodologies.

---

# Future Enhancement Backlog

## Educational Enhancements

- hidden advanced challenge datasets
- anomaly-injection scenarios
- synthetic fraud/collusion scenarios
- injury-event analytical datasets
- weather/environmental datasets
- player-travel datasets
- optional advanced cohort release with ratings fully hidden

## Technical Enhancements

- partitioned parquet optimization
- Iceberg/Delta Lake support
- release lineage metadata
- reproducibility manifests
- release signing/checksums
- automated schema drift detection against ORM metadata

## Instructor Enhancements

- instructor-only truth datasets
- hidden benchmark scoring datasets
- automated assignment evaluation datasets
- student leaderboard datasets
- controlled hidden holdout datasets
- instructor-only reference dimensional model for grading and comparison
