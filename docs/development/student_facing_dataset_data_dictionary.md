# Student-Facing Analytics Dataset Data Dictionary

## Status

This is the current data dictionary for the student-facing Parquet export
contract.

It is aligned to:

- `backend/app/exports/student_dataset/projection.py`
- `backend/app/exports/student_dataset/queries.py`
- `backend/app/exports/student_dataset/writer.py`
- `docs/development/student_facing_dataset_build_specification.md`

Current student dataset schema version: `1.6`.

Older checked-in release artifacts may still contain `players.parquet` and
`player_rating_history.parquet`. Those are legacy outputs. The current
student-facing contract publishes `player_master.parquet` instead.

## Release Package Model

A release package is the unit distributed to students. A package may contain:

- a clean dataset variant,
- a tainted dataset variant when data-quality injection is enabled.

Clean and tainted variants contain the same student-facing table names and
column order. The tainted variant may contain intentionally injected data
quality issues. Instructor-only injection manifests are not student-facing
outputs.

Within each variant, the exporter writes one historical baseline release folder
and zero or more monthly incremental release folders.

Folder naming:

```text
<release_name>_initial_history
<release_name>_snapshot_YYYY_MM
```

The `_snapshot_YYYY_MM` suffix is retained for compatibility. The release type
for those folders is `monthly_incremental`.

## Release Folder Contents

Every concrete release folder contains these files:

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

The Parquet file order follows `STUDENT_TABLE_ORDER` in the exporter. Load order
does not need to match this list, but relationship checks are easiest when
dimension tables are loaded before fact tables.

## Baseline And Incremental Semantics

The baseline release contains the first `initial_history_month_count` monthly
batches.

Monthly incremental releases contain:

- fact rows for exactly one new monthly batch,
- changed or newly referenced snapshot rows needed to apply that incremental,
- as-of values evaluated at that release folder's `snapshot_month`.

For snapshot-style dimensions, later incrementals are not full restatements of
the entire dimension. They are merge-ready deltas relative to the prior
snapshot.

Fact tables and dimensions use different incremental rules. Fact tables emit
rows tied to the release's fact batch window. Snapshot-style dimensions emit
rows that changed since the prior snapshot or are newly referenced by the fact
rows and changed relationships in the incremental.

Important release-scope terms:

| Term | Meaning |
| --- | --- |
| `snapshot_month` | Newest `monthly_batches.batch_month` visible to the release. |
| `snapshot_end_exclusive` | First day after `snapshot_month`; temporal filters use `< snapshot_end_exclusive`. |
| `snapshot_batch_sequences` | All batch sequences visible to the snapshot as of the release. |
| `fact_batch_sequences` | Batch sequences whose fact rows are emitted in this release folder. |

## Manifest

Each release folder includes `manifest.json`. It is part of the student-facing
package metadata.

Key manifest fields:

| Field | Description |
| --- | --- |
| `release_name` | Concrete release folder name. |
| `release_sequence_number` | One-based sequence in the release package. |
| `release_mode` | `baseline` for the initial release or `monthly_incremental` for later releases. |
| `release_type` | `initial_snapshot` or `monthly_incremental`. |
| `release_month` | Fact month for monthly incrementals; `null` for the baseline. |
| `included_months` | Legacy-compatible copy of the fact batch sequence numbers included in this folder. |
| `load_strategy` | `full_load` for the baseline or `incremental_load` for later releases. |
| `included_batch_months` | ISO month values for the fact batches included in this folder. |
| `snapshot_month` | Snapshot month used for as-of dimensions. |
| `snapshot_end_exclusive` | First day after `snapshot_month`. |
| `included_batch_sequences` | Fact batch sequences in this folder. |
| `snapshot_batch_months` | ISO month values visible to the snapshot as of this folder. |
| `snapshot_batch_sequences` | Snapshot batch sequences visible as of this folder. |
| `fact_batch_months` | ISO month values whose fact rows are emitted in this folder. |
| `fact_batch_sequences` | Fact batch sequences in this folder. |
| `parquet_compression` | Compression codec used for the Parquet files. |
| `output_files` | Per-file metadata including row count, schema hash, and checksum. |
| `row_counts` | Per-table row counts. |
| `ordered_columns` | Published column order by table. |
| `schema_hashes` | Schema hash by table. |
| `file_checksums` | File checksum by table. |
| `build_timestamp` | UTC timestamp when the release folder manifest was written. |
| `student_dataset_schema_version` | Current schema contract version. |
| `validation_status` | Release validation status. |
| `validation_summary` | DuckDB validation summary. |

Each `output_files` entry contains:

- `table_name`
- `file_name`
- `file_path`
- `row_count`
- `columns`
- `schema_hash`
- `checksum`

## General Conventions

- File format is Parquet.
- Column names are lower snake case.
- The type names below describe the exported Parquet logical types, not the ORM
  source-column types.
- Date and datetime values are normalized to ISO-8601 strings before Parquet
  writing.
- Integer-valued columns are written as Parquet `INT64`.
- UUID values are exported as plain string columns.
- Decimal-valued columns are written as Parquet `DECIMAL`. For non-empty files,
  precision is inferred from the first streamed chunk of observed values; empty
  files fall back to the projection schema derived from source precision/scale.
- Primary keys are stable exported identifiers within a generation run.
- Foreign-key references point to other student-facing Parquet tables in the
  same release state.
- Hidden simulation values, operational timestamps, job metadata, raw seed
  tables, tournament tables, and instructor-only artifacts are excluded.
- Nullable means the exported Parquet column may contain null values.

## Included Tables

| Table | Grain |
| --- | --- |
| `clubs` | One row per exported club or facility. |
| `club_memberships` | One row per exported player-to-club membership interval. |
| `match_games` | One row per exported game within a match. |
| `match_team_players` | One row per exported player on a match side. |
| `match_teams` | One row per exported side in a match. |
| `matches` | One row per exported match. |
| `monthly_batches` | One row per exported monthly fact batch. |
| `player_assessment_history` | One row per exported player assessment observation. |
| `player_master` | One row per exported player dimension row as of the release snapshot. |
| `player_registrations` | One row per exported player registration event. |
| `regions` | One row per referenced geographic region. |
| `team_memberships` | One row per exported player-to-team membership interval. |
| `teams` | One row per exported doubles team. |

## Entity Relationships

| Child table | Child column | Parent table | Parent column | Nullable |
| --- | --- | --- | --- | --- |
| `clubs` | `region_id` | `regions` | `id` | no |
| `club_memberships` | `player_id` | `player_master` | `player_id` | no |
| `club_memberships` | `club_id` | `clubs` | `id` | no |
| `match_games` | `match_id` | `matches` | `id` | no |
| `match_team_players` | `match_team_id` | `match_teams` | `id` | no |
| `match_team_players` | `player_id` | `player_master` | `player_id` | no |
| `match_teams` | `match_id` | `matches` | `id` | no |
| `match_teams` | `team_id` | `teams` | `id` | no |
| `matches` | `region_id` | `regions` | `id` | yes |
| `matches` | `batch_id` | `monthly_batches` | `id` | no |
| `matches` | `winning_team_id` | `teams` | `id` | yes |
| `player_assessment_history` | `player_id` | `player_master` | `player_id` | no |
| `player_assessment_history` | `batch_id` | `monthly_batches` | `id` | no |
| `player_master` | `home_region_id` | `regions` | `id` | yes |
| `player_registrations` | `player_id` | `player_master` | `player_id` | no |
| `player_registrations` | `batch_id` | `monthly_batches` | `id` | no |
| `player_registrations` | `assigned_region_id` | `regions` | `id` | yes |
| `team_memberships` | `team_id` | `teams` | `id` | no |
| `team_memberships` | `player_id` | `player_master` | `player_id` | no |

`matches.winning_team_id` must match one of the two `match_teams.team_id`
values for the match when it is not null.

## Source Filters

| Output table | Export filter |
| --- | --- |
| `clubs` | Clubs for the generation run founded before `snapshot_end_exclusive`, plus clubs referenced by included memberships. Incrementals include changed clubs and clubs referenced by changed memberships. |
| `club_memberships` | Memberships for included players and clubs with `joined_date < snapshot_end_exclusive`; future `left_date` values are projected to null. Incrementals include changed rows only. |
| `match_games` | Games whose `match_id` belongs to included matches. |
| `match_team_players` | Player rows whose `match_team_id` belongs to included match teams. |
| `match_teams` | Match sides whose `match_id` belongs to included matches. |
| `matches` | Matches whose `batch_id` belongs to the release fact batch ids. |
| `monthly_batches` | Completed monthly batches for the selected generation run and release fact batch sequence window. |
| `player_assessment_history` | Assessment rows tied to included fact batches and included players. |
| `player_master` | Players registered before `snapshot_end_exclusive`, with latest rating state before `snapshot_end_exclusive`. Incrementals include changed players and players referenced by new facts or changed memberships. |
| `player_registrations` | Registration rows tied to included fact batches and included players. |
| `regions` | Regions referenced by included players, clubs, registrations, or matches. Incrementals include newly referenced or changed regions. |
| `team_memberships` | Memberships for included teams and players with `joined_date < snapshot_end_exclusive`; future `left_date` values are projected to null. Incrementals include changed memberships and teams referenced by new match sides. |
| `teams` | Teams for the generation run with `formation_date < snapshot_end_exclusive`; future dissolution state is projected to the as-of snapshot. Incrementals include changed teams, teams referenced by changed memberships, and teams referenced by new match sides. |

## Excluded Source Data

The student export intentionally excludes:

- `player_rating_history` as a standalone file; current rating state is folded
  into `player_master`.
- `players` as a standalone file; current player state is published as
  `player_master`.
- generation run parameters and runtime metrics.
- job status, background worker, and export bookkeeping tables.
- raw seed files and raw normalized seed tables.
- hidden expected-performance, prediction, noise, chemistry, and persistence
  fields.
- tournament simulation tables.
- instructor-only data-quality injection manifests.

## Table Dictionary

### `clubs`

Business description: club, facility, and organization dimension.

Grain: one row per exported club.

Source table: `clubs`.

| Column | Type | Nullable | FK | Description |
| --- | --- | --- | --- | --- |
| `id` | INT64 | no | none | Club identifier. |
| `club_name` | STRING | no | none | Club or facility name. |
| `region_id` | INT64 | no | `regions.id` | Region where the club is located. |
| `club_type` | STRING | yes | none | Club classification. |
| `competitiveness_level` | STRING | yes | none | Competitive segment assigned to the club. |
| `member_capacity` | INT64 | yes | none | Approximate member capacity. |
| `founding_date` | STRING (ISO date) | yes | none | Club founding date. |
| `indoor_court_count` | INT64 | yes | none | Number of indoor courts. |
| `outdoor_court_count` | INT64 | yes | none | Number of outdoor courts. |

Excluded source columns: `generation_run_id`, `created_at`, `updated_at`.

### `club_memberships`

Business description: player-to-club membership intervals.

Grain: one row per exported club membership interval.

Source table: `club_memberships`.

| Column | Type | Nullable | FK | Description |
| --- | --- | --- | --- | --- |
| `id` | INT64 | no | none | Club membership identifier. |
| `player_id` | INT64 | no | `player_master.player_id` | Member player. |
| `club_id` | INT64 | no | `clubs.id` | Club joined by the player. |
| `membership_type` | STRING | yes | none | Membership category. |
| `joined_date` | STRING (ISO date) | no | none | Membership start date. Exported from source `start_date`. |
| `left_date` | STRING (ISO date) | yes | none | Membership end date; future end dates are projected to null. Exported from source `end_date`. |
| `is_primary` | BOOL | yes | none | Whether this is the player's primary club membership. |

Excluded source columns: `generation_run_id`, `created_at`, `updated_at`.

### `match_games`

Business description: game-level scoring rows inside exported matches.

Grain: one row per exported game.

Source table: `match_games`.

| Column | Type | Nullable | FK | Description |
| --- | --- | --- | --- | --- |
| `id` | INT64 | no | none | Match game identifier. |
| `match_id` | INT64 | no | `matches.id` | Match containing the game. |
| `game_number` | INT64 | no | none | Game sequence number within the match. |
| `team_one_score` | INT64 | no | none | Score for team number `1`. |
| `team_two_score` | INT64 | no | none | Score for team number `2`. |
| `winning_team_number` | INT64 | no | none | Winning side number: `1` or `2`. |
| `target_score` | INT64 | yes | none | Target score for the game. |
| `win_by` | INT64 | yes | none | Required winning margin. |
| `actual_team_one_score_share` | DECIMAL (scale 4) | yes | none | Team one's share of total points in the game. |

Excluded source columns: `expected_team_one_score_share`,
`expected_team_one_score`, `expected_team_two_score`, `score_noise_factor`,
`created_at`, `updated_at`.

### `match_team_players`

Business description: player participation rows within match sides.

Grain: one row per exported player on a match side.

Source table: `match_team_players`.

| Column | Type | Nullable | FK | Description |
| --- | --- | --- | --- | --- |
| `id` | INT64 | no | none | Match-team-player row identifier. |
| `match_team_id` | INT64 | no | `match_teams.id` | Match side containing this player. |
| `player_id` | INT64 | no | `player_master.player_id` | Participating player. |
| `player_position` | INT64 | yes | none | Player order on the side. |
| `player_rating_at_match` | DECIMAL (scale 3) | yes | none | Public player rating used at match time. |

Excluded source columns: `created_at`, `updated_at`.

### `match_teams`

Business description: side-level facts within exported matches.

Grain: one row per side in an exported match.

Source table: `match_teams`.

| Column | Type | Nullable | FK | Description |
| --- | --- | --- | --- | --- |
| `id` | INT64 | no | none | Match side identifier. |
| `match_id` | INT64 | no | `matches.id` | Match containing this side. |
| `team_number` | INT64 | no | none | Side number within the match. |
| `team_id` | INT64 | no | `teams.id` | Persistent team identity for this side. Exported from source `source_team_id`. |
| `team_score` | INT64 | no | none | Match-level score for this side. |
| `average_team_rating` | DECIMAL (scale 3) | yes | none | Average public rating for players on the side. |

Excluded source columns: `expected_win_probability`, `pairing_source`,
`source_team_id`, `created_at`, `updated_at`.

### `matches`

Business description: match-level facts.

Grain: one row per exported match.

Source table: `matches`.

| Column | Type | Nullable | FK | Description |
| --- | --- | --- | --- | --- |
| `id` | INT64 | no | none | Match identifier. |
| `match_date` | STRING (ISO date) | no | none | Match date. |
| `region_id` | INT64 | yes | `regions.id` | Region where the match occurred. |
| `match_type` | STRING | no | none | Match type, such as recreational, league, ladder, tournament, challenge, or clinic. |
| `court_type` | STRING | yes | none | Court context. |
| `match_format` | STRING | yes | none | Match format descriptor. |
| `winning_team_id` | INT64 | yes | `teams.id` | Persistent team id for the winning side. |
| `total_points_played` | INT64 | yes | none | Total points across all games in the match. |
| `batch_id` | INT64 | no | `monthly_batches.id` | Monthly batch for the match. |

Excluded source columns: `tournament_id`, `predicted_winning_team_number`,
`predicted_win_probability`, `expected_competitiveness`,
`simulation_noise_factor`, `created_at`, `updated_at`.

### `monthly_batches`

Business description: monthly reporting periods in the release fact window.

Grain: one row per exported monthly batch.

Source table: `monthly_batches`.

| Column | Type | Nullable | FK | Description |
| --- | --- | --- | --- | --- |
| `id` | INT64 | no | none | Monthly batch identifier. |
| `batch_month` | STRING (ISO date) | no | none | First day of the reporting month. |
| `batch_sequence` | INT64 | no | none | Sequence number within the generation run. |
| `batch_type` | STRING | no | none | Timeline classification. |
| `active_player_count_start` | INT64 | yes | none | Active player count at month start. |
| `new_player_count` | INT64 | yes | none | Players added during the month. |
| `active_player_count_end` | INT64 | yes | none | Active player count at month end. |
| `match_count_generated` | INT64 | yes | none | Matches generated for the month. |
| `rating_update_count` | INT64 | yes | none | Rating rows generated for the month. |
| `assessment_update_count` | INT64 | yes | none | Assessment rows generated for the month. |

Excluded source columns: `generation_run_id`, `processing_status`,
`started_at`, `completed_at`, `error_message`, `created_at`, `updated_at`.

### `player_assessment_history`

Business description: player assessment observations.

Grain: one row per exported assessment observation.

Source table: `player_assessment_history`.

| Column | Type | Nullable | FK | Description |
| --- | --- | --- | --- | --- |
| `id` | INT64 | no | none | Assessment identifier. |
| `player_id` | INT64 | no | `player_master.player_id` | Assessed player. |
| `assessment_date` | STRING (ISO date) | no | none | Assessment date. |
| `assessment_type` | STRING | no | none | Assessment category. |
| `assessment_value` | DECIMAL (scale 3) | yes | none | Assessment value. |
| `confidence_score` | DECIMAL (scale 3) | yes | none | Assessment confidence score. |
| `derived_from_matches` | INT64 | yes | none | Number of matches used in the assessment. |
| `batch_id` | INT64 | no | `monthly_batches.id` | Monthly batch for the assessment row. |

Excluded source columns: `created_at`.

### `player_master`

Business description: player dimension with current public rating state as of
the release snapshot.

Grain: one row per exported player.

Source composition: `players` plus the latest eligible row from
`player_rating_history`, with `country_code` derived from the player's home
region.

| Column | Type | Nullable | FK | Description |
| --- | --- | --- | --- | --- |
| `player_id` | INT64 | no | none | Player identifier from source `players.id`. |
| `external_player_key` | STRING (UUID text) | no | none | Stable external player identifier exported as a plain string. |
| `first_name` | STRING | no | none | Player first name. |
| `last_name` | STRING | no | none | Player last name. |
| `gender` | STRING | yes | none | Player gender value. |
| `birth_date` | STRING (ISO date) | no | none | Player birth date. |
| `dominant_hand` | STRING | yes | none | Dominant hand. |
| `home_region_id` | INT64 | yes | `regions.id` | Player home region. |
| `country_code` | STRING | yes | none | Home-region country code resolved from `regions.country_code`. |
| `registration_date` | STRING (ISO date) | no | none | Date the player entered the population. |
| `player_status` | STRING | no | none | Player lifecycle status. |
| `rating` | DECIMAL (scale 3) | yes | none | Compatibility alias of `rating_value` for ranking-oriented consumers. |
| `rating_value` | DECIMAL (scale 3) | yes | none | Latest public rating before `snapshot_end_exclusive`. |
| `confidence_score` | DECIMAL (scale 3) | yes | none | Latest rating confidence score. |
| `volatility_score` | DECIMAL (scale 3) | yes | none | Latest rating volatility measure. |
| `global_percentile` | DECIMAL (scale 2) | yes | none | Latest global percentile ranking. |
| `match_count_used` | INT64 | yes | none | Match count reflected in the latest rating. |
| `rating_date` | STRING (ISO date) | yes | none | Effective date of the latest included rating row. |
| `rating_batch_id` | INT64 | yes | none | Source monthly batch for the latest included rating row. |
| `snapshot_month` | STRING (ISO date) | no | none | Release snapshot month carried on every player row. |

Excluded source columns: source `players.id` is renamed to `player_id`;
`initial_skill_seed`, `generation_run_id`, `created_at`, and `updated_at` are
not exported. `player_rating_history` is not exported as a standalone table.

### `player_registrations`

Business description: player onboarding events.

Grain: one row per exported registration event.

Source table: `player_registrations`.

| Column | Type | Nullable | FK | Description |
| --- | --- | --- | --- | --- |
| `id` | INT64 | no | none | Registration identifier. |
| `player_id` | INT64 | no | `player_master.player_id` | Registered player. |
| `batch_id` | INT64 | no | `monthly_batches.id` | Monthly batch for the event. |
| `registration_month` | STRING (ISO date) | no | none | Registration reporting month. |
| `registration_source` | STRING | yes | none | Acquisition or registration source. |
| `assigned_region_id` | INT64 | yes | `regions.id` | Region assigned at registration. |
| `initial_rating_value` | DECIMAL (scale 3) | yes | none | Initial public rating. |
| `initial_confidence_score` | DECIMAL (scale 3) | yes | none | Initial confidence score. |

Excluded source columns: `created_at`.

### `regions`

Business description: geographic markets used for player homes, clubs,
registrations, and matches.

Grain: one row per referenced region.

Source table: `regions`.

| Column | Type | Nullable | FK | Description |
| --- | --- | --- | --- | --- |
| `id` | INT64 | no | none | Region identifier. |
| `country_code` | STRING | no | none | Country code such as `US` or `CA`. |
| `region_type` | STRING | yes | none | Region classification. |
| `region_name` | STRING | no | none | Human-readable region name. |
| `state_province_code` | STRING | yes | none | State or province code when applicable. |
| `population` | INT64 | yes | none | Approximate market population. |
| `latitude` | DECIMAL (scale 6) | yes | none | Latitude. |
| `longitude` | DECIMAL (scale 6) | yes | none | Longitude. |

Excluded source columns: `selection_probability`,
`competitiveness_multiplier`, `created_at`, `updated_at`.

### `team_memberships`

Business description: player-to-team membership intervals.

Grain: one row per exported team membership interval.

Source table: `team_memberships`.

| Column | Type | Nullable | FK | Description |
| --- | --- | --- | --- | --- |
| `id` | INT64 | no | none | Team membership identifier. |
| `team_id` | INT64 | no | `teams.id` | Team joined by the player. |
| `player_id` | INT64 | no | `player_master.player_id` | Player on the team. |
| `player_position` | INT64 | no | none | Player order on the team. |
| `joined_date` | STRING (ISO date) | no | none | Membership start date. |
| `left_date` | STRING (ISO date) | yes | none | Membership end date; future left dates are projected to null. |

Excluded source columns: `created_at`, `updated_at`.

### `teams`

Business description: doubles team dimension.

Grain: one row per exported team.

Source table: `teams`.

| Column | Type | Nullable | FK | Description |
| --- | --- | --- | --- | --- |
| `id` | INT64 | no | none | Team identifier. |
| `team_type` | STRING | no | none | Team identity type: `competitive` or `ad_hoc`. |
| `team_division` | STRING | no | none | Competition category such as `mens_doubles`, `womens_doubles`, `mixed_doubles`, or `open_doubles`. |
| `team_status` | STRING | no | none | Team lifecycle status projected as of the release snapshot. |
| `country_code` | STRING | yes | none | Team country code. Expected to be populated when player-region country is known. |
| `formation_date` | STRING (ISO date) | no | none | Team formation date. |
| `dissolution_date` | STRING (ISO date) | yes | none | Team dissolution date; future dissolution dates are projected to null. |

Excluded source columns: `chemistry_score`, `persistence_probability`,
`generation_run_id`, `created_at`, `updated_at`.
