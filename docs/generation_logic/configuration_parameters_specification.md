# Configuration Parameters Specification

**Pickleball Simulation Platform - Authoritative Configuration Schema**

**Document Purpose**: This document defines all configurable parameters used throughout the simulation platform, standardizing naming conventions, data types, defaults, and valid ranges.

**Version**: 1.0  
**Last Updated**: 2024-05-10

---

## 1. Configuration Principles

1. **snake_case** naming for all parameters
2. All probabilities are decimal values between 0.0 and 1.0
3. All percentages are expressed as decimals (e.g., 0.02 for 2%)
4. All multipliers are decimal values (typically 0.5 to 2.0 range)
5. All noise parameters include units (e.g., rating_points, probability_shift)
6. All date parameters use ISO 8601 format (YYYY-MM-DD)
7. All configuration must be serializable to YAML/JSON and JSONB

---

## 2. Global Simulation Parameters

| Parameter Name | Type | Default | Range/Options | Units | Description |
|----------------|------|---------|---------------|-------|-------------|
| `master_seed` | INTEGER | (required) | > 0 | - | Master random seed for reproducibility |
| `simulation_version` | STRING | "1.0" | semantic version | - | Platform version identifier |
| `simulation_name` | STRING | (required) | max 255 chars | - | Human-readable simulation name |
| `target_total_players` | INTEGER | 50000 | 1000-10000000 | players | Total player population target |
| `historical_batch_count` | INTEGER | 12 | 1-36 | months | Number of historical months to generate |
| `generation_run_mode` | ENUM | "full" | full, historical_only, incremental | - | Execution mode |

---

## 3. Player Generation Parameters

| Parameter Name | Type | Default | Range/Options | Units | Description |
|----------------|------|---------|---------------|-------|-------------|
| `monthly_player_growth_rate` | DECIMAL | 0.02 | 0.0-0.10 | decimal | Monthly new player growth (2% default) |
| `initial_player_count` | INTEGER | (calculated) | - | players | Starting player population (calculated from growth) |
| `player_gender_distribution_male` | DECIMAL | 0.50 | 0.0-1.0 | probability | Probability of male player |
| `player_gender_distribution_female` | DECIMAL | 0.50 | 0.0-1.0 | probability | Probability of female player |
| `player_age_min` | INTEGER | 18 | 18-100 | years | Minimum player age |
| `player_age_max` | INTEGER | 85 | 18-100 | years | Maximum player age |
| `player_age_distribution_18_29` | DECIMAL | 0.08 | 0.0-1.0 | probability | Age cohort 18-29 weight |
| `player_age_distribution_30_44` | DECIMAL | 0.18 | 0.0-1.0 | probability | Age cohort 30-44 weight |
| `player_age_distribution_45_59` | DECIMAL | 0.32 | 0.0-1.0 | probability | Age cohort 45-59 weight |
| `player_age_distribution_60_74` | DECIMAL | 0.34 | 0.0-1.0 | probability | Age cohort 60-74 weight |
| `player_age_distribution_75_plus` | DECIMAL | 0.08 | 0.0-1.0 | probability | Age cohort 75+ weight |
| `dominant_hand_right_probability` | DECIMAL | 0.88 | 0.5-1.0 | probability | Right-handed player probability |
| `dominant_hand_left_probability` | DECIMAL | 0.10 | 0.0-0.5 | probability | Left-handed player probability |
| `dominant_hand_ambidextrous_probability` | DECIMAL | 0.02 | 0.0-0.1 | probability | Ambidextrous player probability |
| `player_status_active_probability` | DECIMAL | 0.94 | 0.0-1.0 | probability | Initial active player status probability |
| `player_status_injured_probability` | DECIMAL | 0.02 | 0.0-0.2 | probability | Initial injured player status probability |
| `player_status_retired_probability` | DECIMAL | 0.02 | 0.0-0.2 | probability | Initial retired player status probability |
| `player_status_inactive_probability` | DECIMAL | 0.02 | 0.0-0.2 | probability | Initial inactive player status probability |
| `initial_skill_seed_mean` | DECIMAL | 1500.0 | 500-3500 | skill_points | Mean initial hidden skill seed |
| `initial_skill_seed_std_dev` | DECIMAL | 275.0 | 25-1000 | skill_points | Standard deviation for initial hidden skill seed |
| `initial_skill_seed_lower_bias` | DECIMAL | 100.0 | 0-500 | skill_points | Downward bias applied after sampling to modestly favor lower initial skill |
| `initial_skill_seed_min` | DECIMAL | 500.0 | 0-3500 | skill_points | Minimum initial hidden skill seed |
| `initial_skill_seed_max` | DECIMAL | 3500.0 | 500-5000 | skill_points | Maximum initial hidden skill seed |
| `name_assignment_noise_rate` | DECIMAL | 0.03 | 0.0-0.10 | probability | Small probability of intentionally imperfect regional name selection |

---

## 4. Rating and Assessment Parameters

| Parameter Name | Type | Default | Range/Options | Units | Description |
|----------------|------|---------|---------------|-------|-------------|
| `initial_rating_mean` | DECIMAL | 1500.0 | 1000-2500 | rating_points | Mean initial player rating |
| `initial_rating_std_dev` | DECIMAL | 200.0 | 50-500 | rating_points | Standard deviation of initial rating |
| `rating_min` | DECIMAL | 0.0 | 0 | rating_points | Minimum allowed rating |
| `rating_max` | DECIMAL | 5000.0 | 3000-10000 | rating_points | Maximum allowed rating |
| `initial_rating_elite_tail_rate` | DECIMAL | 0.003 | 0.0-0.02 | probability | Small share of initial players sampled from the elite rating tail |
| `initial_rating_elite_min` | DECIMAL | 4000.0 | 3000-5000 | rating_points | Lower bound for elite-tail initial ratings |
| `initial_rating_elite_max` | DECIMAL | 4500.0 | 3000-5000 | rating_points | Upper bound for elite-tail initial ratings |
| `initial_confidence_score` | DECIMAL | 0.10 | 0.0-1.0 | probability | Starting confidence for new players |
| `confidence_min` | DECIMAL | 0.0 | 0.0-1.0 | probability | Minimum confidence score |
| `confidence_max` | DECIMAL | 1.0 | 0.0-1.0 | probability | Maximum confidence score |
| `k_factor_new_player` | DECIMAL | 48.0 | 16-64 | rating_change_multiplier | K-factor for new players (<10 matches) |
| `k_factor_established` | DECIMAL | 24.0 | 16-64 | rating_change_multiplier | K-factor for established players |
| `k_factor_elite` | DECIMAL | 16.0 | 8-32 | rating_change_multiplier | K-factor for elite stable players |
| `rating_noise_std_dev` | DECIMAL | 75.0 | 0-200 | rating_points | Match performance noise standard deviation |
| `confidence_recency_half_life_days` | DECIMAL | 90.0 | 30-365 | days | Confidence decay half-life |

---

## 5. Regional Distribution Parameters

| Parameter Name | Type | Default | Range/Options | Units | Description |
|----------------|------|---------|---------------|-------|-------------|
| `region_population_weight` | DECIMAL | 1.0 | 0.1-2.0 | multiplier | Regional population scaling factor |
| `competitiveness_multiplier_default` | DECIMAL | 1.0 | 0.5-2.0 | multiplier | Default regional competitiveness |
| `competitiveness_noise_std_dev` | DECIMAL | 0.05 | 0.0-0.25 | multiplier | Noise added to regional competitiveness |
| `min_players_per_region` | INTEGER | 100 | 10-1000 | players | Minimum regional player allocation |

### Regional Multiplier Examples (Configurable per Region)

| Region | Multiplier | Rationale |
|--------|-----------|-----------|
| Naples, FL | 1.25 | High pickleball density |
| Phoenix, AZ | 1.15 | Retirement population |
| Austin, TX | 1.10 | High participation |
| Toronto, ON | 1.05 | Major metro |
| Rural cold climates | 0.85 | Lower participation |

---

## 6. Club Generation Parameters

| Parameter Name | Type | Default | Range/Options | Units | Description |
|----------------|------|---------|---------------|-------|-------------|
| `clubs_per_75k_population` | DECIMAL | 1.0 | 0.5-3.0 | clubs/population | Club density ratio |
| `club_size_distribution_small` | DECIMAL | 0.35 | 0.0-1.0 | probability | Small clubs (10-30 members) |
| `club_size_distribution_medium` | DECIMAL | 0.40 | 0.0-1.0 | probability | Medium clubs (31-75 members) |
| `club_size_distribution_large` | DECIMAL | 0.20 | 0.0-1.0 | probability | Large clubs (76-200 members) |
| `club_size_distribution_very_large` | DECIMAL | 0.04 | 0.0-1.0 | probability | Very large clubs (201-500 members) |
| `club_size_distribution_mega` | DECIMAL | 0.01 | 0.0-1.0 | probability | Mega clubs (500+ members) |
| `club_assignment_noise_std_dev` | DECIMAL | 0.10 | 0.0-0.5 | probability_shift | Club assignment randomness |
| `unaffiliated_player_rate` | DECIMAL | 0.12 | 0.0-0.30 | probability | Players without primary club |
| `multi_club_membership_rate` | DECIMAL | 0.06 | 0.0-0.20 | probability | Affiliated players with secondary club memberships |
| `min_club_memberships_per_affiliated_player` | INTEGER | 1 | 1-3 | memberships | Minimum club memberships for affiliated players |
| `max_club_memberships_per_player` | INTEGER | 3 | 1-5 | memberships | Maximum active club memberships for any player |
| `secondary_membership_same_region_rate` | DECIMAL | 0.85 | 0.0-1.0 | probability | Share of secondary club memberships constrained to the player's primary region |

---

## 7. Team Formation Parameters

| Parameter Name | Type | Default | Range/Options | Units | Description |
|----------------|------|---------|---------------|-------|-------------|
| `target_team_count` | INTEGER/null | null | null or >0 | teams | Optional explicit team count target; null derives demand from eligible players |
| `player_team_participation_rate` | DECIMAL | 0.70 | 0.0-1.0 | probability | Share of eligible players assigned to at least one active team in a batch |
| `multi_team_player_rate` | DECIMAL | 0.08 | 0.0-0.30 | probability | Share of team-participating players allowed on multiple active teams |
| `max_active_teams_per_player` | INTEGER | 2 | 1-5 | teams | Maximum active teams per player when multiple active teams are allowed |
| `same_club_team_rate` | DECIMAL | 0.78 | 0.0-1.0 | probability | Share of new teams whose partners should share a club when feasible |
| `same_region_team_rate` | DECIMAL | 0.95 | 0.0-1.0 | probability | Share of new teams whose partners should share a region when feasible |
| `rating_gap_mean` | DECIMAL | 175.0 | 0-1000 | rating_points | Target average rating gap between team partners |
| `rating_gap_std_dev` | DECIMAL | 125.0 | 0-1000 | rating_points | Variation in acceptable rating gap during partner selection |
| `rating_gap_max` | DECIMAL | 1500.0 | 0-2500 | rating_points | Maximum allowed rating gap between partners for newly formed teams, especially open-play teams |
| `team_type_weights` | OBJECT | see defaults | probabilities sum to 1 | probability | Distribution across mens, womens, mixed, and open doubles teams |
| `team_persistence_probability_recreational` | DECIMAL | 0.72 | 0.3-0.95 | probability | Recreational team retention rate |
| `team_persistence_probability_competitive` | DECIMAL | 0.88 | 0.5-0.98 | probability | Competitive team retention rate |
| `dormant_team_reactivation_rate` | DECIMAL | 0.04 | 0.0-0.30 | probability | Monthly chance that an eligible dormant partnership reforms |
| `retired_team_rate_on_dissolution` | DECIMAL | 0.10 | 0.0-1.0 | probability | Share of dissolved teams marked retired instead of dormant |
| `team_chemistry_weight` | DECIMAL | 0.35 | 0.0-1.0 | weight | Weight of chemistry in team formation |
| `team_skill_balance_weight` | DECIMAL | 0.25 | 0.0-1.0 | weight | Weight of rating balance |
| `team_club_proximity_weight` | DECIMAL | 0.25 | 0.0-1.0 | weight | Weight of shared-club proximity in partner scoring |
| `team_region_proximity_weight` | DECIMAL | 0.10 | 0.0-1.0 | weight | Weight of regional proximity in partner scoring |
| `team_prior_partnership_weight` | DECIMAL | 0.20 | 0.0-1.0 | weight | Weight of prior partnership history in partner scoring |
| `team_noise_factor` | DECIMAL | 0.15 | 0.0-0.5 | probability_shift | Random variation in team formation |
| `monthly_team_dissolution_rate` | DECIMAL | 0.10 | 0.0-0.5 | probability | Monthly probability that an active team dissolves or becomes dormant |
| `allow_multiple_active_teams_per_scope` | BOOLEAN | false | true/false | flag | Whether a player can be active on multiple teams in the same scheduling scope |

---

## 8. Match Scheduling Parameters

| Parameter Name | Type | Default | Range/Options | Units | Description |
|----------------|------|---------|---------------|-------|-------------|
| `monthly_matches_per_active_player_mean` | DECIMAL | 8.0 | 1.0-30.0 | matches | Average matches per player per month |
| `monthly_matches_per_active_player_std_dev` | DECIMAL | 4.0 | 1.0-15.0 | matches | Standard deviation of match frequency |
| `weekend_concentration_bias` | DECIMAL | 1.75 | 1.0-3.0 | multiplier | Weekend date probability multiplier |
| `saturday_weight` | DECIMAL | 2.25 | 1.0-4.0 | weight | Saturday match concentration |
| `sunday_weight` | DECIMAL | 1.85 | 1.0-4.0 | weight | Sunday match concentration |
| `friday_weight` | DECIMAL | 1.20 | 0.5-2.0 | weight | Friday match concentration |
| `weekday_evening_weight` | DECIMAL | 1.00 | 0.3-1.5 | weight | Monday-Thursday weight |
| `league_weekday_multiplier` | DECIMAL | 1.40 | 1.0-2.5 | multiplier | League play weekday boost |
| `tournament_weekend_multiplier` | DECIMAL | 2.50 | 1.5-4.0 | multiplier | Tournament weekend concentration |
| `max_daily_match_share` | DECIMAL | 0.08 | 0.03-0.15 | probability | Maximum matches on single day |
| `date_allocation_noise_level` | ENUM | "medium" | low, medium, high | - | Day-of-month allocation noise |

---

## 9. Match Type Distribution Parameters

| Parameter Name | Type | Default | Range/Options | Units | Description |
|----------------|------|---------|---------------|-------|-------------|
| `match_type_recreational` | DECIMAL | 0.55 | 0.0-1.0 | probability | Recreational/open play matches |
| `match_type_league` | DECIMAL | 0.20 | 0.0-1.0 | probability | League matches |
| `match_type_ladder` | DECIMAL | 0.10 | 0.0-1.0 | probability | Ladder matches |
| `match_type_tournament` | DECIMAL | 0.10 | 0.0-1.0 | probability | Tournament matches |
| `match_type_challenge` | DECIMAL | 0.04 | 0.0-1.0 | probability | Challenge matches |
| `match_type_clinic` | DECIMAL | 0.01 | 0.0-1.0 | probability | Clinic/event matches |

---

## 10. Matchmaking Parameters

| Parameter Name | Type | Default | Range/Options | Units | Description |
|----------------|------|---------|---------------|-------|-------------|
| `rating_band_width_recreational` | DECIMAL | 400.0 | 100-1000 | rating_points | Rating tolerance for recreational |
| `rating_band_width_competitive` | DECIMAL | 150.0 | 50-400 | rating_points | Rating tolerance for competitive |
| `rating_band_width_tournament` | DECIMAL | 100.0 | 25-250 | rating_points | Rating tolerance for tournaments |
| `matchmaking_noise_factor` | DECIMAL | 0.20 | 0.0-0.5 | probability_shift | Randomness in opponent selection |
| `rematch_penalty_window_days` | INTEGER | 30 | 7-90 | days | Repeat opponent penalty window |
| `locality_weight` | DECIMAL | 0.30 | 0.0-1.0 | weight | Geographic proximity weight |
| `ideal_matchup_probability` | DECIMAL | 0.65 | 0.3-0.9 | probability | Well-balanced match target rate |
| `slight_mismatch_probability` | DECIMAL | 0.25 | 0.1-0.5 | probability | Moderate mismatch rate |
| `significant_mismatch_probability` | DECIMAL | 0.08 | 0.0-0.3 | probability | Large mismatch rate |
| `chaos_matchup_probability` | DECIMAL | 0.02 | 0.0-0.1 | probability | Random pairing rate |

---

## 11. Game and Score Generation Parameters

| Parameter Name | Type | Default | Range/Options | Units | Description |
|----------------|------|---------|---------------|-------|-------------|
| `games_per_match_recreational` | INTEGER | 1 | 1-5 | games | Games for recreational matches |
| `games_per_match_league` | INTEGER | 2 | 1-5 | games | Games for league matches |
| `games_per_match_tournament` | INTEGER | 3 | 1-5 | games | Games for tournament matches (best-of-3) |
| `score_noise_std_dev` | DECIMAL | 1.5 | 0.0-5.0 | points | Score outcome randomness |
| `upset_probability_boost` | DECIMAL | 0.15 | 0.0-0.4 | probability_shift | Underdog win probability boost |
| `win_by_two_rule_enabled` | BOOLEAN | true | true, false | - | Enforce win-by-two rule |
| `game_target_score` | INTEGER | 11 | 11-21 | points | Standard game winning score |

---

## 12. Export and Partition Parameters

| Parameter Name | Type | Default | Range/Options | Units | Description |
|----------------|------|---------|---------------|-------|-------------|
| `export_format_primary` | ENUM | "parquet" | parquet, csv, json | - | Primary export format |
| `export_partition_strategy` | ENUM | "monthly" | none, monthly, regional, hybrid | - | Parquet partitioning strategy |
| `export_compression_codec` | ENUM | "snappy" | snappy, gzip, zstd, none | - | Compression algorithm |
| `export_included_table_groups` | ARRAY | ["student_core"] | student_core, reference, operational, raw_seed, audit, simulation_truth | - | Named export table groups to include |
| `export_included_tables` | ARRAY | [] | table names | - | Explicit table allow-list; when populated, it overrides table groups |
| `export_batch_on_completion` | BOOLEAN | true | true, false | - | Auto-export after validation |

Exports use explicit allow-lists. Instructor or audit datasets are included only
when their table group or table name is explicitly listed.

---

## 13. Validation Parameters

| Parameter Name | Type | Default | Range/Options | Units | Description |
|----------------|------|---------|---------------|-------|-------------|
| `validation_strictness` | ENUM | "standard" | lenient, standard, strict | - | Validation enforcement level |
| `validation_blocker_threshold` | INTEGER | 0 | 0-1000 | blockers | Max blockers before failure |
| `validation_error_threshold` | INTEGER | 100 | 0-10000 | errors | Max errors before warning |
| `validation_sample_size_distribution` | INTEGER | 10000 | 100-1000000 | rows | Sample size for distribution tests |
| `weekend_concentration_min` | DECIMAL | 0.40 | 0.2-0.8 | probability | Minimum weekend match share |
| `weekend_concentration_max` | DECIMAL | 0.60 | 0.3-0.9 | probability | Maximum weekend match share |

---

## 14. Noise Configuration Matrix

### Noise Level Definitions

| Noise Level | Multiplier Range | Use Case |
|-------------|------------------|----------|
| `none` | 1.0 (fixed) | Deterministic testing |
| `low` | 0.90 - 1.10 | Tournament scheduling, competitive matchmaking |
| `medium` | 0.80 - 1.25 | Recreational matchmaking, team formation |
| `high` | 0.65 - 1.50 | Open play, social dynamics |

### Parameter-Specific Noise Mapping

| Parameter | Noise Type | Units | Low | Medium | High |
|-----------|------------|-------|-----|--------|------|
| `rating_noise_std_dev` | Gaussian | rating_points | 25 | 75 | 125 |
| `competitiveness_noise_std_dev` | Gaussian | multiplier | 0.02 | 0.05 | 0.12 |
| `club_assignment_noise_std_dev` | Uniform | probability_shift | 0.05 | 0.10 | 0.25 |
| `date_allocation_noise_level` | Multiplicative | multiplier_range | [0.90,1.10] | [0.80,1.25] | [0.65,1.50] |

---

## 15. Configuration File Format

### YAML Example

```yaml
simulation:
  master_seed: 42
  simulation_name: "NAPA_Olympic_Analytics_v1"
  simulation_version: "1.0"
  target_total_players: 50000
  historical_batch_count: 12

player_generation:
  monthly_player_growth_rate: 0.02
  player_age_distribution_45_59: 0.32
  dominant_hand_right_probability: 0.88
  dominant_hand_left_probability: 0.10
  dominant_hand_ambidextrous_probability: 0.02
  player_status_active_probability: 0.94
  player_status_injured_probability: 0.02
  player_status_retired_probability: 0.02
  player_status_inactive_probability: 0.02
  initial_skill_seed_mean: 1500.0
  initial_skill_seed_std_dev: 275.0
  initial_skill_seed_lower_bias: 100.0
  initial_skill_seed_min: 500.0
  initial_skill_seed_max: 3500.0
  name_assignment_noise_rate: 0.03
  initial_rating_mean: 1500.0
  initial_rating_std_dev: 200.0
  initial_rating_elite_tail_rate: 0.003
  initial_rating_elite_min: 4000.0
  initial_rating_elite_max: 4500.0

regional:
  competitiveness_multiplier_default: 1.0
  competitiveness_noise_std_dev: 0.05

clubs:
  clubs_per_75k_population: 1.0
  unaffiliated_player_rate: 0.12
  multi_club_membership_rate: 0.06
  min_club_memberships_per_affiliated_player: 1
  max_club_memberships_per_player: 3
  secondary_membership_same_region_rate: 0.85

match_scheduling:
  monthly_matches_per_active_player_mean: 8.0
  weekend_concentration_bias: 1.75
  saturday_weight: 2.25

matchmaking:
  rating_band_width_recreational: 400.0
  matchmaking_noise_factor: 0.20

validation:
  validation_strictness: "standard"
  weekend_concentration_min: 0.40
  weekend_concentration_max: 0.60

export:
  export_format_primary: "parquet"
  export_partition_strategy: "monthly"
  export_compression_codec: "snappy"
  export_included_table_groups:
    - "student_core"
    - "reference"
  export_included_tables: []
  export_batch_on_completion: true
```

### JSON Example

```json
{
  "simulation": {
    "master_seed": 42,
    "simulation_name": "NAPA_Olympic_Analytics_v1",
    "target_total_players": 50000
  },
  "player_generation": {
    "monthly_player_growth_rate": 0.02,
    "dominant_hand_right_probability": 0.88,
    "dominant_hand_left_probability": 0.10,
    "dominant_hand_ambidextrous_probability": 0.02,
    "player_status_active_probability": 0.94,
    "player_status_injured_probability": 0.02,
    "player_status_retired_probability": 0.02,
    "player_status_inactive_probability": 0.02,
    "initial_skill_seed_mean": 1500.0,
    "initial_skill_seed_std_dev": 275.0,
    "initial_skill_seed_lower_bias": 100.0,
    "initial_rating_mean": 1500.0
  },
  "match_scheduling": {
    "weekend_concentration_bias": 1.75
  },
  "export": {
    "export_format_primary": "parquet",
    "export_partition_strategy": "monthly",
    "export_compression_codec": "snappy",
    "export_included_table_groups": ["student_core", "reference"],
    "export_included_tables": [],
    "export_batch_on_completion": true
  }
}
```

---

## 16. Parameter Validation Rules

All configuration parsers must enforce:

1. **Required parameters**: `master_seed`, `simulation_name`, `target_total_players`
2. **Range validation**: All numeric parameters within documented ranges
3. **Probability sum validation**: All distribution groups sum to 1.0 ± 0.01,
   including gender, dominant hand, player status, club size, match type, and
   matchmaking quality distributions.
4. **Consistency checks**: 
   - `rating_min` < `initial_rating_mean` < `rating_max`
   - `player_age_min` < `player_age_max`
   - `confidence_min` < `initial_confidence_score` < `confidence_max`
   - `initial_skill_seed_min` < `initial_skill_seed_mean` < `initial_skill_seed_max`
   - `initial_skill_seed_std_dev` > 0
   - `initial_skill_seed_lower_bias` >= 0
   - `export_included_table_groups` values must be known group names
   - `export_included_tables` values must be known ORM table names
5. **Type validation**: Enums must match exact string values
6. **Mutual exclusivity**: Some parameters are mutually exclusive (documented per parameter)

---

## 17. Configuration Repository Storage

Configuration is stored in the database as versioned profile payloads so a
future web UI can create, edit, validate, and activate configurations without
schema changes for every individual parameter.

- `configuration_profiles` stores named configuration profiles and whether a
  profile is active.
- `configuration_profile_versions` stores immutable versioned JSONB payloads
  in `config_payload`, with a `config_schema_version` and validation status.
- Individual configuration parameters are keys inside `config_payload`, not
  columns on `configuration_profile_versions`.
- `generation_runs.parameter_snapshot` stores the frozen effective
  configuration used by a specific generation run after defaults,
  profile values, environment overrides, UI overrides, and command-line
  arguments are resolved.
- A generation run must never depend on mutable profile state after it starts;
  it must copy the resolved configuration into `parameter_snapshot`.
- The canonical payload shape and grouped sample JSON are defined in
  [Configuration Payload Architecture](../architecture/configuration_payload_architecture.md).

This structure supports profile-level reloads, version history, rollback by
selecting an earlier version, web-based editing, and future schema migrations
inside the JSON payload.

## 18. Configuration Precedence

When loading configuration:

1. **Default values** (documented in this specification)
2. **Configuration profile version** (`configuration_profile_versions.config_payload`)
3. **Configuration file** (YAML/JSON, for development or import/export)
4. **Environment variables** (prefixed with `PBSIM_`)
5. **UI overrides** (submitted through web control panel)
6. **Command-line arguments** (highest precedence)

Example environment variable: `PBSIM_MASTER_SEED=12345`

---

## 19. Deprecated Parameters

### Removed in v1.0

| Old Parameter Name | Replacement | Reason |
|--------------------|-------------|---------|
| `monthly_growth_rate` | `monthly_player_growth_rate` | Naming clarity |
| `weekend_bias` | `weekend_concentration_bias` | Naming consistency |
| `weekend_bias_multiplier` | `weekend_concentration_bias` | Naming consistency |
| `date_noise_level` | `date_allocation_noise_level` | Naming consistency |
| `regional_multiplier` | `competitiveness_multiplier_default` | Naming precision |
| `rating_noise_factor` | `rating_noise_std_dev` | Unit specification |
| `initial_rating_sd` | `initial_rating_std_dev` | Unit specification |
| `initial_confidence` | `initial_confidence_score` | Naming precision |
| `include_instructor_only_tables` | `export_included_table_groups` or `export_included_tables` | Explicit export allow-list |

---

## 20. Future Configuration Extensions

Planned parameters for future versions:

- Injury simulation rates
- Weather impact modifiers
- Court surface type distributions
- Player fatigue modeling
- Travel distance penalties
- Seasonal participation variations
- Tournament bracket structures
- Partnership chemistry evolution rates

---

## 21. Configuration Schema Versioning

This configuration specification is versioned separately from the platform version.

| Schema Version | Platform Versions | Breaking Changes |
|----------------|-------------------|------------------|
| 1.0 | 1.0.x | Initial specification |

Future schema changes will follow semantic versioning:
- **Major**: Breaking changes requiring configuration migration
- **Minor**: New optional parameters
- **Patch**: Documentation clarifications, default adjustments

---

**END OF CONFIGURATION PARAMETERS SPECIFICATION**
