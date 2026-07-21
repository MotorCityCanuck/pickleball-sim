# Gold Source Contract

## Scope

This document defines the actual Silver input contract for the future Gold
pipeline based on the checked-in 5K clean export:

`data/student_dataset_exports/5k_12_months_eliminated_uuid_data_types/20260714/114303Z/clean/5k_12_months_eliminated_uuid_data_types_initial_history`

This contract reflects schema version `1.3` and the current export code in:

- `backend/app/exports/student_dataset/projection.py`
- `backend/app/exports/student_dataset/queries.py`

## Approved Baseline Contract

Use schema `1.4` with `player_master` as the default Gold source contract.

Do not target the older `players` plus `player_rating_history` export shape
unless the instructor explicitly re-baselines the project.

## Silver Table Inventory

- `clubs`
- `club_memberships`
- `match_games`
- `match_team_players`
- `match_teams`
- `matches`
- `monthly_batches`
- `player_assessment_history`
- `player_master`
- `player_registrations`
- `regions`
- `team_memberships`
- `teams`

## Table Contracts

### `clubs`

- Primary key: `id`
- Foreign keys:
  - `region_id -> regions.id`
- Nullable fields in physical Parquet:
  - all columns are nullable at the file-schema level
- Business-required fields from source model:
  - `id`
  - `club_name`
  - `region_id`
- Columns:
  - `id: int64`
  - `club_name: string`
  - `region_id: int64`
  - `club_type: string`
  - `competitiveness_level: string`
  - `member_capacity: int64`
  - `founding_date: string`
  - `indoor_court_count: int64`
  - `outdoor_court_count: int64`
- Derivation/filter notes:
  - founded before snapshot end
  - may also be included when referenced by included memberships

### `club_memberships`

- Primary key: `id`
- Foreign keys:
  - `player_id -> player_master.player_id`
  - `club_id -> clubs.id`
- Nullable fields in physical Parquet:
  - all columns are nullable at the file-schema level
  - `end_date` is commonly null by design
- Columns:
  - `id: int64`
  - `player_id: int64`
  - `club_id: int64`
  - `membership_type: string`
  - `start_date: string`
  - `end_date: null`
  - `is_primary: bool`
- Code values:
  - `membership_type`: `member`, `secondary`
- Derivation/filter notes:
  - `end_date` values on or after snapshot end are projected to `null`
  - suitable for as-of joins using `start_date <= as_of < coalesce(end_date, +inf)`

### `match_games`

- Primary key: `id`
- Candidate alternate key:
  - `(match_id, game_number)`
- Foreign keys:
  - `match_id -> matches.id`
- Columns:
  - `id: int64`
  - `match_id: int64`
  - `game_number: int64`
  - `team_one_score: int64`
  - `team_two_score: int64`
  - `winning_team_number: int64`
  - `target_score: int64`
  - `win_by: int64`
  - `actual_team_one_score_share: decimal128(5,4)`
- Derivation/filter notes:
  - one row per exported game for included matches

### `match_team_players`

- Primary key: `id`
- Candidate alternate keys:
  - `(match_team_id, player_position)`
  - `(match_team_id, player_id)`
- Foreign keys:
  - `match_team_id -> match_teams.id`
  - `player_id -> player_master.player_id`
- Columns:
  - `id: int64`
  - `match_team_id: int64`
  - `player_id: int64`
  - `player_position: int64`
  - `player_rating_at_match: decimal128(7,3)`
- Derivation/filter notes:
  - one row per player participating on an exported match side

### `match_teams`

- Primary key: `id`
- Candidate alternate key:
  - `(match_id, team_number)`
- Foreign keys:
  - `match_id -> matches.id`
  - `team_id -> teams.id` when populated
- Columns:
  - `id: int64`
  - `match_id: int64`
  - `team_number: int64`
  - `team_id: int64`
  - `team_score: int64`
  - `average_team_rating: decimal128(7,3)`
- Derivation/filter notes:
  - exported `team_id` is aliased from upstream `source_team_id`
  - ad hoc sides can have `team_id = null`
- Approved fallback:
  - where `team_id` is null, reconstruct or classify the side from
    membership/player history in Gold

### `matches`

- Primary key: `id`
- Foreign keys:
  - `region_id -> regions.id`
  - `winning_team_id -> match_teams.id`
  - `batch_id -> monthly_batches.id`
- Columns:
  - `id: int64`
  - `match_date: string`
  - `region_id: int64`
  - `match_type: string`
  - `court_type: string`
  - `match_format: string`
  - `winning_team_id: int64`
  - `total_points_played: int64`
  - `batch_id: int64`
- Code values:
  - `match_type`: `challenge`, `clinic`, `ladder`, `league`, `recreational`,
    `tournament`
- Approved fallback:
  - winning side can be resolved through `winning_team_id -> match_teams.id`
    even without persistent team identity

### `monthly_batches`

- Primary key: `id`
- Alternate key candidate:
  - `batch_sequence`
- Columns:
  - `id: int64`
  - `batch_month: string`
  - `batch_sequence: int64`
  - `batch_type: string`
  - `active_player_count_start: int64`
  - `new_player_count: int64`
  - `active_player_count_end: int64`
  - `match_count_generated: int64`
  - `rating_update_count: int64`
  - `assessment_update_count: null`
- Derivation/filter notes:
  - contains the selected release-window batches only
  - upstream planning requires the parent generation run to have status
    `succeeded`

### `player_assessment_history`

- Primary key: `id`
- Foreign keys:
  - `player_id -> player_master.player_id`
  - `batch_id -> monthly_batches.id`
- Columns:
  - `id: int64`
  - `player_id: int64`
  - `assessment_date: string`
  - `assessment_type: string`
  - `assessment_value: decimal128(8,3)`
  - `confidence_score: decimal128(8,3)`
  - `derived_from_matches: int64`
  - `batch_id: int64`
- Notes:
  - older artifacts may contain an all-null physical schema when no data exists
  - the 5K clean artifact has typed columns

### `player_master`

- Primary key:
  - `player_id`
- Foreign keys:
  - `home_region_id -> regions.id`
  - `rating_batch_id -> monthly_batches.id` logically, though not explicitly
    validated in projection metadata
- Columns:
  - `player_id: int64`
  - `external_player_key: string`
  - `first_name: string`
  - `last_name: string`
  - `gender: string`
  - `birth_date: string`
  - `dominant_hand: string`
  - `home_region_id: int64`
  - `registration_date: string`
  - `player_status: string`
  - `rating_value: decimal128(7,3)`
  - `confidence_score: decimal128(4,3)`
  - `volatility_score: decimal128(4,3)`
  - `global_percentile: null`
  - `match_count_used: int64`
  - `rating_date: string`
  - `rating_batch_id: int64`
  - `snapshot_month: string`
- Code values:
  - `gender`: `F`, `M`
  - `player_status`: `ACTIVE`, `INACTIVE`, `INJURED`, `RETIRED`
- Field derivations:
  - exported from source table `players`
  - joined to latest rating row as of snapshot end
  - one row per player as of the snapshot
  - `snapshot_month` is injected at export time
- Unsupported conceptual fields:
  - no direct `country_code`
- Approved fallback:
  - derive player country via `home_region_id -> regions.country_code`

### `player_registrations`

- Primary key: `id`
- Foreign keys:
  - `player_id -> player_master.player_id`
  - `batch_id -> monthly_batches.id`
  - `assigned_region_id -> regions.id`
- Columns:
  - `id: int64`
  - `player_id: int64`
  - `batch_id: int64`
  - `registration_month: string`
  - `registration_source: string`
  - `assigned_region_id: int64`
  - `initial_rating_value: decimal128(7,3)`
  - `initial_confidence_score: decimal128(4,3)`

### `regions`

- Primary key: `id`
- Columns:
  - `id: int64`
  - `country_code: string`
  - `region_type: string`
  - `region_name: string`
  - `state_province_code: string`
  - `population: int64`
  - `latitude: null`
  - `longitude: null`
- Code values:
  - `country_code`: `CA`, `US`
  - `region_type`: `CA`, `CMA`, `MSA`
- Field derivations:
  - release includes regions referenced by included players, clubs,
    registrations, or matches

### `team_memberships`

- Primary key: `id`
- Foreign keys:
  - `team_id -> teams.id`
  - `player_id -> player_master.player_id`
- Columns:
  - `id: int64`
  - `team_id: int64`
  - `player_id: int64`
  - `player_position: int64`
  - `joined_date: string`
  - `left_date: null`
- Field derivations:
  - `left_date` values on or after snapshot end are projected to `null`
- Approved fallback:
  - use as-of interval logic to reconstruct valid player-team membership at
    match or analysis time

### `teams`

- Primary key: `id`
- Columns:
  - `id: int64`
  - `team_type: string`
  - `team_status: string`
  - `country_code: string`
  - `formation_date: string`
  - `dissolution_date: string`
- Code values:
  - `team_type`: `mens_doubles`, `mixed_doubles`, `open_doubles`,
    `womens_doubles`
  - `team_status`: `active`, `dormant`, `retired`
- Field derivations:
  - exported teams are limited to the selected generation run
  - future `dissolution_date` is projected to `null`
  - if dissolution is in the future and source status is `dormant` or
    `retired`, export logic projects status back to `active` as of snapshot

## Unsupported or Missing Conceptual Fields

These concepts from the Gold specification are not directly available in the
current Silver export contract.

- Persistent match-side `team_id`
- Direct player `country_code`
- Direct player-side category on match facts
- Geographic coordinates populated in practice
- Reliable `global_percentile` values in current checked-in data

## Approved Fallbacks

- Player country:
  - derive from `player_master.home_region_id -> regions.country_code`
- Team category:
  - use `teams.team_type`
- Match winner:
  - use `matches.winning_team_id -> match_teams.id`
- Persistent team identity:
  - reconstruct via `team_memberships`, `match_team_players`, `matches`, and
    as-of logic
- Latest player rating state:
  - use fields embedded in `player_master`

## Physical-Contract Drift

The repository contains older checked-in artifacts that do not match this
contract.

Observed older shape:

- `players.parquet` instead of `player_master.parquet`
- `player_rating_history.parquet` present as a separate table
- missing `country_code` in `teams` for at least one older checked-in artifact

Gold development should not mix these shapes without an explicit compatibility
layer.

## Unresolved Questions

1. Should Gold support only schema `1.4`, or must it also support the older
   `1.0`-style `players` export shape?
2. Should Gold also retain compatibility with `1.3` exports that omitted
   `match_teams.team_id`?
3. Should the Gold release parameter be keyed by repository export family name
   or normalized to the spec names `napa_5k`, `napa_50k`, `napa_250k`?
4. Is persistent team reconstruction expected to be exact or best-effort when
   historical match sides still have `team_id = null`?
5. Should `regions.region_type='CA'` be treated as a Canadian census
   agglomeration or as a generic catch-all region bucket for Gold analytics?
6. Is `player_assessment_history` expected to remain optional for scoring, given
   that some exports may have no assessment rows?
