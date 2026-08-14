# NAPA Tainted Dataset Data Quality Issues

## Purpose

This document outlines the data quality issues students should consider when
building ingestion, validation, cleaning, and analytical pipelines for the
tainted NAPA student dataset variant.

The tainted files use the same published table names, column names, and file
layout as the clean student-facing dataset. The issues are injected only into
the exported Parquet files. They do not change the source simulation database.

Students should treat the tainted package as a realistic operational dataset:
readable, relationally usable, but imperfect.

## What Is Preserved

The tainted export is designed to remain usable for analytics engineering and
modeling. Students should still expect the following to hold:

- Parquet files are readable by standard tools such as DuckDB, PyArrow, and
  Databricks.
- Published file names and column order match the student dataset contract.
- Primary keys remain populated and unique.
- Foreign-key relationships are preserved.
- Required join keys are preserved.
- The dataset does not expose hidden simulation truth fields.
- The dataset does not expose generator configuration, job metadata, or
  instructor-only injection lineage.
- Most rows remain clean.
- A single row should not have many independent injected defects.

The tainted export is not intended to be broken beyond repair. The goal is to
require explicit profiling, validation, and documented remediation decisions.

## Issue Severity And Frequency

The export supports named quality levels:

| Level | Field-level issue rate | Categorical variant rate | Duplicate-like row rate |
| --- | ---: | ---: | ---: |
| `none` | 0.00% | 0.00% | 0.00% |
| `low` | 0.10% - 0.50% | 0.10% - 0.30% | 0.01% - 0.05% |
| `medium` | 0.50% - 2.00% | 0.30% - 1.00% | 0.05% - 0.20% |
| `high` | 2.00% - 5.00% | 1.00% - 3.00% | 0.20% - 0.75% |
| `very_high` | 5.00% - 10.00% | 3.00% - 6.00% | 0.75% - 1.50% |

Actual counts vary by table size and by whether eligible non-null values exist
in a column. The export also enforces a global cap so that affected rows remain
bounded.

Current table profiles:

| Table | Injection profile |
| --- | --- |
| `clubs` | `medium` |
| `club_memberships` | `low` |
| `match_games` | `low` |
| `match_team_players` | `low` |
| `match_teams` | `low` |
| `matches` | `medium` |
| `monthly_batches` | `low` |
| `player_assessment_history` | `low` |
| `player_master` | `medium` |
| `player_registrations` | `low` |
| `regions` | `low` |
| `team_memberships` | `none` |
| `teams` | `low` |

## Active Issue Types

### Missing Optional Values

Some optional descriptive or analytical fields may be set to null. Required
keys and required operational fields are not intentionally nulled.

Affected columns:

| Table | Columns |
| --- | --- |
| `clubs` | `club_type`, `competitiveness_level` |
| `club_memberships` | `membership_type` |
| `matches` | `court_type` |
| `player_assessment_history` | `confidence_score` |
| `player_master` | `dominant_hand` |
| `player_registrations` | `registration_source` |

Pipeline considerations:

- Profile null rates by table and column before applying transformations.
- Distinguish optional missingness from impossible missingness.
- Avoid dropping otherwise useful rows solely because optional attributes are
  null.
- Document any imputation, defaulting, or unknown-category handling.

### Categorical Variants

Some categorical values may contain controlled formatting variants. These are
intended to simulate operational systems that encode the same business concept
with inconsistent labels.

Typical transformations include:

- lower-case variants
- upper-case variants
- title-case variants
- underscore-to-space variants
- underscore-to-hyphen variants

Affected columns:

| Table | Columns |
| --- | --- |
| `clubs` | `club_type`, `competitiveness_level` |
| `club_memberships` | `membership_type` |
| `matches` | `match_type`, `court_type`, `match_format` |
| `player_master` | `gender`, `dominant_hand`, `player_status` |
| `player_registrations` | `registration_source` |
| `regions` | `region_type` |
| `teams` | `team_type`, `team_division`, `team_status` |

Pipeline considerations:

- Normalize categorical values before grouping, filtering, or joining on labels.
- Preserve raw values in the Bronze layer when possible.
- Create explicit cleaned-domain mappings in Silver models.
- Track unmapped categories instead of silently coercing every unexpected value.

### Name Case Variants

Some player names may contain inconsistent casing or trailing whitespace.

Affected columns:

| Table | Columns |
| --- | --- |
| `player_master` | `first_name`, `last_name` |

Pipeline considerations:

- Trim whitespace in cleaned person-name fields.
- Avoid treating name casing as a stable entity key.
- Use stable identifiers such as `player_id` and `external_player_key` for
  joins.
- Preserve original names when presentation fidelity matters.

### Soft Join Ambiguity In Descriptive Fields

Some descriptive labels may be formatted inconsistently while stable IDs remain
unchanged. This simulates source systems where labels are messy but surrogate
keys remain trustworthy.

Typical transformations include:

- leading or trailing whitespace
- punctuation removal
- `&` versus `and`
- hyphen-to-space variants

Affected columns:

| Table | Columns |
| --- | --- |
| `clubs` | `club_name` |
| `regions` | `region_name` |

Pipeline considerations:

- Do not join on names when an ID is available.
- Use `club_id`, `region_id`, `player_id`, `team_id`, and `match_id` as the
  authoritative relationship keys.
- Normalize descriptive names for display, search, and grouping.
- Keep the raw descriptive value available for auditability.

### Rounding Variants

Some numeric measures may be rounded to inconsistent precision. These values
remain numeric, but precision may vary across rows.

Affected columns:

| Table | Columns |
| --- | --- |
| `match_team_players` | `player_rating_at_match` |
| `match_teams` | `average_team_rating` |
| `player_assessment_history` | `assessment_value`, `confidence_score` |
| `player_master` | `confidence_score`, `volatility_score`, `global_percentile` |
| `player_registrations` | `initial_rating_value`, `initial_confidence_score` |

Important note: `player_master.rating` and `player_master.rating_value` are not
targeted by rounding injection in the current export.

Pipeline considerations:

- Be explicit about numeric precision in Silver and Gold tables.
- Avoid comparing rounded values for exact equality unless the precision is
  defined.
- Use tolerance-based comparisons for derived checks where appropriate.
- Document any standard rounding applied in curated outputs.

### Numeric Outliers

Some numeric values may be scaled upward within bounded ranges. These values are
intended to look suspicious but remain within configured safety limits.

Affected columns:

| Table | Columns | Configured bounds |
| --- | --- | --- |
| `match_games` | `actual_team_one_score_share` | `0.0` to `1.0` |
| `match_teams` | `average_team_rating` | `0.0` to `5000.0` |
| `monthly_batches` | `active_player_count_start`, `new_player_count`, `active_player_count_end`, `match_count_generated`, `rating_update_count`, `assessment_update_count` | `0.0` to `1,000,000.0` |
| `player_assessment_history` | `assessment_value` | `0.0` to `5000.0` |
| `player_assessment_history` | `confidence_score` | `0.0` to `1.0` |

Pipeline considerations:

- Profile distributions before building rankings or forecasts.
- Flag values that are valid by type but suspicious by business context.
- Use domain checks, percentile checks, and cross-table reconciliation checks.
- Decide whether to cap, exclude, investigate, or retain outliers based on the
  analytical use case.

### Duplicate-Like Match Families

The tainted export may include duplicate-like competition records. These are
not duplicate primary keys. Instead, a selected match and its related rows are
cloned with new primary keys while preserving internal relationships.

Affected tables:

| Table | Effect |
| --- | --- |
| `matches` | Additional match rows that resemble existing matches. |
| `match_teams` | Related side rows cloned for the added matches. |
| `match_team_players` | Related player participation rows cloned for the added match sides. |
| `match_games` | Related game rows cloned for the added matches. |

Pipeline considerations:

- Primary-key uniqueness alone will not detect these records.
- Look for duplicate-like match signatures using combinations such as
  `match_date`, `region_id`, `match_type`, teams, players, and game scores.
- Evaluate whether duplicate-like rows should be retained, collapsed, or
  flagged depending on the downstream metric.
- Be careful when calculating match counts, win rates, player activity, and
  team performance.

## Tables Without Direct Field Mutation

`team_memberships` currently has no configured injection profile. It may still
be affected indirectly in analysis if related tables contain categorical,
rounding, outlier, or duplicate-like issues.

The following issue types exist in the injection framework but are not active in
the current baseline tainted student export:

- `timestamp_jitter`: date columns are protected by current safety rules.
- `delayed_rating_updates`: no standalone rating-history table is published in
  the current student contract.
- direct primary-key mutation
- direct foreign-key mutation
- required join-key nulling
- impossible score corruption
- hidden truth leakage

## Recommended Student Validation Checks

Students should build checks that cover at least the following areas:

| Area | Suggested checks |
| --- | --- |
| File integrity | Required files exist; Parquet files read successfully; row counts reconcile to `manifest.json`. |
| Schema integrity | Published columns match the manifest and assignment data dictionary. |
| Primary keys | Primary keys are populated and unique within each table. |
| Relationships | Foreign keys resolve across tables. |
| Optional missingness | Null rates are profiled and explained by column. |
| Categorical domains | Raw values are profiled; cleaned mappings are documented. |
| Text normalization | Names and descriptive labels are trimmed and standardized where useful. |
| Numeric distributions | Outliers and precision variants are profiled before analytics. |
| Match structure | Each match has coherent sides, players, games, and winner references. |
| Duplicate-like events | Competition records are checked for repeated-looking match families. |
| Temporal logic | Registration, formation, membership, rating, match, and dissolution dates are checked for plausible ordering. |
| Analytical sensitivity | Rankings and recommendations are tested for sensitivity to cleaning choices. |

## Recommended Pipeline Treatment

For a medallion-style workflow:

- Raw layer: retain the delivered Parquet files unchanged.
- Bronze layer: load all tables with ingestion metadata and manifest
  reconciliation.
- Silver layer: apply type normalization, categorical standardization,
  optional-null handling, deduplication flags, and relationship checks.
- Gold layer: build rankings, scorecards, tournament candidates, and dashboards
  using documented data quality assumptions.

Students should not assume that every suspicious value is wrong. The expected
standard is to profile the data, identify risks, make explicit cleaning
decisions, and explain how those decisions affect confidence in the final
recommendations.

