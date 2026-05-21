# Realism Audit Module Specification

## Status

Proposed specification for review.

## Purpose

This document defines the design for a standalone realism-audit module for the
pickleball simulation platform.

The purpose of the module is to evaluate whether generated simulation data
looks operationally plausible as dataset size increases, using reusable
SQL-backed audits that can run independently of the generation workflow.

This module is intended to assess realism in generated data before any workflow
integration, pipeline gating, UI exposure, or persistence of findings is added.

The module should be designed in a manner that supports future integration
into the overall data generation workflow 

---

# Core Design Decision

## Recommended First Implementation

The first implementation should be a standalone, report-only audit module.

Recommended flow:

```text
Generate synthetic data
        ↓
Run standalone realism audit pack against generation run / batch
        ↓
Review summary metrics, distributions, and outliers
        ↓
Tune generation logic or audit thresholds
        ↓
Integrate into workflow later if warranted
```

## Rationale

This is the preferred first step because it:

- avoids coupling new realism checks to the control plane too early
- allows rapid iteration on query design and thresholds
- lets us observe real generated-data behavior before defining hard gates
- reduces the risk of false failures while the generator logic is still maturing
- supports large-dataset inspection using database-native aggregation
- creates a reusable audit surface for manual review, automated tests, and later
  pipeline integration

The initial module should be descriptive first, not prescriptive first.

---

# Non-Goals for Initial Version

The first version should NOT:

- block monthly batch completion
- write findings into `validation_results`
- modify generated data
- modify configuration payloads
- require control-panel UI changes
- require new exposed config fields
- require export-layer integration
- define final production warning or blocker thresholds for every audit

Those concerns can be added after the standalone audit pack is stable.

---

# Scope

## In Scope

The module should support:

- reusable named audit queries
- generation-run scoped audits
- monthly-batch scoped audits
- SQL-first implementations for scalability
- report-only execution from a script or module API
- comparisons against current configuration snapshot where useful
- summary metrics, distributions, and outlier-oriented outputs
- deterministic interpretation of the same underlying dataset
- test coverage for audit execution and representative query results

## Out of Scope for Initial Implementation

The first version does not need:

- automatic persistence of findings
- severity-based pipeline stopping
- control-panel rendering
- asynchronous audit jobs
- cross-run trend warehousing
- instructor-only truth tables
- statistical modeling beyond pragmatic SQL summaries
- visualization dashboards

---

# Design Principles

The realism-audit module should follow these rules:

- Prefer SQL queries over Python row-by-row inspection.
- Prefer reportable aggregates over opaque pass/fail booleans.
- Compare generated outcomes to active configuration when the configuration is
  already consumed by live generation logic.
- Avoid audits for fields that are not currently populated by live logic.
- Keep the module reusable outside the monthly pipeline.
- Make outputs readable in both human and machine formats.
- Treat the first release as an audit pack, not a validation gate.
- Provide results in a format that allows inspection and review.

---

# Current Baseline

The codebase already contains an initial realism-audit scaffold with:

- a named query registry
- a runner that resolves parameters from `generation_runs.parameter_snapshot`
- a CLI script
- one focused SQLite test

The current baseline is useful but narrow. It covers:

- player roster summary
- club membership geography summary
- match type distribution
- weekend match share
- game competitiveness summary
- rating delta summary

The next step is to expand this into a practical first-pass audit pack that
covers the most important realism questions across players, clubs, matches,
scores, and ratings.

---

# Module Boundaries

## Inputs

Primary inputs:

- database connection / ORM session
- `generation_run_id` for run-scoped audits
- `batch_id` for batch-scoped audits
- active configuration snapshot from `generation_runs.parameter_snapshot`
- optional named query filters

These should default to the most recent run only.  The database will have
only one version of data, prior runs will have been purged.

## Outputs

Primary outputs:

- named audit result sets
- machine-readable JSON output
- human-readable tabular output
- summary-oriented metrics for review
- outlier rows where useful

## No Initial Persistent Outputs

The first version should not persist results to database tables.

In particular, it should not write to:

- `validation_results`
- `batch_runs`
- `job_stage_progress`

---

# Audit Taxonomy

The first-pass audit pack should be organized into the following categories.

## 1. Player Population Distribution Audits

Purpose:

- check whether generated player populations broadly match configured and
  expected shapes

Initial audit targets:

- total player count by generation run
- active / injured / inactive / retired status distribution
- gender distribution versus configured weights
- age-bucket distribution versus configured weights
- regional allocation distribution versus `regions.selection_probability`
- registration-month counts by batch
- initial rating distribution summary
- initial confidence summary

Recommended outputs:

- counts
- percentages
- configured target percentages where available
- absolute percentage-point drift
- top regional outliers
- percentile summaries for age and initial rating

## 2. Club Size and Capacity Audits

Purpose:

- check whether club usage looks plausible given seeded club supply and current
  assignment logic

Initial audit targets:

- players with zero club memberships
- players with more than one club membership
- players with multiple primary memberships
- memberships per club
- primary memberships per club
- total memberships versus `member_capacity`
- club fill ratio distribution
- clubs with implausibly high or low utilization
- clubs with zero memberships in high-population regions

Recommended outputs:

- fill ratio percentiles
- over-capacity club counts
- top overloaded clubs
- counts by club type if populated
- counts by region

## 3. Membership Geography and Locality Audits

Purpose:

- check whether club assignment respects locality expectations

Initial audit targets:

- primary memberships in home region versus outside home region
- secondary memberships in same region versus cross-region
- cross-region membership rate compared to
  `club_generation.cross_region_assignment_enabled`
- cross-region rate compared to
  `club_generation.secondary_membership_same_region_rate`
- regions with unusually high outbound or inbound membership flow

Recommended outputs:

- same-region percentages
- cross-region percentages
- counts by region pair for strongest cross-region flows
- exception tables for unusual patterns

## 4. Match Volume and Cadence Audits

Purpose:

- check whether generated match activity looks operationally plausible across
  batches and teams

Initial audit targets:

- matches per batch
- matches by match type
- matches by day of week
- weekend share versus configured weekend range
- matches per team per month
- teams with zero matches in an active batch
- teams exceeding configured daily match caps
- region-level match concentration
- monthly cadence distribution across the historical window

Recommended outputs:

- counts and percentages
- average and percentile matches per team
- daily cap violations
- top heavy-use teams
- top underused teams

## 5. Score Competitiveness Audits

Purpose:

- check whether game and match scorelines look plausible given matchmaking and
  score-generation logic

Initial audit targets:

- average game margin
- game margin distribution
- extended-game rate
- straight-target wins versus extended wins
- points played per match
- upset rate relative to predicted winner
- expected competitiveness versus actual score closeness
- match-type differences in competitiveness

Recommended outputs:

- margin percentiles
- extended-game percentages
- upset percentages
- score-share drift summaries
- comparison of predicted win probability buckets to actual outcomes

## 6. Rating Movement and Outlier Audits

Purpose:

- check whether rating movement magnitude and direction look plausible

Initial audit targets:

- average absolute rating delta
- max absolute rating delta
- large-delta rate versus configured threshold
- delta distribution by batch
- delta distribution by player confidence band
- delta distribution by rating band
- confidence progression summaries
- players with repeated extreme rating swings
- ratings pushed to configured min or max bounds

Recommended outputs:

- percentile summaries
- threshold counts
- top outlier players
- confidence-before versus delta summaries
- batch-level movement comparisons

---

# Query Design Requirements

Each audit query should have explicit metadata.

Minimum metadata:

- query name
- scope: `generation_run` or `batch`
- plain-language description
- required parameters
- tags

Optional metadata for the expanded design:

- category
- intended audience
- related configuration keys
- suggested severity if later integrated into validation workflow
- whether the query is summary-only or outlier-oriented

## Query Conventions

Queries should:

- return deterministic row sets for the same data
- use explicit ordering for multi-row outputs
- avoid dialect-specific SQL unless necessary
- supply dialect-specific variants only when required
- return numeric drift values where comparisons are made
- avoid mixing too many unrelated concepts into one result set

The goal is composable audits, not one giant audit query.

---

# Configuration Awareness

The module should read from the frozen run snapshot where useful, not from
mutable live defaults alone.

The first-pass audit pack should compare against snapshot values for settings
already used by current live generation logic, including where applicable:

- player count
- age distribution
- gender weights
- player status weights
- weekend concentration bounds
- match type weights
- club unaffiliated rate
- multi-club membership rate
- same-region secondary membership rate
- rating movement warning threshold

If a value is missing from the snapshot, the module may fall back to the
application default payload.

---

# Output Formats

The standalone module should support at least:

- human-readable table output
- JSON output

## Table Output

Table output should be optimized for quick operator review:

- grouped by audit query
- stable column ordering
- readable numeric formatting
- explicit indication when no rows are returned

## JSON Output

JSON output should be optimized for:

- test assertions
- future automation
- later UI or persistence integration

Recommended JSON shape:

```json
[
  {
    "query": "player_age_distribution",
    "scope": "generation_run",
    "description": "Observed age-bucket mix versus configured target weights.",
    "rows": [
      {
        "age_bucket": "45_59",
        "player_count": 12345,
        "player_pct": 31.82,
        "configured_pct": 32.0,
        "pct_point_drift": -0.18
      }
    ]
  }
]
```

---

# Severity Model

The standalone module should not enforce blocking behavior yet, but the spec
should define a future-compatible severity model.

Recommended future severities:

- `info`
- `warning`
- `error`
- `blocker`

## Initial Handling

For the standalone module:

- severities may be documented in query metadata later
- outputs should remain report-only
- no batch or run should fail because of audit findings yet

This keeps the first iteration focused on trust-building and threshold tuning.

---

# Suggested First-Pass Query List

The following named queries are recommended for the first implementation wave.

## Generation-Run Scoped

- `player_roster_summary`
- `player_status_distribution`
- `player_gender_distribution`
- `player_age_distribution`
- `player_region_distribution`
- `player_registration_by_batch`
- `initial_rating_distribution_summary`
- `club_membership_summary`
- `club_primary_membership_integrity`
- `club_fill_ratio_summary`
- `club_fill_ratio_outliers`
- `club_membership_geography`
- `cross_region_membership_flows`

## Batch Scoped

- `match_volume_summary`
- `match_type_distribution`
- `match_day_of_week_distribution`
- `weekend_match_share`
- `matches_per_team_distribution`
- `daily_team_match_cap_violations`
- `batch_region_match_distribution`
- `game_competitiveness_summary`
- `game_margin_distribution`
- `upset_rate_summary`
- `predicted_vs_actual_outcome_buckets`
- `rating_delta_summary`
- `rating_delta_distribution`
- `rating_delta_by_confidence_band`
- `rating_outlier_players`

This list is intentionally practical rather than exhaustive.

---

# Recommended Implementation Phases

## Phase 1

Build the standalone audit pack only.

Deliverables:

- expanded query registry
- query metadata
- standalone runner API
- CLI support for named query execution
- JSON and table outputs
- test coverage for representative audits

## Phase 2

Tune realism expectations against larger generated datasets.

Deliverables:

- drift thresholds refined using observed outputs
- redundant or low-value audits removed
- naming and output cleanup

## Phase 3

Optional workflow integration.

Possible future deliverables:

- pipeline invocation after generation
- persistence into `validation_results`
- severity-based summaries
- operator UI surfacing

Integration should happen only after the standalone pack proves useful.

---

# Testing Requirements

Minimum tests for the module should include:

- audit runner executes named queries on SQLite
- parameter resolution reads from `generation_runs.parameter_snapshot`
- configuration comparisons compute expected drift correctly
- unknown query names fail clearly
- missing required scope parameters fail clearly
- representative generation-run queries return expected rows
- representative batch queries return expected rows
- empty-result queries return stable output

## Recommended Additional Tests

- large synthetic fixture for club fill-ratio behavior
- weekend share calculations on both SQLite and PostgreSQL-compatible SQL
- cross-region membership edge cases
- rating outlier detection edge cases
- score competitiveness edge cases such as extended games and upset-heavy batches

---

# Performance Expectations

The realism-audit module should be designed for larger generated datasets.

Performance guidance:

- push aggregation into SQL
- avoid loading full tables into Python
- prefer grouped summaries and targeted outlier extracts
- avoid correlated subqueries where simpler CTEs or grouped joins suffice
- ensure queries align with existing indexed join keys where possible

Initial success criteria:

- the audit pack runs comfortably against a materially larger dataset than the
  small test fixtures
- individual queries remain understandable and maintainable

---

# Review Questions

Before implementation, the following points should be confirmed:

1. Should the first version remain entirely report-only with no persistence?
2. Which audits are mandatory for wave one versus nice-to-have?
3. Should drift comparisons be strict percentages, percentile-based, or both?
4. Should the first pass focus only on run and batch summaries, or also include
   detailed outlier row extracts?
5. Should any future severity defaults be documented now, or deferred until
   after first real-data review?

---

# Recommendation

Proceed by building the realism-audit module as an independent, SQL-backed,
report-only component first.

The first implementation should prioritize:

- player population distribution checks
- club size and capacity sanity checks
- membership geography and locality checks
- match volume and cadence checks
- score competitiveness checks
- rating movement and outlier checks

Only after reviewing outputs from a larger generated dataset should we decide
how much of this should become persisted validation or workflow enforcement.
