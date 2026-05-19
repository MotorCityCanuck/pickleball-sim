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

# Recommendation

The student-facing datasets should intentionally resemble realistic operational
sports analytics releases rather than perfectly transparent simulation outputs.

The educational objective is not to expose the simulation engine itself, but to
provide a rich analytical environment where students must reason under
uncertainty, derive insight from incomplete observability, and develop
defensible analytical methodologies.
