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
| `target_total_players` | INTEGER | 250000 | 1000-10000000 | players | Total player population target |
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
| `dominant_hand_right_probability` | DECIMAL | 0.90 | 0.5-1.0 | probability | Right-handed player probability |

---

## 4. Rating and Assessment Parameters

| Parameter Name | Type | Default | Range/Options | Units | Description |
|----------------|------|---------|---------------|-------|-------------|
| `initial_rating_mean` | DECIMAL | 1500.0 | 1000-2500 | rating_points | Mean initial player rating |
| `initial_rating_std_dev` | DECIMAL | 200.0 | 50-500 | rating_points | Standard deviation of initial rating |
| `rating_min` | DECIMAL | 0.0 | 0 | rating_points | Minimum allowed rating |
| `rating_max` | DECIMAL | 5000.0 | 3000-10000 | rating_points | Maximum allowed rating |
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

---

## 7. Team Formation Parameters

| Parameter Name | Type | Default | Range/Options | Units | Description |
|----------------|------|---------|---------------|-------|-------------|
| `team_persistence_probability_recreational` | DECIMAL | 0.72 | 0.3-0.95 | probability | Recreational team retention rate |
| `team_persistence_probability_competitive` | DECIMAL | 0.88 | 0.5-0.98 | probability | Competitive team retention rate |
| `team_chemistry_weight` | DECIMAL | 0.35 | 0.0-1.0 | weight | Weight of chemistry in team formation |
| `team_skill_balance_weight` | DECIMAL | 0.25 | 0.0-1.0 | weight | Weight of rating balance |
| `team_noise_factor` | DECIMAL | 0.15 | 0.0-0.5 | probability_shift | Random variation in team formation |

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
| `include_instructor_only_tables` | BOOLEAN | false | true, false | - | Export hidden truth tables |
| `export_batch_on_completion` | BOOLEAN | true | true, false | - | Auto-export after validation |

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
  target_total_players: 250000
  historical_batch_count: 12

player_generation:
  monthly_player_growth_rate: 0.02
  player_age_distribution_45_59: 0.32
  initial_rating_mean: 1500.0
  initial_rating_std_dev: 200.0

regional:
  competitiveness_multiplier_default: 1.0
  competitiveness_noise_std_dev: 0.05

clubs:
  clubs_per_75k_population: 1.0
  unaffiliated_player_rate: 0.12

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
```

### JSON Example

```json
{
  "simulation": {
    "master_seed": 42,
    "simulation_name": "NAPA_Olympic_Analytics_v1",
    "target_total_players": 250000
  },
  "player_generation": {
    "monthly_player_growth_rate": 0.02,
    "initial_rating_mean": 1500.0
  },
  "match_scheduling": {
    "weekend_concentration_bias": 1.75
  }
}
```

---

## 16. Parameter Validation Rules

All configuration parsers must enforce:

1. **Required parameters**: `master_seed`, `simulation_name`, `target_total_players`
2. **Range validation**: All numeric parameters within documented ranges
3. **Probability sum validation**: All distribution parameters sum to 1.0 ± 0.01
4. **Consistency checks**: 
   - `rating_min` < `initial_rating_mean` < `rating_max`
   - `player_age_min` < `player_age_max`
   - `confidence_min` < `initial_confidence_score` < `confidence_max`
5. **Type validation**: Enums must match exact string values
6. **Mutual exclusivity**: Some parameters are mutually exclusive (documented per parameter)

---

## 17. Configuration Precedence

When loading configuration:

1. **Default values** (documented in this specification)
2. **Configuration file** (YAML/JSON)
3. **Environment variables** (prefixed with `PBSIM_`)
4. **UI overrides** (submitted through web control panel)
5. **Command-line arguments** (highest precedence)

Example environment variable: `PBSIM_MASTER_SEED=12345`

---

## 18. Deprecated Parameters

### Removed in v1.0

| Old Parameter Name | Replacement | Reason |
|--------------------|-------------|---------|
| `monthly_growth_rate` | `monthly_player_growth_rate` | Naming clarity |
| `weekend_bias` | `weekend_concentration_bias` | Naming consistency |
| `regional_multiplier` | `competitiveness_multiplier_default` | Naming precision |
| `rating_noise_factor` | `rating_noise_std_dev` | Unit specification |

---

## 19. Future Configuration Extensions

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

## 20. Configuration Schema Versioning

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
