# Analytics Dataset Data Dictionary

## Status

Draft companion document for `student_facing_dataset_build_specification.md`.

## Scope

This data dictionary defines the analytical Parquet schema. It includes the
tables and columns approved for the production-style analytical data product.
Operational tables, configuration tables, log tables, raw data tables,
validation tables, tournaments, uploaded files, internal scoring fields, and
excluded model output columns are intentionally absent.

All files are Parquet and must be queryable with DuckDB. Column order in each
Parquet file must match the order shown here.

## Common Conventions

- Primary keys are stable entity identifiers.
- Foreign keys refer to other Parquet tables in this data product.
- Dates use DuckDB-compatible `DATE`.
- Decimal fields use DuckDB-compatible `DECIMAL(p,s)` when precision and scale
  are known.
- Boolean fields use DuckDB-compatible `BOOLEAN`.
- Nullable means the released Parquet column may contain null values.

## Entity Relationship Summary

| Table | Primary relationships |
| --- | --- |
| `regions` | Parent of `players`, `clubs`, `matches`, and `player_registrations`. |
| `monthly_batches` | Parent of monthly facts, ratings, assessments, registrations, and matches. |
| `players` | Parent of memberships, registrations, ratings, assessments, and match participation. |
| `clubs` | Parent of `club_memberships`. |
| `teams` | Parent of `team_memberships`. |
| `matches` | Parent of `match_teams` and `match_games`. |
| `match_teams` | Parent of `match_team_players`; referenced by `matches.winning_team_id`. |

## `regions`

Business description: geographic markets used for player homes, clubs, and
matches. Regions provide market context for participation, club distribution,
and match activity.

Grain: one row per region.

| Column | Type | Nullable | FK | Business description and valid values |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | no | none | Region identifier. Positive integer. |
| `country_code` | VARCHAR | no | none | Country code such as `US` or `CA`. |
| `region_type` | VARCHAR | yes | none | Region classification such as metro area, state, province, or market. |
| `region_name` | VARCHAR | no | none | Human-readable region name. |
| `state_province_code` | VARCHAR | yes | none | State or province abbreviation where applicable. |
| `population` | BIGINT | yes | none | Approximate market population. Expected to be non-negative. |
| `latitude` | DECIMAL(10,6) | yes | none | Region latitude. Expected range `-90` to `90`. |
| `longitude` | DECIMAL(10,6) | yes | none | Region longitude. Expected range `-180` to `180`. |

## `monthly_batches`

Business description: monthly reporting periods in the historical timeline.
This table supports analysis of growth, activity, ratings, and match volume by
month.

Grain: one row per monthly period included in the data snapshot.

| Column | Type | Nullable | FK | Business description and valid values |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | no | none | Monthly batch identifier. Positive integer. |
| `batch_month` | DATE | no | none | First day of the reporting month. |
| `batch_sequence` | INTEGER | no | none | Sequence number within the generation run. Starts at `1` and increases by `1`. |
| `batch_type` | VARCHAR | no | none | Timeline classification such as `historical_initial` or `future_increment`. |
| `active_player_count_start` | INTEGER | yes | none | Active player count at the start of the month. Expected to be non-negative. |
| `new_player_count` | INTEGER | yes | none | Players added during the month. Expected to be non-negative. |
| `active_player_count_end` | INTEGER | yes | none | Active player count at the end of the month. Expected to be non-negative. |
| `match_count_generated` | INTEGER | yes | none | Matches recorded for the month. Expected to be non-negative. |
| `rating_update_count` | INTEGER | yes | none | Rating history rows recorded for the month. Expected to be non-negative. |
| `assessment_update_count` | INTEGER | yes | none | Assessment history rows recorded for the month. Expected to be non-negative. |

## `players`

Business description: pickleball players available for analysis. The table
includes demographic, geography, handedness, and status fields.

Grain: one row per player included in the data snapshot.

| Column | Type | Nullable | FK | Business description and valid values |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | no | none | Player identifier. Positive integer. |
| `external_player_key` | UUID | no | none | Stable external player identifier for joins or exports. |
| `first_name` | VARCHAR | no | none | Player first name. |
| `last_name` | VARCHAR | no | none | Player last name. |
| `gender` | VARCHAR | yes | none | Player gender value. Expected values include `M`, `F`, or configured equivalents. |
| `birth_date` | DATE | no | none | Exact birth date. |
| `dominant_hand` | VARCHAR | yes | none | Dominant hand. Expected values include `RIGHT`, `LEFT`, or `AMBID`. |
| `home_region_id` | BIGINT | yes | `regions.id` | Home region for the player. |
| `registration_date` | DATE | no | none | Date the player entered the active player population. |
| `player_status` | VARCHAR | no | none | Player lifecycle status such as `ACTIVE`, `INACTIVE`, `INJURED`, or `RETIRED`. |

## `player_registrations`

Business description: player onboarding facts by month. This table supports
cohort analysis and joins newly added players to monthly batches.

Grain: one row per player registration event.

| Column | Type | Nullable | FK | Business description and valid values |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | no | none | Registration identifier. Positive integer. |
| `player_id` | BIGINT | no | `players.id` | Registered player. |
| `batch_id` | BIGINT | no | `monthly_batches.id` | Monthly period when the registration was recorded. |
| `registration_month` | DATE | no | none | Month of registration, generally the first day of the month. |
| `registration_source` | VARCHAR | yes | none | Acquisition or registration source. |
| `assigned_region_id` | BIGINT | yes | `regions.id` | Region assigned at registration. |
| `initial_rating_value` | DECIMAL(8,3) | yes | none | Initial public rating. Expected to be non-negative. |
| `initial_confidence_score` | DECIMAL(8,3) | yes | none | Initial confidence score. Expected range `0` to `1`. |

## `player_rating_history`

Business description: public player rating history over time. This table is
intended for trend analysis, player ranking, forecasting, and rating movement
assignments.

Grain: one row per player rating observation.

| Column | Type | Nullable | FK | Business description and valid values |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | no | none | Rating history identifier. Positive integer. |
| `player_id` | BIGINT | no | `players.id` | Rated player. |
| `rating_date` | DATE | no | none | Date the rating applies. |
| `rating_type` | VARCHAR | no | none | Rating category, such as initial or match update. |
| `rating_value` | DECIMAL(8,3) | no | none | Public player rating. Expected to be non-negative. |
| `confidence_score` | DECIMAL(8,3) | yes | none | Rating confidence. Expected range `0` to `1`. |
| `volatility_score` | DECIMAL(8,3) | yes | none | Rating volatility measure. Expected to be non-negative. |
| `regional_adjustment_factor` | DECIMAL(8,4) | yes | none | Public contextual adjustment factor. |
| `global_percentile` | DECIMAL(5,2) | yes | none | Global percentile ranking. Expected range `0` to `100`. |
| `match_count_used` | INTEGER | yes | none | Number of matches reflected in rating calculation. Expected to be non-negative. |
| `batch_id` | BIGINT | no | `monthly_batches.id` | Monthly batch associated with the rating row. |

## `player_assessment_history`

Business description: player assessment values recorded over time. Assessments
support analysis beyond rating alone.

Grain: one row per player assessment observation.

| Column | Type | Nullable | FK | Business description and valid values |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | no | none | Assessment history identifier. Positive integer. |
| `player_id` | BIGINT | no | `players.id` | Assessed player. |
| `assessment_date` | DATE | no | none | Date the assessment applies. |
| `assessment_type` | VARCHAR | no | none | Assessment category. |
| `assessment_value` | DECIMAL(8,3) | yes | none | Public assessment score. Expected range depends on assessment type. |
| `confidence_score` | DECIMAL(8,3) | yes | none | Assessment confidence. Expected range `0` to `1`. |
| `derived_from_matches` | INTEGER | yes | none | Number of matches used to derive the assessment. Expected to be non-negative. |
| `batch_id` | BIGINT | no | `monthly_batches.id` | Monthly batch associated with the assessment row. |

## `clubs`

Business description: pickleball clubs, parks, facilities, and club
organizations. Clubs provide context for memberships, geography, facility size,
and competitive environment.

Grain: one row per club.

| Column | Type | Nullable | FK | Business description and valid values |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | no | none | Club identifier. Positive integer. |
| `club_name` | VARCHAR | no | none | Club name. |
| `region_id` | BIGINT | no | `regions.id` | Region where the club is located. |
| `club_type` | VARCHAR | yes | none | Club classification such as public park, private club, or dedicated facility. |
| `competitiveness_level` | VARCHAR | yes | none | Club competitive segment such as recreational or competitive. |
| `member_capacity` | INTEGER | yes | none | Approximate member capacity. Expected to be non-negative. |
| `founding_date` | DATE | yes | none | Club founding date. |
| `indoor_court_count` | INTEGER | yes | none | Number of indoor courts. Expected to be non-negative. |
| `outdoor_court_count` | INTEGER | yes | none | Number of outdoor courts. Expected to be non-negative. |

## `club_memberships`

Business description: player membership relationships to clubs. This table
supports analysis of club affiliation, multi-club behavior, membership tenure,
and geographic participation.

Grain: one row per player-club membership interval.

| Column | Type | Nullable | FK | Business description and valid values |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | no | none | Club membership identifier. Positive integer. |
| `player_id` | BIGINT | no | `players.id` | Member player. |
| `club_id` | BIGINT | no | `clubs.id` | Club joined by the player. |
| `membership_type` | VARCHAR | yes | none | Membership category. Default expected value is `member`. |
| `start_date` | DATE | no | none | Membership start date. |
| `end_date` | DATE | yes | none | Membership end date. Null means active/open-ended. |
| `is_primary` | BOOLEAN | yes | none | Whether this is the player's primary club membership. |

## `teams`

Business description: doubles teams. Teams connect players over time and
support analysis of partnership, chemistry, lifecycle, and performance.

Grain: one row per team.

| Column | Type | Nullable | FK | Business description and valid values |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | no | none | Team identifier. Positive integer. |
| `team_type` | VARCHAR | no | none | Team category such as mens doubles, womens doubles, mixed doubles, or open doubles. |
| `team_status` | VARCHAR | no | none | Team lifecycle status such as active or dormant. |
| `formation_date` | DATE | no | none | Date the team formed. |
| `dissolution_date` | DATE | yes | none | Date the team dissolved. Null means not dissolved. |
| `chemistry_score` | DECIMAL(8,4) | yes | none | Public team chemistry metric. Expected range is generally `0` to `1`. |
| `persistence_probability` | DECIMAL(5,4) | yes | none | Public estimate of team persistence. Expected range `0` to `1`. |

## `team_memberships`

Business description: player membership intervals on teams. This table supports
analysis of player partnerships and team composition over time.

Grain: one row per player-team membership interval.

| Column | Type | Nullable | FK | Business description and valid values |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | no | none | Team membership identifier. Positive integer. |
| `team_id` | BIGINT | no | `teams.id` | Team joined by the player. |
| `player_id` | BIGINT | no | `players.id` | Player on the team. |
| `player_position` | INTEGER | no | none | Player position/order on the team. Expected values are positive integers. |
| `joined_date` | DATE | no | none | Team membership start date. |
| `left_date` | DATE | yes | none | Team membership end date. Null means active/open-ended. |

## `matches`

Business description: match-level facts. This table captures when and where a
match occurred, what type of match it was, who won, and how many total points
were played.

Grain: one row per match.

| Column | Type | Nullable | FK | Business description and valid values |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | no | none | Match identifier. Positive integer. |
| `match_date` | DATE | no | none | Date the match was played. |
| `region_id` | BIGINT | yes | `regions.id` | Region where the match occurred. |
| `match_type` | VARCHAR | no | none | Match classification such as recreational, league, or tournament-style. |
| `court_type` | VARCHAR | yes | none | Court context such as indoor or outdoor. |
| `match_format` | VARCHAR | yes | none | Match format descriptor. |
| `winning_team_id` | BIGINT | yes | `match_teams.id` | Match team row for the winning side. |
| `total_points_played` | INTEGER | yes | none | Total points across all games in the match. Expected to be non-negative. |
| `batch_id` | BIGINT | no | `monthly_batches.id` | Monthly batch associated with the match. |

## `match_teams`

Business description: the two sides that participated in a match, including
team number, final match score, and average team rating.

Grain: one row per side in a match, normally two rows per match.

| Column | Type | Nullable | FK | Business description and valid values |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | no | none | Match team identifier. Positive integer. |
| `match_id` | BIGINT | no | `matches.id` | Match that this side belongs to. |
| `team_number` | INTEGER | no | none | Side number within the match. Expected values are `1` or `2`. |
| `team_score` | INTEGER | no | none | Match-level score for this side. Expected to be non-negative. |
| `average_team_rating` | DECIMAL(8,3) | yes | none | Average public rating of players on this side at match time. |

## `match_team_players`

Business description: player participation on a match side. This table connects
players to the match teams they played on and records their rating snapshot at
match time.

Grain: one row per player participating on a match team.

| Column | Type | Nullable | FK | Business description and valid values |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | no | none | Match team player identifier. Positive integer. |
| `match_team_id` | BIGINT | no | `match_teams.id` | Match side that the player participated on. |
| `player_id` | BIGINT | no | `players.id` | Participating player. |
| `player_position` | INTEGER | yes | none | Player order on the match side. Expected values are positive integers. |
| `player_rating_at_match` | DECIMAL(8,3) | yes | none | Public rating snapshot at the time of the match. |

## `match_games`

Business description: game-level scores within a match. A match can contain one
or more games, and this table provides the detailed score sequence.

Grain: one row per game within a match.

| Column | Type | Nullable | FK | Business description and valid values |
| --- | --- | --- | --- | --- |
| `id` | BIGINT | no | none | Match game identifier. Positive integer. |
| `match_id` | BIGINT | no | `matches.id` | Match containing the game. |
| `game_number` | INTEGER | no | none | Game sequence within the match. Starts at `1`. |
| `team_one_score` | INTEGER | no | none | Score for team number `1`. Expected to be non-negative. |
| `team_two_score` | INTEGER | no | none | Score for team number `2`. Expected to be non-negative. |
| `winning_team_number` | INTEGER | no | none | Winning side number. Expected values are `1` or `2`. |
| `target_score` | INTEGER | yes | none | Target score for the game. Expected to be positive when present. |
| `win_by` | INTEGER | yes | none | Required winning margin. Expected to be positive when present. |
| `actual_team_one_score_share` | DECIMAL(8,4) | yes | none | Team one share of points in the game. Expected range `0` to `1`. |
