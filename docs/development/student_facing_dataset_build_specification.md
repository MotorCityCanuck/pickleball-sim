# Student-Facing Dataset Build Specification

## Status

Draft implementation specification.

## Purpose

This document defines the student-facing analytical dataset that will be exported
from the pickleball simulation database.

The dataset must be released as Parquet files and must be directly queryable
with DuckDB. It is intended for student analytics, data engineering, dashboard,
machine learning, and modeling assignments. It must not expose internal
configuration, orchestration state, raw seed inputs, operational logs,
validation records, or generator-only hidden variables.

This specification is intentionally stricter than the internal database schema.
The source database can contain operational and privileged fields; the
student-facing dataset must contain only the approved projection defined here.

## Output Format

All student-facing data tables must be exported as Parquet.

Each included source table must produce one Parquet file per release folder
named:

```text
<table_name>.parquet
```

Each derived release folder should have this internal layout:

```text
<derived_release_folder>/
  clubs.parquet
  club_memberships.parquet
  match_games.parquet
  match_team_players.parquet
  match_teams.parquet
  matches.parquet
  monthly_batches.parquet
  player_assessment_history.parquet
  player_rating_history.parquet
  player_registrations.parquet
  players.parquet
  regions.parquet
  team_memberships.parquet
  teams.parquet
```

The exporter may also create non-student operational artifacts outside this
directory, but no operational artifact may be required to query the student
dataset.

## Build Parameters

The student dataset build process must be parameterized. The first
implementation must support these required parameters:

| Parameter | Type | Required | Description |
| --- | --- | --- | --- |
| `generation_run_id` | integer | yes | Source generation run to export. |
| `initial_history_month_count` | integer | yes | Number of monthly batches to include in the first historical release. |
| `subsequent_month_count` | integer | yes | Number of later monthly snapshot releases to export after the initial history release. |
| `output_root` | path/string | yes | Directory where release folders are written. |
| `release_name` | string | yes | Base release name used to derive release folder names and metadata. |
| `data_quality_profile` | string | no | Optional profile for future data quality injection. The default is `clean`. |
| `overwrite_existing` | boolean | no | Whether an existing release folder may be replaced. Default must be `false`. |

When the build is launched from the control panel or another UI, `output_root`
must be selectable with a folder picker. The selected folder path becomes the
`output_root` build parameter. The UI must display the selected folder before
the build starts so the operator can confirm where the Parquet release files
will be written.

Interactive UI builds must also allow the operator to choose the base
`release_name` with a file or folder name picker. The operator chooses one base
name for the release family, not separate names for each Parquet table and not
separate names for each table file set. The exporter derives each release folder
name by adding deterministic suffixes to the selected base name.

Recommended derived release folder names:

```text
<release_name>_initial_history
<release_name>_snapshot_YYYY_MM
```

For example, if the selected base name is `napa_student_release`, the release
folders should be:

```text
napa_student_release_initial_history/
napa_student_release_snapshot_2025_01/
napa_student_release_snapshot_2025_02/
```

The folder picker requirement applies only to interactive UI launches. Command
line, scheduled, or test builds may provide `output_root` and `release_name`
directly as arguments.

The monthly source window is determined by `monthly_batches.batch_sequence` for
the selected `generation_run_id`.

For example, with:

```text
initial_history_month_count = 12
subsequent_month_count = 6
```

the build must produce:

- one initial history release containing batch sequences `1` through `12`
- six separate monthly snapshot releases where the first snapshot contains
  batch sequences `1` through `13`, the second contains `1` through `14`, and
  the sixth contains `1` through `18`

If the selected generation run does not contain enough completed monthly batches
to satisfy the requested window, the build must fail before writing a partial
student release.

## Release Types and Output Layout

The student dataset build produces a release family composed of one initial
history release and zero or more subsequent monthly snapshot releases.

Recommended layout:

```text
<output_root>/<release_name>/
  <release_name>_initial_history/
    clubs.parquet
    club_memberships.parquet
    match_games.parquet
    match_team_players.parquet
    match_teams.parquet
    matches.parquet
    monthly_batches.parquet
    player_assessment_history.parquet
    player_rating_history.parquet
    player_registrations.parquet
    players.parquet
    regions.parquet
    team_memberships.parquet
    teams.parquet
  <release_name>_snapshot_2025_01/
    clubs.parquet
    ...
  <release_name>_snapshot_2025_02/
    clubs.parquet
    ...
```

The monthly snapshot suffix should use the newest included
`monthly_batches.batch_month` value in `YYYY_MM` format.

Each release folder must be independently queryable in DuckDB. A student should
be able to query only the initial history folder, only one monthly snapshot
folder, or compare multiple snapshot folders manually.

Monthly releases are complete snapshots, not deltas. Each monthly snapshot must
contain the initial history rows plus all rows through the snapshot month.

## DuckDB Access

The release must be usable from DuckDB without loading a Postgres database.

Minimum supported access pattern:

```sql
INSTALL parquet;
LOAD parquet;

CREATE VIEW players AS
SELECT * FROM read_parquet('student_release/players.parquet');

CREATE VIEW matches AS
SELECT * FROM read_parquet('student_release/matches.parquet');
```

Bulk discovery should also work:

```sql
SELECT *
FROM read_parquet('student_release/*.parquet', filename = true);
```

Column names in Parquet must match the names in this specification. File names
must match table names exactly.

The companion data dictionary is:

```text
docs/development/student_facing_dataset_data_dictionary.md
```

## Release Scope

The student-facing release is a projection of generated analytical entities and
reference entities only.

The release must exclude:

- operational tracking tables
- configuration tables
- log tables
- raw data tables
- seed ingest tracking tables
- validation tables and validation result details
- uploaded file metadata
- tournament records
- student release tracking tables
- generator configuration snapshots and seeds

## General Column Rules

For included tables:

- Keep stable primary keys and foreign keys needed for joins.
- Keep descriptive analytical attributes.
- Keep dates that are part of the simulated business process.
- Keep generated public-facing ratings, confidence scores, outcomes, scores,
  counts, and status values that support student analysis.
- Exclude `created_at` and `updated_at` from all student-facing tables.
- Exclude `generation_run_id` from all student-facing tables.
- Exclude operational status, error, and timing fields unless they represent
  simulated business events rather than job execution.
- Exclude hidden generator variables and privileged simulation controls.
- Exclude raw source file fields, checksums, payloads, and ingestion metadata.

## Included Tables

The following source tables are included in the student-facing release:

| Source table | Output file | Purpose |
| --- | --- | --- |
| `clubs` | `clubs.parquet` | Simulated pickleball clubs and facility attributes. |
| `club_memberships` | `club_memberships.parquet` | Player membership relationships to clubs. |
| `match_games` | `match_games.parquet` | Game-level scores inside each match. |
| `match_team_players` | `match_team_players.parquet` | Player participation on match teams. |
| `match_teams` | `match_teams.parquet` | Team-level match scores and public matchup estimates. |
| `matches` | `matches.parquet` | Match-level facts. |
| `monthly_batches` | `monthly_batches.parquet` | Simulated monthly time periods and aggregate monthly counts. |
| `player_assessment_history` | `player_assessment_history.parquet` | Public player assessment history. |
| `player_rating_history` | `player_rating_history.parquet` | Public player rating history. |
| `player_registrations` | `player_registrations.parquet` | Player registration facts by month. |
| `players` | `players.parquet` | Simulated player demographic and status attributes. |
| `regions` | `regions.parquet` | Simulated geographic market attributes. |
| `team_memberships` | `team_memberships.parquet` | Player membership relationships to teams. |
| `teams` | `teams.parquet` | Simulated doubles teams. |

## Excluded Tables

The following source tables must not be exported to the student-facing release:

| Source table | Exclusion reason |
| --- | --- |
| `batch_runs` | Operational batch execution tracking. |
| `configuration_profile_versions` | Configuration and internal payload storage. |
| `configuration_profiles` | Configuration metadata. |
| `export_runs` | Operational export tracking. |
| `first_names` | Normalized seed/reference data, not student analytical output. |
| `generation_runs` | Operational generation tracking and configuration snapshot exposure. |
| `job_stage_progress` | Operational job liveness and progress tracking. |
| `job_status` | Operational job tracking. |
| `last_names` | Normalized seed/reference data, not student analytical output. |
| `ratings_update_log` | Log table with privileged rating update mechanics. |
| `raw_first_names` | Raw seed data. |
| `raw_last_names` | Raw seed data. |
| `raw_metro_areas` | Raw seed data. |
| `raw_pickleball_club_distributions` | Raw seed data. |
| `raw_pickleball_club_names` | Raw seed data. |
| `raw_seed_load_errors` | Raw seed ingest error tracking. |
| `raw_seed_load_runs` | Raw seed ingest operational tracking. |
| `raw_state_prov_biases` | Raw seed data. |
| `student_dataset_release_files` | Operational student release tracking. |
| `student_dataset_releases` | Operational student release tracking. |
| `tournaments` | Explicitly excluded from student release scope. |
| `uploaded_files` | Uploaded file metadata and validation state. |
| `validation_results` | Validation details and quality-control metadata. |

## Column Projection Specifications

Each included table below lists every current source column and the required
student-facing decision.

### `clubs`

| Column | Decision | Notes |
| --- | --- | --- |
| `id` | Include | Primary key. |
| `club_name` | Include | Public analytical attribute. |
| `region_id` | Include | Foreign key to `regions.id`. |
| `club_type` | Include | Public analytical attribute. |
| `competitiveness_level` | Include | Public club segmentation. |
| `member_capacity` | Include | Public facility capacity. |
| `founding_date` | Include | Public lifecycle date. |
| `indoor_court_count` | Include | Public facility attribute. |
| `outdoor_court_count` | Include | Public facility attribute. |
| `generation_run_id` | Exclude | Internal generation lineage. |
| `created_at` | Exclude | Operational metadata. |
| `updated_at` | Exclude | Operational metadata. |

### `club_memberships`

| Column | Decision | Notes |
| --- | --- | --- |
| `id` | Include | Primary key. |
| `player_id` | Include | Foreign key to `players.id`. |
| `club_id` | Include | Foreign key to `clubs.id`. |
| `membership_type` | Include | Public membership attribute. |
| `start_date` | Include | Simulated business event date. |
| `end_date` | Include | Simulated business event date. |
| `is_primary` | Include | Useful analytical flag. |
| `generation_run_id` | Exclude | Internal generation lineage. |
| `created_at` | Exclude | Operational metadata. |
| `updated_at` | Exclude | Operational metadata. |

### `match_games`

| Column | Decision | Notes |
| --- | --- | --- |
| `id` | Include | Primary key. |
| `match_id` | Include | Foreign key to `matches.id`. |
| `game_number` | Include | Game sequence within match. |
| `team_one_score` | Include | Public score. |
| `team_two_score` | Include | Public score. |
| `winning_team_number` | Include | Public outcome. |
| `target_score` | Include | Game rules attribute. |
| `win_by` | Include | Game rules attribute. |
| `expected_team_one_score_share` | Exclude | Model-derived expectation; reserve for instructor/internal analysis. |
| `actual_team_one_score_share` | Include | Public observed game share. |
| `expected_team_one_score` | Exclude | Model-derived expectation; reserve for instructor/internal analysis. |
| `expected_team_two_score` | Exclude | Model-derived expectation; reserve for instructor/internal analysis. |
| `score_noise_factor` | Exclude | Hidden generator noise. |
| `created_at` | Exclude | Operational metadata. |
| `updated_at` | Exclude | Operational metadata. |

### `match_team_players`

| Column | Decision | Notes |
| --- | --- | --- |
| `id` | Include | Primary key. |
| `match_team_id` | Include | Foreign key to `match_teams.id`. |
| `player_id` | Include | Foreign key to `players.id`. |
| `player_position` | Include | Public player order on match team. |
| `player_rating_at_match` | Include | Public rating snapshot for analytical use. |
| `created_at` | Exclude | Operational metadata. |
| `updated_at` | Exclude | Operational metadata. |

### `match_teams`

| Column | Decision | Notes |
| --- | --- | --- |
| `id` | Include | Primary key. |
| `match_id` | Include | Foreign key to `matches.id`. |
| `team_number` | Include | Public team number within match. |
| `team_score` | Include | Public match-level score. |
| `expected_win_probability` | Exclude | Model-derived expectation; reserve for instructor/internal analysis. |
| `average_team_rating` | Include | Public team strength measure. |
| `created_at` | Exclude | Operational metadata. |
| `updated_at` | Exclude | Operational metadata. |

### `matches`

| Column | Decision | Notes |
| --- | --- | --- |
| `id` | Include | Primary key. |
| `tournament_id` | Exclude | `tournaments` is excluded. |
| `match_date` | Include | Public event date. |
| `region_id` | Include | Foreign key to `regions.id`. |
| `match_type` | Include | Public match classification. |
| `court_type` | Include | Public match attribute. |
| `match_format` | Include | Public match attribute. |
| `winning_team_id` | Include | Foreign key to winning `match_teams.id`. |
| `predicted_winning_team_number` | Exclude | Model-derived prediction; reserve for instructor/internal analysis. |
| `predicted_win_probability` | Exclude | Model-derived prediction; reserve for instructor/internal analysis. |
| `total_points_played` | Include | Public match aggregate. |
| `expected_competitiveness` | Exclude | Model-derived expectation; reserve for instructor/internal analysis. |
| `simulation_noise_factor` | Exclude | Hidden generator noise. |
| `batch_id` | Include | Foreign key to `monthly_batches.id`. |
| `created_at` | Exclude | Operational metadata. |
| `updated_at` | Exclude | Operational metadata. |

### `monthly_batches`

| Column | Decision | Notes |
| --- | --- | --- |
| `id` | Include | Primary key for monthly period joins. |
| `generation_run_id` | Exclude | Internal generation lineage. |
| `batch_month` | Include | Public month identifier. |
| `batch_sequence` | Include | Public month sequence. |
| `batch_type` | Include | Public timeline classification. |
| `active_player_count_start` | Include | Public monthly aggregate. |
| `new_player_count` | Include | Public monthly aggregate. |
| `active_player_count_end` | Include | Public monthly aggregate. |
| `match_count_generated` | Include | Public monthly aggregate. |
| `rating_update_count` | Include | Public monthly aggregate. |
| `assessment_update_count` | Include | Public monthly aggregate. |
| `processing_status` | Exclude | Operational processing state. |
| `started_at` | Exclude | Operational execution timing. |
| `completed_at` | Exclude | Operational execution timing. |
| `error_message` | Exclude | Operational error detail. |
| `created_at` | Exclude | Operational metadata. |
| `updated_at` | Exclude | Operational metadata. |

### `player_assessment_history`

| Column | Decision | Notes |
| --- | --- | --- |
| `id` | Include | Primary key. |
| `player_id` | Include | Foreign key to `players.id`. |
| `assessment_date` | Include | Public assessment date. |
| `assessment_type` | Include | Public assessment category. |
| `assessment_value` | Include | Public assessment value. |
| `confidence_score` | Include | Public confidence score. |
| `derived_from_matches` | Include | Public count/lineage summary, not operational metadata. |
| `batch_id` | Include | Foreign key to `monthly_batches.id`. |
| `created_at` | Exclude | Operational metadata. |

### `player_rating_history`

| Column | Decision | Notes |
| --- | --- | --- |
| `id` | Include | Primary key. |
| `player_id` | Include | Foreign key to `players.id`. |
| `rating_date` | Include | Public rating date. |
| `rating_type` | Include | Public rating category. |
| `rating_value` | Include | Public rating value. |
| `confidence_score` | Include | Public confidence score. |
| `volatility_score` | Include | Public volatility score. |
| `expected_performance` | Exclude | Model-derived expectation; reserve for instructor/internal analysis. |
| `regional_adjustment_factor` | Include | Public contextual adjustment. |
| `global_percentile` | Include | Public ranking metric. |
| `match_count_used` | Include | Public rating sample-size indicator. |
| `calculation_version` | Exclude | Internal calculation implementation metadata. |
| `batch_id` | Include | Foreign key to `monthly_batches.id`. |
| `created_at` | Exclude | Operational metadata. |
| `updated_at` | Exclude | Operational metadata. |

### `player_registrations`

| Column | Decision | Notes |
| --- | --- | --- |
| `id` | Include | Primary key. |
| `player_id` | Include | Foreign key to `players.id`. |
| `batch_id` | Include | Foreign key to `monthly_batches.id`. |
| `registration_month` | Include | Public registration month. |
| `registration_source` | Include | Public acquisition/source category. |
| `assigned_region_id` | Include | Foreign key to `regions.id`. |
| `initial_rating_value` | Include | Public starting rating. |
| `initial_confidence_score` | Include | Public starting confidence. |
| `created_at` | Exclude | Operational metadata. |

### `players`

| Column | Decision | Notes |
| --- | --- | --- |
| `id` | Include | Primary key. |
| `external_player_key` | Include | Stable external identifier for student use. |
| `first_name` | Include | Public simulated identity attribute. |
| `last_name` | Include | Public simulated identity attribute. |
| `gender` | Include | Public demographic attribute. |
| `birth_date` | Include | Public demographic attribute. |
| `dominant_hand` | Include | Public player attribute. |
| `home_region_id` | Include | Foreign key to `regions.id`. |
| `registration_date` | Include | Public registration date. |
| `initial_skill_seed` | Exclude | Hidden generator variable. |
| `player_status` | Include | Public player lifecycle/status attribute. |
| `generation_run_id` | Exclude | Internal generation lineage. |
| `created_at` | Exclude | Operational metadata. |
| `updated_at` | Exclude | Operational metadata. |

### `regions`

| Column | Decision | Notes |
| --- | --- | --- |
| `id` | Include | Primary key. |
| `country_code` | Include | Public geography attribute. |
| `region_type` | Include | Public geography classification. |
| `region_name` | Include | Public geography attribute. |
| `state_province_code` | Include | Public geography attribute. |
| `population` | Include | Public market size attribute. |
| `selection_probability` | Exclude | Internal sampling weight. |
| `competitiveness_multiplier` | Exclude | Hidden generator parameter. |
| `latitude` | Include | Public geography attribute. |
| `longitude` | Include | Public geography attribute. |
| `created_at` | Exclude | Operational metadata. |
| `updated_at` | Exclude | Operational metadata. |

### `team_memberships`

| Column | Decision | Notes |
| --- | --- | --- |
| `id` | Include | Primary key. |
| `team_id` | Include | Foreign key to `teams.id`. |
| `player_id` | Include | Foreign key to `players.id`. |
| `player_position` | Include | Public player position/order. |
| `joined_date` | Include | Simulated business event date. |
| `left_date` | Include | Simulated business event date. |
| `created_at` | Exclude | Operational metadata. |
| `updated_at` | Exclude | Operational metadata. |

### `teams`

| Column | Decision | Notes |
| --- | --- | --- |
| `id` | Include | Primary key. |
| `team_type` | Include | Public team classification. |
| `team_status` | Include | Public lifecycle/status attribute. |
| `formation_date` | Include | Simulated business event date. |
| `dissolution_date` | Include | Simulated business event date. |
| `chemistry_score` | Include | Public analytical team metric. |
| `persistence_probability` | Include | Public analytical team metric. |
| `generation_run_id` | Exclude | Internal generation lineage. |
| `created_at` | Exclude | Operational metadata. |
| `updated_at` | Exclude | Operational metadata. |

## Referential Integrity Requirements

The exported Parquet files must preserve these student-facing relationships:

| Child table | Child column | Parent table | Parent column |
| --- | --- | --- | --- |
| `clubs` | `region_id` | `regions` | `id` |
| `club_memberships` | `player_id` | `players` | `id` |
| `club_memberships` | `club_id` | `clubs` | `id` |
| `matches` | `region_id` | `regions` | `id` |
| `matches` | `batch_id` | `monthly_batches` | `id` |
| `match_games` | `match_id` | `matches` | `id` |
| `match_teams` | `match_id` | `matches` | `id` |
| `match_team_players` | `match_team_id` | `match_teams` | `id` |
| `match_team_players` | `player_id` | `players` | `id` |
| `player_assessment_history` | `player_id` | `players` | `id` |
| `player_assessment_history` | `batch_id` | `monthly_batches` | `id` |
| `player_rating_history` | `player_id` | `players` | `id` |
| `player_rating_history` | `batch_id` | `monthly_batches` | `id` |
| `player_registrations` | `player_id` | `players` | `id` |
| `player_registrations` | `batch_id` | `monthly_batches` | `id` |
| `player_registrations` | `assigned_region_id` | `regions` | `id` |
| `team_memberships` | `team_id` | `teams` | `id` |
| `team_memberships` | `player_id` | `players` | `id` |

The `matches.winning_team_id` column references `match_teams.id` and should be
validated when present.

## Export Filtering Requirements

The export should select one completed generation run at a time. The source run
must have all requested monthly batches completed before release.

The release windows are:

| Release type | Included batch sequences |
| --- | --- |
| Initial history | `1` through `initial_history_month_count` |
| Subsequent monthly snapshot N | `1` through `initial_history_month_count + N` |

Using the example `initial_history_month_count = 12` and
`subsequent_month_count = 6`:

| Release folder | Included batch sequence(s) |
| --- | --- |
| `<release_name>_initial_history/` | `1` through `12` |
| first monthly snapshot | `1` through `13` |
| second monthly snapshot | `1` through `14` |
| third monthly snapshot | `1` through `15` |
| fourth monthly snapshot | `1` through `16` |
| fifth monthly snapshot | `1` through `17` |
| sixth monthly snapshot | `1` through `18` |

For each included table:

- Export only rows belonging to the selected generation run when the table
  contains generation lineage directly or through a join path.
- Export only rows reachable from the monthly batches included in that specific
  release folder.
- Export only rows reachable from included rows through the student-facing
  relationships above.
- Do not export orphaned rows.
- Preserve source primary keys; do not remap keys in the first implementation.

Recommended lineage filters:

| Table | Source filter |
| --- | --- |
| `monthly_batches` | `monthly_batches.generation_run_id = :generation_run_id` and `batch_sequence` is in the release window. |
| `players` | Include players registered on or before the last batch month in the release window and belonging to the selected generation run. |
| `clubs` | Include clubs for the selected run plus any referenced by included memberships. |
| `teams` | `teams.generation_run_id = :generation_run_id` |
| `club_memberships` | `club_memberships.generation_run_id = :generation_run_id` or `player_id` in included players. |
| `matches` | `batch_id` in included monthly batches. |
| `match_teams` | `match_id` in included matches. |
| `match_team_players` | `match_team_id` in included match teams. |
| `match_games` | `match_id` in included matches. |
| `player_rating_history` | `batch_id` in included monthly batches and `player_id` in included players. |
| `player_assessment_history` | `batch_id` in included monthly batches and `player_id` in included players. |
| `player_registrations` | `batch_id` in included monthly batches and `player_id` in included players. |
| `regions` | Include regions referenced by included players, clubs, registrations, or matches. |
| `team_memberships` | `team_id` in included teams and `player_id` in included players. |

For subsequent monthly releases, dimension-like tables such as `players`,
`clubs`, `teams`, and `regions` should include the records needed to make that
monthly release independently queryable. Because monthly releases are complete
snapshots, they should include all rows in the selected generation run that are
reachable through the snapshot's included batch sequence range.

## Monthly Snapshot Semantics

Monthly releases must be complete snapshots, not incremental deltas.

For a snapshot ending at batch sequence `N`:

- `monthly_batches` includes batch sequences `1` through `N`.
- fact tables such as `matches`, `match_games`, `match_teams`,
  `match_team_players`, `player_rating_history`,
  `player_assessment_history`, and `player_registrations` include rows tied to
  included monthly batches.
- dimension-like tables such as `players`, `clubs`, `teams`, `regions`,
  `club_memberships`, and `team_memberships` include records needed to interpret
  the included facts through the snapshot month.
- records created after the snapshot month must not appear.

This lets a student open any one monthly snapshot folder and analyze the full
state of the simulated world as of that month.

## DuckDB Validation Queries

The implementation must validate the Parquet release with DuckDB before marking
the release complete.

Minimum validation checks:

```sql
SELECT COUNT(*) FROM read_parquet('student_release/players.parquet');
SELECT COUNT(*) FROM read_parquet('student_release/matches.parquet');
SELECT COUNT(*) FROM read_parquet('student_release/match_games.parquet');
```

Schema checks must confirm that excluded columns are absent:

```sql
DESCRIBE SELECT * FROM read_parquet('student_release/players.parquet');
DESCRIBE SELECT * FROM read_parquet('student_release/matches.parquet');
DESCRIBE SELECT * FROM read_parquet('student_release/monthly_batches.parquet');
```

Referential integrity checks should be run with DuckDB joins. Example:

```sql
WITH missing AS (
  SELECT m.id, m.batch_id
  FROM read_parquet('student_release/matches.parquet') m
  LEFT JOIN read_parquet('student_release/monthly_batches.parquet') b
    ON b.id = m.batch_id
  WHERE b.id IS NULL
)
SELECT COUNT(*) AS missing_batch_count
FROM missing;
```

Every referential integrity check must return zero missing rows.

## Acceptance Criteria

A student-facing release is complete only when all of these conditions are met:

- Every included table has exactly one Parquet file in the release folder.
- No excluded table has a Parquet file in the release folder.
- Every Parquet file can be opened by DuckDB.
- Every Parquet file contains exactly the documented included columns in the
  documented order.
- No excluded column appears in any Parquet file.
- Every required referential integrity check returns zero missing rows.
- Row counts match the manifest row counts.
- `monthly_batches` contains exactly the expected batch sequence window.
- Non-empty required tables contain at least one row.
- The release manifest is written and reports successful validation.

## Failure and Cleanup Behavior

The exporter must write to a temporary staging folder first. It must validate
the staged Parquet files before promoting them to the final release folder.

Recommended flow:

1. Create a staging folder under `output_root`.
2. Write all Parquet files and manifests to the staging folder.
3. Run DuckDB schema, readability, row count, and referential integrity checks.
4. If validation passes, move or rename the staging folder to the final release
   folder name.
5. If validation fails, leave the final release folder unchanged and mark the
   staged release failed.

Partial releases must not appear in the final output location. If
`overwrite_existing` is `false` and the target folder already exists, the build
must fail before writing.

## Schema Versioning

The student dataset schema must have its own version independent of application,
database, configuration, and generation-run versions.

Initial schema version:

```text
student_dataset_schema_version = 1.0
```

The schema version must be included in every manifest. Any change to included
tables, included columns, column names, column ordering, meaning, or data types
must update the schema version.

## Column Ordering and Type Contract

The column order in each Parquet file must match the order in
`student_facing_dataset_data_dictionary.md`.

The exporter must preserve DuckDB-compatible logical types:

- integer identifiers and counts as `BIGINT` or `INTEGER`
- dates as `DATE`
- timestamps only where explicitly allowed
- decimals as DuckDB `DECIMAL(p,s)` where precision and scale are known
- text fields as `VARCHAR`
- booleans as `BOOLEAN`
- UUID values as `UUID` or `VARCHAR` if the writer cannot preserve UUID natively

Type drift is a schema change and must fail validation unless the data
dictionary and schema version are updated.

## Null and Empty Table Policy

Required non-empty tables for a valid release:

- `monthly_batches`
- `players`
- `regions`

Tables expected to be non-empty after match generation:

- `matches`
- `match_teams`
- `match_team_players`
- `match_games`
- `player_rating_history`

Tables that may be empty in a valid release depending on configuration or
generation outcomes:

- `clubs`
- `club_memberships`
- `teams`
- `team_memberships`
- `player_assessment_history`
- `player_registrations`

Column nullability must follow the data dictionary. Nullable fields may contain
nulls where business semantics permit missing or not-yet-ended values, such as
`club_memberships.end_date`, `team_memberships.left_date`, and
`teams.dissolution_date`.

## Privacy and Synthetic Data Statement

The student-facing dataset is synthetic. Names, demographics, regions, clubs,
matches, ratings, and scores are generated for educational use and do not
represent real people or real match outcomes.

Even though the data is synthetic, the release must avoid exposing hidden
generator variables or internal configuration fields. The goal is a realistic
student analytical dataset, not a transparent generator trace.

## Instructor and Student Artifacts

Student artifacts:

- Parquet files for included student-facing tables.
- Optional student-facing data dictionary and assignment materials.

Instructor/operator artifacts:

- `manifest.json`
- build logs
- validation summaries
- row count summaries
- schema hashes
- checksums
- operational error details

Instructor/operator artifacts may live beside a release folder for auditing, but
they are not part of the student analytical dataset and should not be required
for DuckDB queries against the Parquet files.

## Implementation Notes

The first implementation should build an explicit table projection map in code.
Do not infer included columns by exporting all ORM columns and removing a small
blocklist. The blocklist approach is too risky for student-facing data because
new privileged columns could leak by default.

The projection map should contain:

- source table name
- output file name
- included columns in order
- optional source filter/query builder
- required parent/child validation checks

The export should fail closed:

- If a table listed as included in this document is missing from the projection
  map, fail.
- If the source table has a column not listed in this document, fail until this
  specification and the projection map are updated.
- If an excluded column appears in a Parquet file, fail.
- If an excluded table appears as a Parquet file, fail.

## Implementation Checklist

- Define the explicit projection map for every included table.
- Define excluded table assertions.
- Implement release parameter parsing and validation.
- Add folder picker support for `output_root` in the control panel.
- Add base release name picker support for interactive builds.
- Generate deterministic suffixed release folder names.
- Implement complete snapshot batch-window selection.
- Write Parquet files to a staging folder.
- Generate per-release `manifest.json` files.
- Validate Parquet readability with DuckDB.
- Validate column order and types against the data dictionary.
- Validate excluded columns and excluded tables are absent.
- Validate referential integrity.
- Validate required non-empty tables.
- Promote staged output only after validation succeeds.
- Add automated tests for initial history and monthly snapshot releases.

## Release Manifest

The build process should emit a release manifest for operator and instructor
auditability. The manifest is not a student data table and must not be required
for DuckDB access to the Parquet files.

The recommended manifest format is JSON because it is metadata, not analytical
student data. The file should be written beside each release folder as:

```text
manifest.json
```

For a release family with `initial_history/` and monthly subfolders, each folder
should have its own manifest. A top-level family manifest may also be emitted to
summarize all child releases.

Each manifest should include:

- release name
- release type: `initial_history` or `monthly`
- source `generation_run_id`
- included `batch_sequence` values
- included `batch_month` values
- build parameters used for the release
- data quality profile
- output files written
- row count by output table
- ordered column list by output table
- schema hash by output table
- file checksum by output table
- build timestamp
- exporter version or code version when available
- validation status and validation summary

The manifest should not include:

- configuration payloads
- seeds
- raw source file paths
- operational job status rows
- validation row-level details
- internal error traces

The manifest is useful for three reasons:

- It lets an instructor confirm exactly which monthly batches a release covers.
- It gives a quick row-count and schema audit without opening every Parquet file.
- It gives the exporter a durable validation target for detecting partial,
  stale, or schema-drifted releases.

## Resolved Design Decisions

These decisions are now fixed for the first implementation:

- Exclude all `expected_*` and `predicted_*` columns from student-facing
  Parquet files.
- Keep `players.birth_date` exact.
- Keep `regions.latitude` and `regions.longitude` exact.
- Emit release manifests as JSON metadata, not Parquet student data.
