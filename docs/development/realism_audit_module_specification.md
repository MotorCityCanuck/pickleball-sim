# Realism Audit Module Specification

## Status

Current implementation specification.

This document describes the realism-audit module as implemented in the current
repository. It is aligned to:

- `backend/app/generation/realism_audit.py`
- `backend/app/generation/realism_audit_service.py`
- `backend/app/generation/realism_audit_report.py`
- `backend/app/generation/realism_audit_assessment.py`
- `backend/app/generation/realism_audit_checkpoints.py`
- `backend/app/generation/realism_audit_job_handler.py`
- `backend/app/generation/realism_audit_history.py`
- `backend/app/web/routes.py`
- `backend/app/web/control_panel_queries.py`
- `scripts/run_realism_audits.sh`

The module is no longer only a proposed standalone audit pack. It supports both
standalone CLI execution and durable control-panel execution with per-query
checkpointing.

## Purpose

The realism-audit module evaluates whether generated simulation data looks
operationally plausible as dataset size increases.

The audit pack is SQL-backed and focuses on reusable aggregate, distribution,
drift, integrity, and outlier checks across:

- players
- clubs and memberships
- matches and scheduling
- teams and partner continuity
- game scores
- rating movement

Realism audit findings are advisory. They help tune generation logic and
configuration. They do not currently block monthly generation or student
dataset export.

## Operating Modes

### Standalone CLI

The command wrapper is:

```bash
./scripts/run_realism_audits.sh
```

Supported options:

- `--list-queries`: list registered query names, scopes, categories, and
  descriptions.
- `--query <name>`: run one named query; repeat to run multiple queries.
- `--format table`: print human-readable tables. This is the default.
- `--format json`: print JSON-ready result payloads.
- `--snapshot-dir <path>`: choose where JSON snapshots are written.
- `--no-save-snapshot`: run without writing a snapshot file.

The CLI uses the latest auditable generation run and latest batch in that run.
Historical run or batch targeting is intentionally not exposed by the wrapper.

### Control Panel

The control panel can queue a durable realism-audit job from the orchestration
tab.

Control-panel execution:

- registers a `job_status` row with `job_type = 'realism_audit'`;
- registers one `job_stage_progress` row for the audit stage;
- creates one `ops.realism_audit_query_runs` checkpoint row per registered
  query;
- executes queries through the durable worker;
- can resume interrupted jobs by skipping succeeded checkpoints and resetting
  interrupted `running` checkpoints to `pending`;
- saves a JSON snapshot after all checkpoints succeed;
- exposes progress, lease state, latest completed query, summary assessment,
  and report download in the UI.

The control panel permits a realism audit only when:

- a generation run exists;
- the generation run status is `succeeded`;
- seed/reference readiness is restored;
- all monthly batches have `processing_status = 'succeeded'`;
- no write-heavy generation job is pending or running;
- no seed preparation job is active;
- no student dataset export is active;
- no realism audit is already active.

## Module Boundaries

## Inputs

Primary inputs:

- SQLAlchemy `Session`;
- latest generation run with monthly batches;
- latest monthly batch for that generation run;
- `generation_runs.parameter_snapshot`;
- application default configuration as fallback;
- optional named query list.

The parameter resolver reads from the frozen run snapshot where available, then
falls back to `DEFAULT_CONFIG_PAYLOAD`.

## Outputs

Primary outputs:

- `RealismAuditResult` objects from the runner;
- table or JSON output from the CLI;
- JSON snapshots under `data/realism_audit_snapshots/` by default;
- Markdown reports downloaded from the control panel under
  `data/realism_audit_reports/` by default;
- UI-ready summary state derived from latest snapshot payloads;
- per-query checkpoint rows for durable jobs.

## Persistent State

The module currently writes operational audit-execution state, but not
student-facing validation records.

Persistent execution state:

- `job_status`
- `job_stage_progress`
- `ops.realism_audit_query_runs`
- filesystem JSON snapshots in `data/realism_audit_snapshots/`
- filesystem Markdown reports in `data/realism_audit_reports/` when downloaded

The module does not write to `validation_results`, mutate generated data, or
modify configuration payloads.

## Query Model

Each query is registered as a `RealismAuditQuery` with:

- `name`
- `scope`: `generation_run` or `batch`
- `description`
- `sql`: a SQL string or dialect map
- `required_params`
- `tags`
- `category`
- `related_config_keys`
- optional `post_process`

The runner selects all queries by default. If query names are supplied, it runs
only those queries and fails clearly for unknown names.

Query execution rules:

- resolve required parameters before execution;
- select SQL by database dialect when a dialect-specific query exists;
- return deterministic row sets where queries produce multiple rows;
- post-process target/drift columns where applicable;
- avoid Python row-by-row table scans.

The `team_partner_continuity_by_batch` query uses helper rows from
`audit_batch_team_rosters` when available and falls back to legacy team
lifecycle reconstruction when helper rows are absent.

## Current Query Registry

The current registry contains 45 queries.

| Query | Scope | Category | Purpose |
| --- | --- | --- | --- |
| `player_roster_summary` | generation_run | players | Top-line roster counts and membership coverage. |
| `player_status_distribution` | generation_run | players | Player status mix versus configured weights. |
| `player_gender_distribution` | generation_run | players | Gender mix versus configured weights. |
| `player_age_distribution` | generation_run | players | Creation-time age buckets versus configured weights. |
| `player_registration_age_distribution` | generation_run | players | Age buckets at stored registration date. |
| `player_region_distribution` | generation_run | players | Home-region allocation versus region selection weights. |
| `player_registration_by_batch` | generation_run | players | Registration counts by monthly batch. |
| `player_name_uniqueness_summary` | generation_run | players | Distinct names and duplicate full-name concentration. |
| `player_first_name_alignment` | generation_run | players | First-name alignment to state/year/gender references. |
| `player_last_name_alignment` | generation_run | players | Last-name alignment to state/province and country references. |
| `initial_rating_distribution_summary` | generation_run | ratings | Initial rating distribution and elite-rate summary. |
| `club_membership_summary` | generation_run | clubs | Club affiliation and multi-club summary. |
| `club_primary_membership_integrity` | generation_run | clubs | Primary membership integrity. |
| `club_fill_ratio_summary` | generation_run | clubs | Club fill ratio versus configured maximum. |
| `club_fill_ratio_outliers` | generation_run | clubs | Highest-loaded club outliers. |
| `club_membership_geography` | generation_run | clubs | Secondary-membership locality and cross-region pressure. |
| `cross_region_membership_flows` | generation_run | clubs | Largest cross-region membership flows. |
| `match_volume_by_batch` | generation_run | matches | Per-batch match volume trend. |
| `match_volume_summary` | batch | matches | Batch match volume and day coverage. |
| `match_type_distribution` | batch | matches | Batch match-type mix versus configured weights. |
| `match_team_pairing_source_distribution` | batch | matches | Match-side source mix by pairing source. |
| `match_day_of_week_distribution` | batch | matches | Batch day-of-week distribution. |
| `weekend_match_share` | batch | matches | Weekend concentration versus configured validation bounds. |
| `matches_per_team_distribution` | batch | matches | Match volume across active team rosters. |
| `team_partner_continuity_by_batch` | generation_run | teams | Active-roster continuity relative to prior batch. |
| `matches_per_player_distribution` | batch | matches | Monthly match volume across active players. |
| `repeat_partner_match_distribution` | batch | matches | Prior same-partner match-count distribution. |
| `zero_match_players_by_registration_cohort` | batch | matches | Zero-match players by registration timing. |
| `zero_match_players_by_team_membership` | batch | matches | Zero-match players by team-membership coverage. |
| `zero_match_players_by_competitive_team_status` | batch | matches | Zero-match players by competitive team coverage. |
| `team_assignment_delay_summary` | batch | teams | Delay from player registration to first team assignment. |
| `zero_match_players_by_ad_hoc_eligibility` | batch | matches | Zero-match players by ad hoc eligibility. |
| `zero_match_players_by_club_affiliation` | batch | matches | Zero-match players by club affiliation. |
| `daily_team_match_cap_violations` | batch | matches | Active teams exceeding same-day match cap. |
| `batch_region_match_distribution` | batch | matches | Region-level match concentration. |
| `game_competitiveness_summary` | batch | scores | Game margin and extension-rate summary. |
| `game_margin_distribution` | batch | scores | Per-game score-margin distribution. |
| `upset_rate_summary` | batch | scores | Upset rate relative to predicted favorite. |
| `predicted_vs_actual_outcome_buckets` | batch | scores | Favorite win rate by predicted-probability bucket. |
| `rating_summary_by_batch` | generation_run | ratings | Per-batch rating summary and spread trend. |
| `rating_band_distribution_by_batch` | generation_run | ratings | Per-batch rating-band distribution. |
| `rating_delta_summary` | batch | ratings | Batch rating movement versus configured warning threshold. |
| `rating_delta_distribution` | batch | ratings | Absolute rating-delta distribution. |
| `rating_delta_by_confidence_band` | batch | ratings | Rating movement by confidence band. |
| `rating_outlier_players` | batch | ratings | Largest individual rating swings. |

## Configuration Awareness

The audit parameter resolver currently reads these configuration-backed values:

| Parameter | Config path | Default fallback |
| --- | --- | --- |
| weekend lower bound | `validation.weekend_concentration_min` | `0.40` |
| weekend upper bound | `validation.weekend_concentration_max` | `0.60` |
| rating delta warning threshold | `ratings.rating_movement_warning_threshold` | `300` |
| initial elite rating minimum | `ratings.initial_rating_elite_min` | `4000` |
| max club fill ratio | `club_generation.max_club_fill_ratio` | `1.0` |
| unaffiliated player rate | `club_generation.unaffiliated_player_rate` | `0.12` |
| multi-club membership rate | `club_generation.multi_club_membership_rate` | `0.06` |
| secondary same-region membership rate | `club_generation.secondary_membership_same_region_rate` | `0.85` |
| cross-region assignment enabled | `club_generation.cross_region_assignment_enabled` | `false` |
| max daily matches per team | `match_scheduling.max_daily_matches_per_team` | `2` |
| monthly matches per active player mean | `match_scheduling.monthly_matches_per_active_player_mean` | `8.0` |
| monthly matches per active player standard deviation | `match_scheduling.monthly_matches_per_active_player_std_dev` | `4.0` |
| match volume noise factor | `match_scheduling.match_volume_noise_factor` | `0.15` |
| player status target percentages | `player_generation.player_status_weights` | empty map if unavailable |
| gender target percentages | `player_generation.gender_weights` | empty map if unavailable |
| age-bucket target percentages | `player_generation.age_distribution` | empty map if unavailable |
| match-type target percentages | `match_types.weights` | empty map if unavailable |

Current application defaults for the main distribution maps are:

- `player_generation.player_status_weights`: `ACTIVE` 94%, `INJURED` 2%,
  `INACTIVE` 2%, `RETIRED` 2%.
- `player_generation.gender_weights`: `M` 50%, `F` 50%.
- `player_generation.age_distribution`: `under_18` 4%, `18_29` 24%,
  `30_44` 32%, `45_59` 24%, `60_74` 13%, `75_plus` 3%.
- `match_types.weights`: `recreational` 55%, `league` 20%, `ladder` 10%,
  `tournament` 10%, `challenge` 4%, `clinic` 1%.

## Assessment Model

Audit assessment is rule-based and report-only. It produces:

- `overall_status`
- `finding_count`
- `severity_counts`
- `category_counts`
- `findings`
- `query_assessments`
- active threshold values

Supported severities:

- `info`
- `warning`
- `error`
- `blocker`

Current overall status mapping:

- max severity `info`: `no_material_issues`
- max severity `warning`: `review_recommended`
- max severity `error` or `blocker`: `significant_realism_concerns`

Default assessment thresholds:

| Threshold | Default |
| --- | --- |
| `distribution_drift_warning_pct_points` | `5.0` |
| `distribution_drift_error_pct_points` | `10.0` |
| `summary_drift_warning_pct_points` | `5.0` |
| `summary_drift_error_pct_points` | `10.0` |
| `duplicate_full_name_warning_pct` | `1.0` |
| `name_alignment_min_reference_pct` | `90.0` |
| `rating_large_delta_warning_pct` | `1.0` |
| `rating_large_delta_error_pct` | `5.0` |
| `rating_outlier_warning_delta` | `250.0` |
| `unteamed_duration_warning_days` | `30.0` |

The control panel lets the operator submit these thresholds when queueing an
audit. The durable job stores normalized threshold values on the audit stage
metadata and uses them when saving the final snapshot.

## Snapshot Format

Saved JSON snapshots use this high-level shape:

```json
{
  "executed_at": "2026-06-20T13:43:51+00:00",
  "generation_run_id": 64,
  "batch_id": 611,
  "batch_month": "2025-12-01",
  "results": [
    {
      "query": "player_status_distribution",
      "scope": "generation_run",
      "category": "players",
      "description": "Observed player-status distribution versus configured weights.",
      "tags": ["players", "distribution"],
      "related_config_keys": ["player_generation.player_status_weights"],
      "rows": []
    }
  ],
  "assessment": {
    "overall_status": "review_recommended",
    "finding_count": 1,
    "severity_counts": {
      "info": 44,
      "warning": 1,
      "error": 0,
      "blocker": 0
    },
    "findings": [],
    "query_assessments": []
  },
  "snapshot_path": "data/realism_audit_snapshots/generation_run_000064/...",
  "snapshot_version": 1,
  "query_count": 45
}
```

The CLI `--format json` output prints only serialized results. The saved
snapshot contains execution metadata, assessment, path, version, and query
count.

## Design Principles

The implemented module follows these rules:

- Prefer SQL aggregation over Python row-by-row inspection.
- Keep queries composable and named.
- Keep output deterministic for repeatable review.
- Compare generated outcomes to the frozen run snapshot when relevant.
- Fall back to application defaults only when snapshot values are unavailable.
- Keep realism findings advisory rather than blocking.
- Preserve generated data; audits must never mutate simulation tables.
- Keep durable job progress recoverable at query granularity.

## Current Limitations

Known boundaries:

- The public CLI intentionally targets only the latest auditable run and latest
  batch.
- Assessment rules are heuristic and intentionally conservative.
- Findings are not persisted to `validation_results`.
- The control panel queues all registered queries; named-query selection is CLI
  only.
- Some historical runs may lack `audit_batch_team_rosters`; continuity audits
  use a legacy fallback in that case.
- The module assesses generated-data realism, not student-export Parquet
  validity. Export validation remains separate.

## Testing Requirements

The current test suite should continue to cover:

- query registry execution;
- parameter resolution from `generation_runs.parameter_snapshot`;
- config-target drift post-processing;
- unknown query failure behavior;
- required parameter failure behavior;
- representative generation-run and batch query outputs;
- empty-result stability;
- assessment severity classification;
- snapshot serialization and Markdown rendering;
- durable checkpoint creation, success, failure, and resume behavior;
- control-panel run gating and progress summaries.

Representative test files:

- `backend/tests/test_realism_audit.py`
- `backend/tests/test_realism_audit_checkpoints.py`
- `backend/tests/test_realism_audit_job_handler.py`
- `backend/tests/test_control_panel_queries.py`
- `backend/tests/test_control_panel_routes.py`

## Performance Expectations

The realism-audit module is intended for large generated datasets.

Performance guidance:

- push aggregation into SQL;
- keep result sets summary-oriented or explicitly outlier-limited;
- preserve indexes used by generation-run, batch, player, team, and match joins;
- avoid full ORM object materialization in query execution;
- prefer helper tables such as `audit_batch_team_rosters` where they avoid
  repeatedly reconstructing expensive historical state.

## Extension Guidance

Future changes should be narrow and tied to observed audit gaps.

Reasonable extensions:

- add a new query with complete `RealismAuditQuery` metadata;
- add dialect-specific SQL only when needed;
- add post-processing when a query compares observed percentages to config
  targets;
- add assessment rules only after reviewing real generated outputs;
- expose named-query subsets in the control panel if full audit runtime becomes
  operationally expensive.

Avoid:

- turning advisory findings into generation blockers without calibration;
- writing realism findings into student-facing exports;
- duplicating export-validation logic in the realism audit pack;
- using live mutable defaults instead of the run snapshot when snapshot values
  exist.
