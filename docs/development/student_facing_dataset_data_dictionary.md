# Analytics Dataset Data Dictionary

## Status

Current companion document for
`docs/development/student_facing_dataset_build_specification.md`.

This dictionary is aligned to the current checked-in `player_master` release
artifact under:

```text
scripts/data/student_dataset_exports/napa_olympic_analytics_v1_test
```

Older checked-in release folders that still publish `players.parquet` and
`player_rating_history.parquet` are legacy artifacts and are not the contract
documented here.

## Scope

This data dictionary defines the released analytical Parquet schema for the
student dataset export.

The contract is:

- baseline plus monthly incrementals,
- operational-style analytical tables,
- `player_master` as the published player dimension,
- DuckDB-friendly column names and ordering.

Operational tables, raw data tables, validation tables, tournament tables,
hidden generator fields, and non-exported source tables are intentionally
absent.

## Common Conventions

- Primary keys are stable exported identifiers.
- Foreign keys refer to other Parquet tables in this release contract.
- Dates use DuckDB-compatible `DATE`.
- Numeric score and rating fields use DuckDB-compatible decimal types when
  precision is known.
- Nullable means the Parquet column may contain null values.

## Entity Relationship Summary

| Table | Primary relationships |
| --- | --- |
| `regions` | Parent of `player_master`, `clubs`, `matches`, and `player_registrations`. |
| `monthly_batches` | Parent of exported batch-tied fact tables. |
| `player_master` | Parent of memberships, registrations, assessments, and match participation. |
| `clubs` | Parent of `club_memberships`. |
| `teams` | Parent of `team_memberships`; referenced by match side `team_id` and match `winning_team_id`. |
| `matches` | Parent of `match_teams` and `match_games`. |
| `match_teams` | Parent of `match_team_players`. |

## `regions`

Business description: geographic markets used for player homes, clubs, and
matches.

Grain: one row per exported region.

| Column | Type | Nullable | FK | Description |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | no | none | Region identifier. |
| `country_code` | VARCHAR | no | none | Country code such as `US` or `CA`. |
| `region_type` | VARCHAR | yes | none | Region classification. |
| `region_name` | VARCHAR | no | none | Human-readable region name. |
| `state_province_code` | VARCHAR | yes | none | State or province code when applicable. |
| `population` | BIGINT | yes | none | Approximate market population. |
| `latitude` | DECIMAL(10,6) | yes | none | Latitude. |
| `longitude` | DECIMAL(10,6) | yes | none | Longitude. |

## `monthly_batches`

Business description: monthly reporting periods emitted in the release fact
window.

Grain: one row per exported monthly batch.

| Column | Type | Nullable | FK | Description |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | no | none | Monthly batch identifier. |
| `batch_month` | DATE | no | none | First day of the reporting month. |
| `batch_sequence` | INTEGER | no | none | Sequence number within the generation run. |
| `batch_type` | VARCHAR | no | none | Timeline classification. |
| `active_player_count_start` | INTEGER | yes | none | Active player count at month start. |
| `new_player_count` | INTEGER | yes | none | Players added during the month. |
| `active_player_count_end` | INTEGER | yes | none | Active player count at month end. |
| `match_count_generated` | INTEGER | yes | none | Matches recorded for the month. |
| `rating_update_count` | INTEGER | yes | none | Rating rows generated for the month. |
| `assessment_update_count` | INTEGER | yes | none | Assessment rows generated for the month. |

## `player_master`

Business description: snapshot-scoped player dimension containing player
identity plus the latest available rating state as of the release snapshot
month.

Grain: one row per exported player.

| Column | Type | Nullable | FK | Description |
| --- | --- | --- | --- | --- |
| `player_id` | BIGINT | no | none | Player identifier. |
| `external_player_key` | UUID-formatted string | no | none | Stable external player identifier exported as a plain string column. |
| `first_name` | VARCHAR | no | none | Player first name. |
| `last_name` | VARCHAR | no | none | Player last name. |
| `gender` | VARCHAR | yes | none | Player gender value. |
| `birth_date` | DATE | no | none | Birth date. |
| `dominant_hand` | VARCHAR | yes | none | Dominant hand. |
| `home_region_id` | BIGINT | yes | `regions.id` | Home region. |
| `registration_date` | DATE | no | none | Date the player entered the population. |
| `player_status` | VARCHAR | no | none | Player lifecycle status. |
| `rating_value` | DECIMAL(8,3) | yes | none | Latest public rating as of the snapshot. |
| `confidence_score` | DECIMAL(8,3) | yes | none | Latest rating confidence score. |
| `volatility_score` | DECIMAL(8,3) | yes | none | Latest rating volatility measure. |
| `global_percentile` | DECIMAL(5,2) | yes | none | Latest global percentile ranking. |
| `match_count_used` | INTEGER | yes | none | Match count reflected in the latest rating. |
| `rating_date` | DATE | yes | none | Effective date of the latest included rating row. |
| `rating_batch_id` | BIGINT | yes | none | Source monthly batch for the latest included rating row. |
| `snapshot_month` | DATE | no | none | Release snapshot month carried on every row. |

## `player_registrations`

Business description: player onboarding fact rows for exported fact batches.

Grain: one row per exported registration event.

| Column | Type | Nullable | FK | Description |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | no | none | Registration identifier. |
| `player_id` | BIGINT | no | `player_master.player_id` | Registered player. |
| `batch_id` | BIGINT | no | `monthly_batches.id` | Monthly batch for the event. |
| `registration_month` | DATE | no | none | Registration reporting month. |
| `registration_source` | VARCHAR | yes | none | Acquisition or registration source. |
| `assigned_region_id` | BIGINT | yes | `regions.id` | Region assigned at registration. |
| `initial_rating_value` | DECIMAL(8,3) | yes | none | Initial public rating. |
| `initial_confidence_score` | DECIMAL(8,3) | yes | none | Initial confidence score. |

## `player_assessment_history`

Business description: player assessment fact rows for exported fact batches.

Grain: one row per exported assessment observation.

| Column | Type | Nullable | FK | Description |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | no | none | Assessment identifier. |
| `player_id` | BIGINT | no | `player_master.player_id` | Assessed player. |
| `assessment_date` | DATE | no | none | Assessment date. |
| `assessment_type` | VARCHAR | no | none | Assessment category. |
| `assessment_value` | DECIMAL(8,3) | yes | none | Assessment value. |
| `confidence_score` | DECIMAL(8,3) | yes | none | Assessment confidence. |
| `derived_from_matches` | INTEGER | yes | none | Number of matches used in the assessment. |
| `batch_id` | BIGINT | no | `monthly_batches.id` | Monthly batch for the assessment row. |

## `clubs`

Business description: pickleball clubs, facilities, and organizations.

Grain: one row per exported club.

| Column | Type | Nullable | FK | Description |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | no | none | Club identifier. |
| `club_name` | VARCHAR | no | none | Club name. |
| `region_id` | BIGINT | no | `regions.id` | Club region. |
| `club_type` | VARCHAR | yes | none | Club classification. |
| `competitiveness_level` | VARCHAR | yes | none | Club competitive segment. |
| `member_capacity` | INTEGER | yes | none | Approximate member capacity. |
| `founding_date` | DATE | yes | none | Club founding date. |
| `indoor_court_count` | INTEGER | yes | none | Indoor court count. |
| `outdoor_court_count` | INTEGER | yes | none | Outdoor court count. |

## `club_memberships`

Business description: player-to-club membership intervals projected to the
release snapshot state.

Grain: one row per exported club membership interval.

| Column | Type | Nullable | FK | Description |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | no | none | Club membership identifier. |
| `player_id` | BIGINT | no | `player_master.player_id` | Member player. |
| `club_id` | BIGINT | no | `clubs.id` | Club joined by the player. |
| `membership_type` | VARCHAR | yes | none | Membership category. |
| `start_date` | DATE | no | none | Membership start date. |
| `end_date` | DATE | yes | none | Membership end date; null means active/open-ended. |
| `is_primary` | BOOLEAN | yes | none | Whether this is the player's primary club membership. |

## `teams`

Business description: doubles teams projected to the release snapshot state.

Grain: one row per exported team.

| Column | Type | Nullable | FK | Description |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | no | none | Team identifier. |
| `team_type` | VARCHAR | no | none | Team identity type: `competitive` or `ad_hoc`. |
| `team_division` | VARCHAR | no | none | Competition category, such as `mens_doubles`, `womens_doubles`, `mixed_doubles`, or `open_doubles`. |
| `team_status` | VARCHAR | no | none | Team lifecycle status as of the snapshot. |
| `country_code` | VARCHAR | yes | none | Team country code. |
| `formation_date` | DATE | no | none | Team formation date. |
| `dissolution_date` | DATE | yes | none | Team dissolution date; future values are suppressed in earlier snapshots. |

## `team_memberships`

Business description: player-to-team membership intervals projected to the
release snapshot state.

Grain: one row per exported team membership interval.

| Column | Type | Nullable | FK | Description |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | no | none | Team membership identifier. |
| `team_id` | BIGINT | no | `teams.id` | Team joined by the player. |
| `player_id` | BIGINT | no | `player_master.player_id` | Player on the team. |
| `player_position` | INTEGER | no | none | Player order on the team. |
| `joined_date` | DATE | no | none | Membership start date. |
| `left_date` | DATE | yes | none | Membership end date; future values are suppressed in earlier snapshots. |

## `matches`

Business description: match-level facts for exported fact batches.

Grain: one row per exported match.

| Column | Type | Nullable | FK | Description |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | no | none | Match identifier. |
| `match_date` | DATE | no | none | Match date. |
| `region_id` | BIGINT | yes | `regions.id` | Match region. |
| `match_type` | VARCHAR | no | none | Match classification. |
| `court_type` | VARCHAR | yes | none | Court context. |
| `match_format` | VARCHAR | yes | none | Match format descriptor. |
| `winning_team_id` | BIGINT | yes | `teams.id` | Persistent team id for the winning side; it must match one of the two `match_teams.team_id` values for the match. |
| `total_points_played` | INTEGER | yes | none | Total points across all games in the match. |
| `batch_id` | BIGINT | no | `monthly_batches.id` | Monthly batch for the match. |

## `match_teams`

Business description: side-level fact rows within exported matches.

Grain: one row per exported match side.

| Column | Type | Nullable | FK | Description |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | no | none | Match team identifier. |
| `match_id` | BIGINT | no | `matches.id` | Match containing this side. |
| `team_number` | INTEGER | no | none | Side number within the match. |
| `team_id` | BIGINT | no | `teams.id` | Persistent team id for this match side. |
| `team_score` | INTEGER | no | none | Match-level score for the side. |
| `average_team_rating` | DECIMAL(8,3) | yes | none | Average public rating for players on the side. |

## `match_team_players`

Business description: player participation rows within exported match teams.

Grain: one row per exported player on a match team.

| Column | Type | Nullable | FK | Description |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | no | none | Match team player identifier. |
| `match_team_id` | BIGINT | no | `match_teams.id` | Match team row. |
| `player_id` | BIGINT | no | `player_master.player_id` | Participating player. |
| `player_position` | INTEGER | yes | none | Player order on the side. |
| `player_rating_at_match` | DECIMAL(8,3) | yes | none | Rating snapshot at match time. |

## `match_games`

Business description: game-level score rows within exported matches.

Grain: one row per exported game.

| Column | Type | Nullable | FK | Description |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | no | none | Match game identifier. |
| `match_id` | BIGINT | no | `matches.id` | Match containing the game. |
| `game_number` | INTEGER | no | none | Game sequence within the match. |
| `team_one_score` | INTEGER | no | none | Score for team number `1`. |
| `team_two_score` | INTEGER | no | none | Score for team number `2`. |
| `winning_team_number` | INTEGER | no | none | Winning side number. |
| `target_score` | INTEGER | yes | none | Target score for the game. |
| `win_by` | INTEGER | yes | none | Required winning margin. |
| `actual_team_one_score_share` | DECIMAL(8,4) | yes | none | Team one share of points in the game. |
