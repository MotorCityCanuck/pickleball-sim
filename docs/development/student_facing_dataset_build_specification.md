# Student-Facing Dataset Build Specification

## Status

Current implementation specification for the baseline-plus-incremental student
dataset export.

Canonical document path:

```text
docs/development/student_facing_dataset_build_specification.md
```

## Purpose

This document defines the student-facing analytical dataset exported from the
pickleball simulation database.

The release format is a family of Parquet folders:

- one historical baseline release,
- zero or more monthly incremental releases,
- a manifest in each release folder,
- a schema designed for DuckDB-based ingestion and analysis.

The export is intentionally stricter than the source database. Operational
tracking, raw seed inputs, hidden generator variables, privileged scoring
mechanics, and tournament internals are excluded.

## Release Family Model

The export produces one baseline plus monthly incrementals.

- The baseline release contains both snapshot and fact data for the first
  `initial_history_month_count` monthly batches.
- Each later release contains:
  - snapshot-scoped dimensions as of the newest month in scope,
  - fact rows for exactly one new monthly batch.

This means the monthly releases are not complete re-exported snapshots. They
are intended to be applied after loading the baseline.

The current folder naming contract is:

```text
<release_name>_initial_history
<release_name>_snapshot_YYYY_MM
```

The `_snapshot_YYYY_MM` suffix is retained for compatibility even though the
release type is a monthly incremental.

Example with `initial_history_month_count = 12` and
`subsequent_month_count = 3`:

| Release folder | Snapshot batch sequences | Fact batch sequences |
| --- | --- | --- |
| `<release_name>_initial_history` | `1..12` | `1..12` |
| `<release_name>_snapshot_2026_01` | `1..13` | `13` |
| `<release_name>_snapshot_2026_02` | `1..14` | `14` |
| `<release_name>_snapshot_2026_03` | `1..15` | `15` |

## Build Parameters

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `generation_run_id` | integer | yes | Source generation run to export. |
| `initial_history_month_count` | integer | yes | Number of monthly batches included in the baseline release. Default operator value is `12`. |
| `subsequent_month_count` | integer | yes | Number of monthly incremental releases to produce after the baseline. |
| `output_root` | path/string | yes | Directory where the release-family folders are written. |
| `release_name` | string | yes | Base name used to derive concrete release folder names. |
| `data_quality_level` | string | no | Release quality level. Current clean export uses `clean`. |
| `overwrite_existing` | boolean | no | Whether an existing release family may be replaced. Default is `false`. |

## Output Files

Every concrete release folder contains exactly these student-facing Parquet
files:

```text
clubs.parquet
club_memberships.parquet
match_games.parquet
match_team_players.parquet
match_teams.parquet
matches.parquet
monthly_batches.parquet
player_assessment_history.parquet
player_master.parquet
player_registrations.parquet
regions.parquet
team_memberships.parquet
teams.parquet
manifest.json
```

`player_master.parquet` is a derived export projection. The release no longer
publishes `players.parquet` or `player_rating_history.parquet`.

## Included and Excluded Scope

Included student-facing tables:

| Output table | Purpose |
| --- | --- |
| `clubs` | Club and facility dimension. |
| `club_memberships` | Player-to-club relationship history projected to snapshot state. |
| `match_games` | Game-level fact rows. |
| `match_team_players` | Player participation in match teams. |
| `match_teams` | Match-side fact rows. |
| `matches` | Match-level fact rows. |
| `monthly_batches` | Batch metadata for the fact window in the release. |
| `player_assessment_history` | Player assessment fact rows for the fact window. |
| `player_master` | Snapshot-scoped player dimension with latest rating state. |
| `player_registrations` | Player registration fact rows for the fact window. |
| `regions` | Geographic dimension referenced by exported rows. |
| `team_memberships` | Player-to-team relationship history projected to snapshot state. |
| `teams` | Team dimension projected to snapshot state. |

Explicitly excluded source tables include:

- `player_rating_history`
- `ratings_update_log`
- generation and export job tables
- raw seed tables
- uploaded file and validation tables
- tournament tables

## Snapshot Scope vs Fact Scope

Every release carries two batch scopes:

| Scope | Meaning | Used by |
| --- | --- | --- |
| `snapshot_batch_sequences` | All batches from `1` through the release month | `player_master`, as-of dimensions, temporal validations |
| `fact_batch_sequences` | Only the batch sequences emitted in this release folder | `monthly_batches`, `matches`, `match_teams`, `match_team_players`, `match_games`, batch-tied histories |

Derived values:

- `snapshot_month`: newest `monthly_batches.batch_month` in snapshot scope
- `snapshot_end_exclusive`: first day of the next month after `snapshot_month`

## Query and Filter Contract

The exporter must use these release-scope rules:

| Output table | Required filter basis |
| --- | --- |
| `player_master` | Players registered before `snapshot_end_exclusive`; latest rating row before `snapshot_end_exclusive`; one row per included player. |
| `matches` | `batch_id` in fact batch ids. |
| `match_teams` | `match_id` in included matches. |
| `match_team_players` | `match_team_id` in included match teams. |
| `match_games` | `match_id` in included matches. |
| `monthly_batches` | Batch rows in fact batch ids. |
| `player_registrations` | `batch_id` in fact batch ids and `player_id` in included `player_master`. |
| `player_assessment_history` | `batch_id` in fact batch ids and `player_id` in included `player_master`. |
| `clubs` | Clubs founded before `snapshot_end_exclusive`, plus clubs referenced by included memberships. |
| `club_memberships` | Memberships joined before `snapshot_end_exclusive`; future `end_date` values projected as null. |
| `teams` | Teams formed before `snapshot_end_exclusive`; future dissolution state projected to the as-of snapshot. |
| `team_memberships` | Memberships joined before `snapshot_end_exclusive`; future `left_date` values projected as null. |
| `regions` | Regions referenced by exported player, club, registration, or match rows. |

## `player_master` Contract

`player_master.parquet` is the student-facing player dimension.

Source composition:

- static identity from `players`,
- latest rating state from `player_rating_history` before
  `snapshot_end_exclusive`,
- release metadata column `snapshot_month`.

Published columns, in order:

1. `player_id`
2. `external_player_key`
3. `first_name`
4. `last_name`
5. `gender`
6. `birth_date`
7. `dominant_hand`
8. `home_region_id`
9. `registration_date`
10. `player_status`
11. `rating_value`
12. `confidence_score`
13. `volatility_score`
14. `global_percentile`
15. `match_count_used`
16. `rating_date`
17. `rating_batch_id`
18. `snapshot_month`

`player_master` replaces direct publication of `players` and
`player_rating_history` in the student contract.

## DuckDB Access and Ingestion Model

Minimum expected ingestion flow:

1. Load the baseline folder.
2. Create or replace the student-facing `player_master` table from
   `player_master.parquet`.
3. Append baseline match-related and batch-tied fact tables.
4. For each monthly incremental:
   - upsert `player_master` by `player_id`,
   - append `monthly_batches`,
   - append `matches`, `match_teams`, `match_team_players`, and `match_games`,
   - append `player_registrations` and `player_assessment_history`,
   - reject a fact batch that has already been loaded.

Baseline folders are independently queryable. Incremental folders are intended
to be applied on top of an already-loaded baseline.

Minimum supported DuckDB access pattern:

```sql
CREATE VIEW player_master AS
SELECT * FROM read_parquet('student_release/player_master.parquet');

CREATE VIEW matches AS
SELECT * FROM read_parquet('student_release/matches.parquet');
```

## Manifest Contract

Each release folder must contain `manifest.json` with, at minimum, these
fields:

| Field | Meaning |
| --- | --- |
| `release_name` | Concrete release folder name. |
| `release_mode` | `baseline` or `monthly_incremental`. |
| `release_type` | `historical_baseline` or `monthly_incremental`. |
| `student_dataset_schema_version` | Student export schema version. |
| `source_generation_run_id` | Source generation run identifier. |
| `included_batch_sequences` | Compatibility alias for `fact_batch_sequences`. |
| `included_batch_months` | Compatibility alias for fact-batch months. |
| `snapshot_batch_sequences` | Snapshot batch scope. |
| `snapshot_batch_months` | Snapshot batch months. |
| `fact_batch_sequences` | Fact batch scope. |
| `fact_batch_months` | Fact batch months. |
| `snapshot_month` | Newest month in snapshot scope. |
| `snapshot_end_exclusive` | First day after `snapshot_month`. |
| `build_parameters` | Export request parameters. |
| `output_files` | Per-file path, row count, columns, schema hash, and checksum. |
| `row_counts` | Per-table row counts. |
| `ordered_columns` | Per-table ordered column list. |
| `schema_hashes` | Per-table schema hashes. |
| `file_checksums` | Per-table file checksums. |
| `validation_status` | Validation result summary status. |
| `validation_summary` | Detailed validation checks. |

## Validation Requirements

The exporter must validate the staged release with DuckDB before promotion.

Required checks:

- every expected Parquet file exists,
- no excluded or unexpected Parquet file exists,
- every expected file is readable in DuckDB,
- every file column list matches the documented order,
- manifest row counts match the actual Parquet row counts,
- required non-empty tables are populated,
- referential integrity checks pass,
- `player_master` has one row per `player_id`,
- `player_master.snapshot_month` matches the release `snapshot_month`,
- `player_master.rating_date` is null or before `snapshot_end_exclusive`,
- each match has exactly two `match_teams`,
- each `match_team` has at least one `match_team_players` row,
- batch-tied fact rows resolve only to included `monthly_batches`,
- snapshot-scoped dates do not leak future state.

Required non-empty tables:

- `clubs`
- `club_memberships`
- `match_games`
- `match_team_players`
- `match_teams`
- `matches`
- `monthly_batches`
- `player_master`
- `player_registrations`
- `regions`
- `team_memberships`
- `teams`

`player_assessment_history` may be empty.

## Referential Integrity Contract

The exported Parquet files must preserve these relationships:

| Child table | Child column | Parent table | Parent column |
| --- | --- | --- | --- |
| `clubs` | `region_id` | `regions` | `id` |
| `club_memberships` | `player_id` | `player_master` | `player_id` |
| `club_memberships` | `club_id` | `clubs` | `id` |
| `matches` | `region_id` | `regions` | `id` |
| `matches` | `batch_id` | `monthly_batches` | `id` |
| `matches` | `winning_team_id` | `match_teams` | `id` |
| `match_games` | `match_id` | `matches` | `id` |
| `match_teams` | `match_id` | `matches` | `id` |
| `match_team_players` | `match_team_id` | `match_teams` | `id` |
| `match_team_players` | `player_id` | `player_master` | `player_id` |
| `player_assessment_history` | `player_id` | `player_master` | `player_id` |
| `player_assessment_history` | `batch_id` | `monthly_batches` | `id` |
| `player_registrations` | `player_id` | `player_master` | `player_id` |
| `player_registrations` | `batch_id` | `monthly_batches` | `id` |
| `player_registrations` | `assigned_region_id` | `regions` | `id` |
| `player_master` | `home_region_id` | `regions` | `id` |
| `team_memberships` | `team_id` | `teams` | `id` |
| `team_memberships` | `player_id` | `player_master` | `player_id` |

## Failure and Cleanup Behavior

The exporter must write into a staging directory first.

Required flow:

1. Create a unique staging root under `output_root`.
2. Write all release folders under that staging root.
3. Validate each staged release folder with DuckDB.
4. Promote the staged family only after validation passes.
5. Leave the final output untouched if validation fails.

Partial final releases must not appear in the destination root.

## Schema Version

Current schema version:

```text
student_dataset_schema_version = 1.3
```

Any change to exported tables, column names, column order, meanings, filter
semantics, or manifest contract must increment this version.

## Testing Requirements

The release contract is covered by:

- `backend/tests/test_student_dataset_release_windows.py`
- `backend/tests/test_student_dataset_projection.py`
- `backend/tests/test_student_dataset_queries.py`
- `backend/tests/test_student_dataset_writer.py`
- `backend/tests/test_student_dataset_service.py`
- `backend/tests/test_control_panel_routes.py`
- `scripts/student_dataset_duckdb_quality_check.sql`
