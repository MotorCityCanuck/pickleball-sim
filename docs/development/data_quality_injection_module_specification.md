# Data Quality Injection Module Specification

## Status

Proposed specification for review.

## Purpose

This document defines the design for a configurable data quality injection module
for the NAPA simulation platform.

The purpose of the module is to introduce realistic, controlled, student-facing
data quality issues into exported analytical parquet datasets while preserving
the integrity of the internal simulation database.

The module should support graduate-level analytics and data engineering learning
objectives by exposing students to realistic imperfections without corrupting
the authoritative generated data.

---

# Core Design Decision

## Recommended Flow

The data quality injection module should run after the full simulation pipeline
has generated high-quality data in the database.

Recommended flow:

```text
Generate clean simulation data in database
        ↓
Validate ORM / database / FK integrity
        ↓
Select student-facing export datasets
        ↓
Apply controlled data quality injections in export layer
        ↓
Write student-facing parquet files
        ↓
Write instructor-only injection manifest
```

## Rationale

This is the preferred architecture because it:

- preserves ORM ruleset integrity
- preserves foreign key referential integrity
- keeps the simulation database trustworthy
- allows repeatable clean exports
- allows multiple student-facing quality variants from the same clean source
- prevents data quality issues from contaminating downstream internal pipeline stages
- supports instructor-controlled difficulty levels
- makes it easier to compare clean truth data against messy analytical data

Data quality issues should be introduced into parquet outputs, not into the
core relational database.

---

# Non-Negotiable Integrity Rules

Data quality injection must NOT:

- violate database primary key rules
- violate foreign key referential integrity
- create orphaned records
- create duplicate primary keys
- break ORM validation assumptions
- corrupt authoritative generation tables
- alter internal hidden truth fields
- overwrite source database records
- prevent parquet files from being read by standard tools
- make the dataset analytically unusable

The exported student-facing data may contain realistic analytical defects, but
the defects must remain controlled, explainable, and bounded.

---

# Target Users

Primary users:

- instructor/developer operators
- student analysts receiving released datasets
- future automated export jobs

Students should experience the resulting data quality issues.

Students should not see:

- the injection configuration
- injected-row lineage
- injected-field lineage
- instructor-only manifests
- hidden truth values
- clean comparison exports unless explicitly released by the instructor

---

# Scope

## In Scope

The data quality injection module should support:

- configurable injection levels
- configurable issue frequencies
- per-table issue controls
- per-column issue eligibility rules
- reproducible randomization using export-level seeds
- instructor-only injection manifests
- parquet-only mutation
- validation of post-injection exported datasets
- separate clean and student-facing export profiles

## Out of Scope for Initial Implementation

The first version does not need:

- UI editing of every injection rule
- machine-learning-based anomaly generation
- automatic issue balancing by assignment objective
- student-visible issue labels
- database-level mutation
- destructive production-data mutation
- real-time injection during pipeline generation

---

# Data Quality Injection Levels

The module should support the following named injection levels:

```text
none
low
medium
high
very_high
```

## Level Definitions

### none

No data quality issues are injected.

Use cases:

- instructor validation
- benchmark exports
- clean comparison datasets
- pipeline testing

---

### low

Light, realistic imperfections.

Students should notice issues only through careful profiling.

Approximate intent:

- suitable for introductory analytics
- mostly clean operational dataset
- minimal disruption to modeling
- small number of missing or inconsistent values

---

### medium

Moderate operational data quality issues.

Students should need to perform explicit cleaning and validation.

Approximate intent:

- suitable for standard graduate assignments
- visible categorical inconsistencies
- manageable missingness
- small number of duplicate-like records
- modest timestamp and formatting inconsistencies

---

### high

Significant data quality issues.

Students must build a robust data cleaning and profiling workflow.

Approximate intent:

- suitable for advanced analytics engineering
- stronger missingness patterns
- more inconsistent labels
- more edge cases
- more outlier values
- greater need for documented cleaning decisions

---

### very_high

Heavy but still bounded data quality issues.

Students must treat data quality as a primary analytical concern.

Approximate intent:

- suitable for capstone or advanced challenge datasets
- many visible but realistic issues
- increased need for validation, profiling, and defensible remediation
- still no broken primary/foreign key integrity

---

# Suggested Default Frequency Bands

Frequencies should be configurable and may vary by table and issue type.

Recommended starting defaults:

| Level | Field-Level Issue Rate | Row-Level Issue Rate | Categorical Variant Rate | Duplicate-Like Row Rate |
|---|---:|---:|---:|---:|
| none | 0.00% | 0.00% | 0.00% | 0.00% |
| low | 0.10% - 0.50% | 0.05% - 0.25% | 0.10% - 0.30% | 0.01% - 0.05% |
| medium | 0.50% - 2.00% | 0.25% - 1.00% | 0.30% - 1.00% | 0.05% - 0.20% |
| high | 2.00% - 5.00% | 1.00% - 3.00% | 1.00% - 3.00% | 0.20% - 0.75% |
| very_high | 5.00% - 10.00% | 3.00% - 6.00% | 3.00% - 6.00% | 0.75% - 1.50% |

These ranges should be treated as starting configuration values, not hard-coded
constants.

---

# Configuration Model

## Recommended Configuration Structure

```yaml
data_quality_injection:
  enabled: true
  level: medium
  random_seed: 12345
  apply_to_release_types:
    - historical
    - monthly
  write_instructor_manifest: true
  write_student_visible_quality_summary: false

  global_limits:
    max_total_affected_rows_pct: 5.0
    max_affected_fields_per_row: 2
    prevent_primary_key_mutation: true
    prevent_foreign_key_mutation: true
    preserve_required_join_keys: true

  table_rules:
    fact_matches:
      enabled: true
      issue_profile: medium
      allowed_issue_types:
        - missing_optional_values
        - categorical_variants
        - timestamp_jitter
        - numeric_outliers
        - duplicate_like_rows

    fact_games:
      enabled: true
      issue_profile: low
      allowed_issue_types:
        - missing_optional_values
        - score_format_variants

    dim_players:
      enabled: true
      issue_profile: medium
      allowed_issue_types:
        - name_case_variants
        - missing_optional_values
        - categorical_variants

    fact_rating_history:
      enabled: true
      issue_profile: low
      allowed_issue_types:
        - delayed_rating_updates
        - missing_optional_values
        - rounding_variants
```

---

# Eligible Issue Types

## 1. Missing Optional Values

Replace eligible non-key, nullable, or analytically optional fields with null.

Examples:

- missing match_duration_band
- missing crowd_band
- missing dominant_hand
- missing club_type
- missing environment_type

Must not affect:

- primary keys
- foreign keys
- required dates
- required metric fields needed for basic analytical usability

---

## 2. Categorical Variants

Introduce controlled inconsistencies in categorical fields.

Examples:

```text
Indoor
indoor
INDOOR
Indoor Court
Indoors
```

Useful fields:

- environment_type
- surface_type
- tournament_type
- club_type
- player_status

Constraints:

- values must remain parseable
- variants should be realistic
- avoid creating hundreds of arbitrary categories
- preserve a mapping in instructor-only manifest

---

## 3. Formatting Variants

Introduce realistic formatting inconsistencies.

Examples:

- inconsistent date string formats in optional display fields
- mixed casing in names
- extra whitespace in text fields
- punctuation variants in club names
- region label variants

Note:

Primary analytical date fields should remain valid timestamps unless a specific
advanced exercise intentionally requires date parsing.

---

## 4. Numeric Outliers

Introduce plausible but suspicious numeric values.

Examples:

- unusually long match duration band
- unusually high monthly match count in derived summaries
- suspicious but possible rating delta
- large but bounded team activity count

Constraints:

- values must remain within physically plausible boundaries
- no negative counts unless explicitly part of an advanced exercise
- no impossible game scores in the initial version
- no rating values outside the published visible rating bounds

---

## 5. Rounding Variants

Apply inconsistent rounding precision to selected visible analytical fields.

Examples:

- visible_rating rounded to 1 decimal place for some records
- visible_rating rounded to 3 decimal places for others
- visible_confidence rounded inconsistently

This is especially useful for student-facing rating history data.

---

## 6. Timestamp Jitter

Introduce small timing offsets in non-critical timestamps.

Examples:

- match_date shifted by plus/minus 1 day for a small percentage of records
- release timestamps rounded differently
- optional event timestamps delayed

Constraints:

- month assignment must remain coherent unless intentionally configured
- historical/monthly release boundaries must not be broken
- no future dates beyond the release period

---

## 7. Duplicate-Like Rows

Create records that appear duplicative but do not violate primary key rules.

Examples:

- repeated-looking match records with distinct match_id
- duplicate-looking player summary rows caused by minor formatting differences
- repeated tournament labels with different tournament_id

Constraints:

- no duplicate primary keys
- no broken foreign keys
- duplicate-like records must remain analytically explainable
- avoid excessive duplication that makes the dataset unusable

---

## 8. Delayed Rating Updates

In exported rating history only, delay or smooth visible rating updates for a
small subset of players.

Examples:

- visible_rating_delta appears one month later than expected
- visible_rating remains flat for one month despite match activity
- visible_confidence updates lag behind visible_rating

Constraints:

- actual hidden ratings are never exposed
- internal database rating state is not changed
- instructor manifest records the injected behavior
- visible rating values remain within valid bounds

---

## 9. Soft Join Ambiguity

Introduce ambiguity in non-key descriptive fields while preserving actual join
keys.

Examples:

- club_name variant while club_id remains correct
- metro_area label variant while region_code remains correct
- tournament_name spelling variant while tournament_id remains correct

Constraints:

- never mutate join keys
- never orphan records
- never require fuzzy matching for primary joins unless this is explicitly
  released as an advanced exercise

---

# Protected Fields

The following fields must never be mutated in student-facing exports unless a
future advanced exercise explicitly overrides this rule.

## Universal Protected Fields

- primary keys
- foreign keys
- stable surrogate identifiers
- release_id
- table partition fields
- required event dates
- hidden truth fields
- instructor-only lineage fields

## Examples

Do not mutate:

- player_id
- team_id
- match_id
- game_id
- club_id
- region_code
- tournament_id
- rating_month
- release_month

---

# Student-Facing vs Instructor-Only Outputs

## Student-Facing Output

Students receive only the released parquet files and student documentation.

Students should not receive:

- injection configuration
- injection manifest
- clean comparison dataset
- hidden rating data
- generator run metadata

---

## Instructor-Only Output

The export process should produce an instructor-only manifest.

Recommended file:

```text
instructor_only/data_quality_injection_manifest.parquet
```

Suggested fields:

- release_id
- table_name
- record_primary_key
- column_name
- issue_type
- original_value
- injected_value
- injection_level
- random_seed
- rule_id
- injected_at

For privacy and simplicity, this file should not be included in student
downloads.

---

# Post-Injection Validation

After injection, the module must validate that exported datasets remain usable.

## Required Validation Checks

- parquet files can be read
- schema is still compatible with the published data dictionary
- protected fields were not mutated
- primary key uniqueness is preserved in exported files
- foreign key relationships remain valid across exported files
- required fields remain populated
- row counts remain within expected tolerance
- configured maximum issue rates were not exceeded
- no hidden truth fields are present
- no generator configuration fields are present
- no operational metadata fields are present

---

# Integration With Export Pipeline

## Recommended Pipeline Placement

```text
database query / extraction
        ↓
clean analytical dataframe construction
        ↓
student-facing column projection
        ↓
data quality injection
        ↓
post-injection validation
        ↓
parquet writing
        ↓
manifest writing
        ↓
release packaging
```

The module should operate on export dataframes, not ORM entities.

---

# Module Interface

## Proposed Python Package Location

```text
backend/app/export/data_quality/
  __init__.py
  config.py
  injector.py
  rules.py
  validators.py
  manifests.py
```

---

## Proposed Entry Point

```python
inject_data_quality_issues(
    tables: dict[str, DataFrame],
    config: DataQualityInjectionConfig,
    release_context: ReleaseContext,
) -> DataQualityInjectionResult
```

---

## Proposed Result Object

```python
DataQualityInjectionResult:
    tables: dict[str, DataFrame]
    manifest: DataFrame
    summary: DataQualityInjectionSummary
    validation_result: ValidationResult
```

---

# Reproducibility

Injection must be reproducible.

Given the same:

- clean export dataset
- release_id
- injection config
- random seed

the module should produce the same injected output.

Recommended approach:

- use deterministic sampling
- combine global seed with table name and rule id
- avoid non-deterministic dataframe ordering
- sort input dataframes before sampling where needed

---

# Release Types

The module should support different behavior for:

## Historical Release

The initial 12-month dataset may receive a broader set of issues because it is
the primary training dataset.

## Monthly Release

Monthly releases should usually receive lower issue rates to avoid excessive
instability and to preserve longitudinal continuity.

Recommended default:

```text
historical release: configured level
monthly release: configured level minus one severity
```

Example:

```text
historical = medium
monthly = low
```

This should be configurable.

---

# Recommended Initial Implementation Scope

The first implementation should include:

- configuration object
- level-based frequency profiles
- table/column eligibility rules
- missing optional values
- categorical variants
- rounding variants
- soft join ambiguity
- duplicate-like rows
- instructor-only manifest
- post-injection validation
- parquet-only mutation

Do not implement in the first version:

- broken join-key exercises
- impossible scores
- severe date corruption
- hidden truth leakage
- database mutation
- student-visible injection labels
- UI-based rule editing

---

# Future Enhancement Backlog

## Advanced Data Quality Issues

- impossible-but-detectable score anomalies
- cross-table consistency drift
- stale dimensional attributes
- slowly changing dimension exercises
- tournament rescheduling anomalies
- late-arriving match results
- player transfer ambiguity
- club consolidation/split scenarios

---

## Educational Enhancements

- instructor-configurable assignment profiles
- beginner/intermediate/advanced dataset variants
- hidden benchmark cleaning rubric
- student data-quality scoring datasets
- optional answer-key manifest exports
- automated validation notebooks

---

## Technical Enhancements

- pluggable rule registry
- schema-driven rule eligibility
- rule-level unit test harness
- integration with export release manifests
- DuckDB-based validation layer
- partition-aware parquet injection
- deterministic distributed sampling

---

## UI Enhancements

- web control panel support for selecting injection level
- injection preview before export
- estimated affected-row summary
- validation results display
- instructor-only manifest download
- release comparison view

---

# Recommendation

The data quality injection module should operate only in the export layer after
the authoritative database has been generated and validated.

This approach protects the internal simulation engine while creating realistic
student-facing analytical complexity. It also supports multiple educational
variants from the same clean generated source, which is valuable for teaching,
testing, benchmarking, and future open dataset publication.
