# Student Dataset Incremental Export Review

## Context

This review covers the database structures and application pipelines involved in rating calculation and student-facing dataset exports.

The proposed change is to provide students with:

- one initial 12-month historical dataset,
- monthly incremental releases after that baseline,
- a player master file containing static player data plus ratings as of the end of the associated month,
- separate match and game data files,
- a repeatable ingestion pattern where students load the baseline and then apply monthly increments.

## Current State

### Rating Calculation

The rating calculation pipeline does not need a structural rewrite for this proposal.

Ratings are generated after monthly matches are created. `RatingUpdateGenerator` applies match-driven updates for one monthly batch at a time, using the latest available prior rating state for each player and then writing:

- event-level rows to `player_rating_history`,
- per-player, per-match audit rows to `ratings_update_log`,
- monthly summary counts back to `monthly_batches.rating_update_count`.

The `players` table intentionally stores static identity attributes only. Mutable rating state lives in `player_rating_history`.

Relevant files:

- `backend/app/generators/ratings.py`
- `backend/app/models/players.py`
- `backend/app/models/player_rating_history.py`
- `backend/app/models/ratings_update_log.py`
- `backend/app/generation/monthly_pipeline.py`

### Current Student Export Shape

The student dataset export is currently table-history based. The explicit projection contract emits normalized Parquet tables such as:

- `players`
- `player_rating_history`
- `player_registrations`
- `matches`
- `match_teams`
- `match_team_players`
- `match_games`
- `monthly_batches`
- clubs, regions, teams, and memberships

`ratings_update_log` is intentionally excluded from the student dataset.

Relevant files:

- `backend/app/exports/student_dataset/projection.py`
- `backend/app/exports/student_dataset/queries.py`
- `backend/app/exports/student_dataset/writer.py`
- `backend/app/exports/student_dataset/validation.py`

### Current Release Window Behavior

The current export code already supports an initial history release plus later monthly releases, but the later releases are cumulative snapshots, not true incrementals.

For example, if `initial_history_month_count = 12` and `subsequent_month_count = 3`, the current release windows are:

| Release | Included batch sequences |
| --- | --- |
| Initial history | `1..12` |
| Snapshot month 13 | `1..13` |
| Snapshot month 14 | `1..14` |
| Snapshot month 15 | `1..15` |

That design lets students reload a full snapshot each month. It does not require them to build an append/update ingestion pipeline.

Relevant file:

- `backend/app/exports/student_dataset/release_windows.py`

## Findings

### 1. Monthly Incrementals Are Currently Cumulative Snapshots

The current `MONTHLY_INCREMENTAL_RELEASE_TYPE` name is misleading. The code builds each later release from batch sequence `1` through the snapshot month.

To support true monthly incrementals, the application needs to separate:

- the batches used to determine the as-of snapshot state,
- the batches emitted as monthly fact data.

### 2. Rating Generation Can Stay As-Is

The rating generator already produces the historical facts needed to derive an end-of-month player rating snapshot. The proposed change only requires an export-time projection that selects the latest rating row per player as of the release month.

The core monthly generation order can remain:

1. players
2. club memberships
3. teams
4. matches
5. ratings

### 3. A Player Master Is an Export Projection, Not a Source Table

The application should not add mutable rating columns to `players`. That would conflict with the current model boundary where `players` is static identity and `player_rating_history` is temporal rating state.

The better design is to generate `player_master.parquet` from a query that joins:

- static player attributes from `players`,
- latest rating attributes from `player_rating_history`,
- optional registration or region attributes as needed.

### 4. Match and Game Separation Already Exists

The application already separates match-level, team-level, player-participation, and game-level facts:

- `matches`
- `match_teams`
- `match_team_players`
- `match_games`

The proposed export does not require new source tables for matches or games. It requires deciding which of these files remain in the student-facing contract and whether they are emitted as baseline-plus-incremental facts.

## Required Application Changes

### 1. Change Release Window Semantics

Introduce separate batch scopes in `StudentDatasetReleaseWindow` or its query context:

- `snapshot_batch_ids`: all batches from the start through the release month; used for as-of dimensions such as player master.
- `fact_batch_ids`: only the batches emitted in this release folder; used for monthly facts such as matches and games.

Desired behavior:

| Release | Snapshot batches | Fact batches |
| --- | --- | --- |
| Initial 12-month baseline | `1..12` | `1..12` |
| Month 13 incremental | `1..13` | `13` |
| Month 14 incremental | `1..14` | `14` |
| Month 15 incremental | `1..15` | `15` |

This is the central change. Most downstream work follows from it.

### 2. Add `player_master.parquet`

Add a student-facing projection for a monthly player master.

Recommended columns:

- `player_id`
- `external_player_key`
- `first_name`
- `last_name`
- `gender`
- `birth_date`
- `dominant_hand`
- `home_region_id`
- `registration_date`
- `player_status`
- `rating_value`
- `confidence_score`
- `volatility_score`
- `global_percentile`
- `match_count_used`
- `rating_date`
- `rating_batch_id`
- `snapshot_month`

The query should select one row per included player, using the latest `player_rating_history` row before `snapshot_end_exclusive`.

Implementation approach:

- add a `player_master` projection to `projection.py`,
- add a `_player_master_query` builder to `queries.py`,
- use a window function such as `row_number() over (partition by player_id order by rating_date desc, id desc)`,
- label rating columns clearly so they do not look like static player fields.

### 3. Decide Whether to Keep `players` and `player_rating_history`

There are two viable designs.

Option A: Replace `players` and `player_rating_history` with `player_master`.

This is cleaner for a student ingestion exercise. Students upsert a monthly player dimension and append fact tables.

Option B: Keep all three files.

This gives students both the simplified current state and the full temporal rating history, but it increases ambiguity. If this path is chosen, the assignment needs to explain which file should drive current player state.

Recommendation: use Option A unless rating-history analysis is explicitly part of the student assignment.

### 4. Update Query Filters

The current query context exposes one `batch_ids` property used across most tables. That is not enough for true incrementals.

Suggested query behavior:

| Table | Filter basis |
| --- | --- |
| `player_master` | players registered before snapshot end; latest rating from snapshot scope |
| `matches` | fact batch ids |
| `match_teams` | included matches |
| `match_team_players` | included match teams |
| `match_games` | included matches |
| `monthly_batches` | likely fact batch ids, with manifest carrying snapshot scope |
| `regions` | regions referenced by player master and monthly facts |
| clubs/teams/memberships | decide whether needed; if included, use as-of snapshot semantics |

This requires changes in `queries.py` and tests that currently assume one release window batch set.

### 5. Update Validation

The DuckDB validation layer currently assumes all batch-tied facts reference included `monthly_batches`.

For true incrementals, validation should distinguish:

- snapshot dimension files,
- monthly fact files,
- metadata files.

Additional validation checks should include:

- `player_master` has one row per included player,
- every match-player row references a `player_master.player_id`,
- every match has exactly two match teams,
- every match team has at least one player,
- every game references an included match,
- fact files only contain rows from the monthly fact batch ids,
- player ratings are as of the release snapshot month, not after it.

### 6. Update Manifest Contract

The manifest should explicitly record both scopes.

Recommended manifest additions:

- `release_mode`: `baseline` or `monthly_incremental`
- `snapshot_batch_sequences`
- `fact_batch_sequences`
- `snapshot_month`
- `snapshot_end_exclusive`
- `student_dataset_schema_version`
- per-file row counts, checksums, schema hashes

This makes it possible for students and graders to verify ingestion behavior deterministically.

### 7. Update Service, UI, and Defaults

The service structure can remain mostly intact, but labels and defaults should change.

Required updates:

- default `initial_history_month_count` to `12`,
- keep `subsequent_month_count`,
- update UI copy from monthly snapshots to monthly incrementals,
- update progress messages and metadata,
- ensure export job metadata records the new release mode.

Relevant files:

- `backend/app/exports/student_dataset/service.py`
- `backend/app/templates/partials/control_export_config_tab.html`
- `backend/app/templates/partials/control_orchestration_tab.html`
- `backend/app/web/routes.py`
- `backend/app/web/control_panel_queries.py`

### 8. Update Tests and Documentation

Primary tests to update or add:

- `backend/tests/test_student_dataset_release_windows.py`
- `backend/tests/test_student_dataset_queries.py`
- `backend/tests/test_student_dataset_writer.py`
- `backend/tests/test_student_dataset_service.py`
- `backend/tests/test_student_dataset_projection.py`
- `backend/tests/test_student_dataset_release_windows.py`
- `scripts/student_dataset_duckdb_quality_check.sql`

Documentation to update:

- `docs/development/student_facing_dataset_build_specification.md`
- `docs/development/student_facing_dataset_data_dictionary.md`
- assignment-facing docs under `docs/student_assignment/`

## Recommended Student Ingestion Model

The exported dataset should encourage this ingestion pattern:

1. Load the 12-month baseline.
2. Create or replace/upsert the player master table using the baseline `player_master.parquet`.
3. Append baseline match and game facts.
4. For each monthly incremental:
   - upsert `player_master` by `player_id`,
   - append `matches`,
   - append `match_teams`,
   - append `match_team_players`,
   - append `match_games`,
   - validate that incoming fact batch ids have not already been loaded.

This gives students a practical, repeatable data engineering workflow without requiring them to understand the internal rating calculation audit trail.

## Recommended Source Generation Model

For an initial 12-month baseline plus 6 monthly incrementals, the application should generate the full 18-month source dataset first and then use the export process to slice that completed generation run into student-facing releases.

This is preferable to generating and exporting the baseline first, then generating each later month independently for release.

Recommended source/export mapping:

| Source generation | Export release |
| --- | --- |
| Generate months `1..18` once | Baseline exports fact batches `1..12`, player master as of month 12 |
| Same source generation run | Incremental 1 exports fact batch `13`, player master as of month 13 |
| Same source generation run | Incremental 2 exports fact batch `14`, player master as of month 14 |
| Same source generation run | Incremental 3 exports fact batch `15`, player master as of month 15 |
| Same source generation run | Incremental 4 exports fact batch `16`, player master as of month 16 |
| Same source generation run | Incremental 5 exports fact batch `17`, player master as of month 17 |
| Same source generation run | Incremental 6 exports fact batch `18`, player master as of month 18 |

This keeps generation and publication concerns separate:

- generation produces the complete, internally consistent source-of-truth dataset,
- export projects that source dataset into student-facing release packages,
- distribution can still mimic monthly delivery even though the source run was generated up front.

This approach is advisable because ratings are stateful. Month 13 ratings depend on months `1..12`; month 14 ratings depend on month 13; and so on. Building all 18 months in one sequential generation run preserves that continuity and avoids drift between separate generation jobs.

The export service should therefore validate that the source `generation_run` has all required monthly batches completed before building the release family. For a 12-month baseline plus 6 incrementals, that means completed batch sequences `1..18`.

The release-window model should still use two scopes:

| Scope | Purpose |
| --- | --- |
| `snapshot_batch_ids` | All batches from month `1` through the release month; used for player master and as-of dimensions |
| `fact_batch_ids` | Only the batches emitted in the release folder; used for matches, games, and other append-only facts |

This gives students a realistic incremental ingestion challenge without making the instructor-facing generation process fragile.

## Implementation Scope

This is a moderate export-layer refactor, not a rating-pipeline rewrite.

Low-risk areas:

- rating generation logic,
- monthly generation orchestration,
- ORM source tables.

Medium-risk areas:

- release-window semantics,
- export query filters,
- manifest schema,
- validation rules.

High-impact student-facing areas:

- data dictionary,
- assignment instructions,
- ingestion expectations,
- grading and quality checks.

## Recommendation

Proceed by treating this as a new student dataset schema version.

Recommended version path:

1. Create schema version `1.2` or `2.0`.
2. Add `player_master.parquet`.
3. Convert later monthly releases from cumulative snapshots to true monthly fact incrementals.
4. Keep the rating calculation pipeline unchanged.
5. Update validation and documentation before exposing the new package to students.

If backward compatibility with the current export is important, preserve the current cumulative snapshot mode as an explicit export option and add the baseline-plus-incremental mode as a separate release mode.
