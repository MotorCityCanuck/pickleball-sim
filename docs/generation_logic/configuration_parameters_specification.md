# Configuration Parameters Specification

**Pickleball Simulation Platform - Authoritative Configuration Schema**

**Document Purpose**: This document defines all configurable parameters used throughout the simulation platform, standardizing naming conventions, data types, defaults, and valid ranges.

**Version**: 1.0  
**Last Updated**: 2026-05-20

---

## 1. Configuration Principles

1. **snake_case** naming for all parameters
2. All probabilities are decimal values between 0.0 and 1.0
3. All percentages are expressed as decimals (e.g., 0.02 for 2%)
4. All multipliers are decimal values (typically 0.5 to 2.0 range)
5. All noise parameters include units (e.g., rating_points, probability_shift)
6. All date parameters use ISO 8601 format (YYYY-MM-DD)
7. All configuration must be serializable to YAML/JSON and JSONB

### 1.1 Recommended Edit Control Taxonomy

The web control panel should use the following control vocabulary when
rendering configuration fields:

- `Text input`: short free-form strings such as names and versions
- `Numeric input`: integer or decimal values where precise entry matters
- `Date picker`: ISO date values
- `Checkbox`: binary true/false values
- `Select`: enumerated options
- `Slider`: bounded probability-style values where drag interaction is useful
- `Weight table row`: one row inside a grouped probability or weight editor
- `Range table row`: one row inside a grouped min/max range editor
- `Multi-select`: list-based selection from known options
- `Read-only computed`: derived values shown but not directly edited
- `Advanced JSON editor`: structured object values that should remain in an advanced editor until a richer purpose-built control exists

---

## 2. Global Simulation Parameters

| Parameter Name | Type | Recommended Edit Control | Default | Range/Options | Units | Description |
|----------------|------|--------------------------|---------|---------------|-------|-------------|
| `master_seed` | INTEGER | Numeric input | (required) | > 0 | - | Master random seed for reproducibility. Required positive integer greater than 0. |
| `simulation_version` | STRING | Text input | "1.0" | semantic version | - | Platform version identifier. Enter a semantic version string such as `1.0` or `1.2.3`. |
| `simulation_name` | STRING | Text input | (required) | max 255 chars | - | Human-readable simulation name. Required text value up to 255 characters. |
| `target_total_players` | INTEGER | Numeric input | 50000 | 1000-10000000 | players | Total player population target. Allowed range is 1,000 to 10,000,000 players. |
| `historical_batch_count` | INTEGER | Numeric input | 12 | 1-36 | months | Number of historical months to generate. Allowed range is 1 to 36 months. |
| `first_batch_month` | DATE | Date picker | 2024-01-01 | ISO date | date | First monthly batch date for the simulation timeline. Must be entered as an ISO date in `YYYY-MM-DD` format. |
| `generation_run_mode` | ENUM | Select | "full" | full, historical_only, incremental | - | Execution mode. Allowed options are `full`, `historical_only`, or `incremental`. |

---

## 3. Player Generation Parameters

| Parameter Name | Type | Recommended Edit Control | Default | Range/Options | Units | Description |
|----------------|------|--------------------------|---------|---------------|-------|-------------|
| `monthly_player_growth_rate` | DECIMAL | Slider | 0.02 | 0.0-0.10 | decimal | Monthly new player growth. Allowed range is 0.0 to 0.10, representing 0% to 10% monthly growth. |
| `player_count` | INTEGER | Numeric input | 50000 | 1000-10000000 | players | Player generator target when no explicit override is supplied. Allowed range is 1,000 to 10,000,000 players. |
| `initial_player_count` | INTEGER | Read-only computed | (calculated) | - | players | Starting player population. This is a calculated read-only value derived from the growth assumptions. |
| `player_gender_distribution_male` | DECIMAL | Weight table row | 0.50 | 0.0-1.0 | probability | Probability of male player. Enter a probability between 0.0 and 1.0; gender distribution weights must sum to 1.0 with the female value. |
| `player_gender_distribution_female` | DECIMAL | Weight table row | 0.50 | 0.0-1.0 | probability | Probability of female player. Enter a probability between 0.0 and 1.0; gender distribution weights must sum to 1.0 with the male value. |
| `player_age_min` | INTEGER | Numeric input | 18 | 18-100 | years | Minimum player age. Allowed range is 18 to 100 years. |
| `player_age_max` | INTEGER | Numeric input | 85 | 18-100 | years | Maximum player age. Allowed range is 18 to 100 years and must remain greater than `player_age_min`. |
| `player_age_distribution_18_29` | DECIMAL | Weight table row | 0.08 | 0.0-1.0 | probability | Age cohort 18-29 weight. Enter a probability between 0.0 and 1.0; all age cohort weights must sum to 1.0. |
| `player_age_distribution_30_44` | DECIMAL | Weight table row | 0.18 | 0.0-1.0 | probability | Age cohort 30-44 weight. Enter a probability between 0.0 and 1.0; all age cohort weights must sum to 1.0. |
| `player_age_distribution_45_59` | DECIMAL | Weight table row | 0.32 | 0.0-1.0 | probability | Age cohort 45-59 weight. Enter a probability between 0.0 and 1.0; all age cohort weights must sum to 1.0. |
| `player_age_distribution_60_74` | DECIMAL | Weight table row | 0.34 | 0.0-1.0 | probability | Age cohort 60-74 weight. Enter a probability between 0.0 and 1.0; all age cohort weights must sum to 1.0. |
| `player_age_distribution_75_plus` | DECIMAL | Weight table row | 0.08 | 0.0-1.0 | probability | Age cohort 75+ weight. Enter a probability between 0.0 and 1.0; all age cohort weights must sum to 1.0. |
| `dominant_hand_right_probability` | DECIMAL | Weight table row | 0.88 | 0.5-1.0 | probability | Right-handed player probability. Allowed range is 0.5 to 1.0; dominant-hand probabilities should sum to 1.0 across all hand values. |
| `dominant_hand_left_probability` | DECIMAL | Weight table row | 0.10 | 0.0-0.5 | probability | Left-handed player probability. Allowed range is 0.0 to 0.5; dominant-hand probabilities should sum to 1.0 across all hand values. |
| `dominant_hand_ambidextrous_probability` | DECIMAL | Weight table row | 0.02 | 0.0-0.1 | probability | Ambidextrous player probability. Allowed range is 0.0 to 0.1; dominant-hand probabilities should sum to 1.0 across all hand values. |
| `player_status_active_probability` | DECIMAL | Weight table row | 0.94 | 0.0-1.0 | probability | Initial active player status probability. Enter a probability between 0.0 and 1.0; all player-status probabilities must sum to 1.0. |
| `player_status_injured_probability` | DECIMAL | Weight table row | 0.02 | 0.0-0.2 | probability | Initial injured player status probability. Allowed range is 0.0 to 0.2; all player-status probabilities must sum to 1.0. |
| `player_status_retired_probability` | DECIMAL | Weight table row | 0.02 | 0.0-0.2 | probability | Initial retired player status probability. Allowed range is 0.0 to 0.2; all player-status probabilities must sum to 1.0. |
| `player_status_inactive_probability` | DECIMAL | Weight table row | 0.02 | 0.0-0.2 | probability | Initial inactive player status probability. Allowed range is 0.0 to 0.2; all player-status probabilities must sum to 1.0. |
| `initial_skill_seed_mean` | DECIMAL | Numeric input | 1500.0 | 500-3500 | skill_points | Mean initial hidden skill seed. Allowed range is 500 to 3,500 skill points. |
| `initial_skill_seed_std_dev` | DECIMAL | Numeric input | 275.0 | 25-1000 | skill_points | Standard deviation for initial hidden skill seed. Allowed range is 25 to 1,000 skill points and must be greater than 0. |
| `initial_skill_seed_lower_bias` | DECIMAL | Numeric input | 100.0 | 0-500 | skill_points | Downward bias applied after sampling to modestly favor lower initial skill. Allowed range is 0 to 500 skill points. |
| `initial_skill_seed_min` | DECIMAL | Numeric input | 500.0 | 0-3500 | skill_points | Minimum initial hidden skill seed. Allowed range is 0 to 3,500 skill points and must stay below the mean and max values. |
| `initial_skill_seed_max` | DECIMAL | Numeric input | 3500.0 | 500-5000 | skill_points | Maximum initial hidden skill seed. Allowed range is 500 to 5,000 skill points and must stay above the mean and min values. |
| `name_assignment_noise_rate` | DECIMAL | Slider | 0.03 | 0.0-0.10 | probability | Small probability of intentionally imperfect regional name selection. Allowed range is 0.0 to 0.10. |

---

## 4. Rating and Assessment Parameters

| Parameter Name | Type | Recommended Edit Control | Default | Range/Options | Units | Description |
|----------------|------|--------------------------|---------|---------------|-------|-------------|
| `initial_rating_mean` | DECIMAL | Numeric input | 1500.0 | 1000-2500 | rating_points | Mean initial player rating. Allowed range is 1,000 to 2,500 rating points. |
| `initial_rating_std_dev` | DECIMAL | Numeric input | 200.0 | 50-500 | rating_points | Standard deviation of initial rating. Allowed range is 50 to 500 rating points. |
| `rating_min` | DECIMAL | Numeric input | 0.0 | 0 | rating_points | Minimum allowed rating. Value must be 0 or greater and remain below `initial_rating_mean` and `rating_max`. |
| `rating_max` | DECIMAL | Numeric input | 5000.0 | 3000-10000 | rating_points | Maximum allowed rating. Allowed range is 3,000 to 10,000 rating points and must remain above `initial_rating_mean`. |
| `initial_rating_elite_tail_rate` | DECIMAL | Slider | 0.003 | 0.0-0.02 | probability | Small share of initial players sampled from the elite rating tail. Allowed range is 0.0 to 0.02. |
| `initial_rating_elite_min` | DECIMAL | Numeric input | 4000.0 | 3000-5000 | rating_points | Lower bound for elite-tail initial ratings. Allowed range is 3,000 to 5,000 rating points. |
| `initial_rating_elite_max` | DECIMAL | Numeric input | 4500.0 | 3000-5000 | rating_points | Upper bound for elite-tail initial ratings. Allowed range is 3,000 to 5,000 rating points and must remain above `initial_rating_elite_min`. |
| `initial_confidence_score` | DECIMAL | Slider | 0.10 | 0.0-1.0 | probability | Starting confidence for new players. Allowed range is 0.0 to 1.0 and should remain between `confidence_min` and `confidence_max`. |
| `confidence_min` | DECIMAL | Numeric input | 0.0 | 0.0-1.0 | probability | Minimum confidence score. Allowed range is 0.0 to 1.0. |
| `confidence_max` | DECIMAL | Numeric input | 1.0 | 0.0-1.0 | probability | Maximum confidence score. Allowed range is 0.0 to 1.0 and must remain above `confidence_min`. |
| `k_factor_new_player` | DECIMAL | Numeric input | 48.0 | 16-64 | rating_change_multiplier | K-factor for new players (<10 matches). Allowed range is 16 to 64. |
| `k_factor_established` | DECIMAL | Numeric input | 24.0 | 16-64 | rating_change_multiplier | K-factor for established players. Allowed range is 16 to 64. |
| `k_factor_elite` | DECIMAL | Numeric input | 16.0 | 8-32 | rating_change_multiplier | K-factor for elite stable players. Allowed range is 8 to 32. |
| `rating_noise_std_dev` | DECIMAL | Numeric input | 75.0 | 0-200 | rating_points | Match performance noise standard deviation. Allowed range is 0 to 200 rating points. |
| `confidence_recency_half_life_days` | DECIMAL | Numeric input | 90.0 | 30-365 | days | Confidence decay half-life. Allowed range is 30 to 365 days. |

---

## 5. Regional Distribution Parameters

| Parameter Name | Type | Recommended Edit Control | Default | Range/Options | Units | Description |
|----------------|------|--------------------------|---------|---------------|-------|-------------|
| `region_population_weight` | DECIMAL | Numeric input | 1.0 | 0.1-2.0 | multiplier | Regional population scaling factor. Allowed range is 0.1 to 2.0. |
| `competitiveness_multiplier_default` | DECIMAL | Numeric input | 1.0 | 0.5-2.0 | multiplier | Default regional competitiveness. Allowed range is 0.5 to 2.0. |
| `competitiveness_noise_std_dev` | DECIMAL | Slider | 0.05 | 0.0-0.25 | multiplier | Noise added to regional competitiveness. Allowed range is 0.0 to 0.25. |
| `min_players_per_region` | INTEGER | Numeric input | 100 | 10-1000 | players | Minimum regional player allocation. Allowed range is 10 to 1,000 players. |

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

| Parameter Name | Type | Recommended Edit Control | Default | Range/Options | Units | Description |
|----------------|------|--------------------------|---------|---------------|-------|-------------|
| `clubs_per_75k_population` | DECIMAL | Numeric input | 1.0 | 0.5-3.0 | clubs/population | Club density ratio. Allowed range is 0.5 to 3.0 clubs per 75,000 population. |
| `club_size_distribution_small` | DECIMAL | Weight table row | 0.35 | 0.0-1.0 | probability | Small clubs (10-30 members). Enter a probability between 0.0 and 1.0; all club-size distribution weights must sum to 1.0. |
| `club_size_distribution_medium` | DECIMAL | Weight table row | 0.40 | 0.0-1.0 | probability | Medium clubs (31-75 members). Enter a probability between 0.0 and 1.0; all club-size distribution weights must sum to 1.0. |
| `club_size_distribution_large` | DECIMAL | Weight table row | 0.20 | 0.0-1.0 | probability | Large clubs (76-200 members). Enter a probability between 0.0 and 1.0; all club-size distribution weights must sum to 1.0. |
| `club_size_distribution_very_large` | DECIMAL | Weight table row | 0.04 | 0.0-1.0 | probability | Very large clubs (201-500 members). Enter a probability between 0.0 and 1.0; all club-size distribution weights must sum to 1.0. |
| `club_size_distribution_mega` | DECIMAL | Weight table row | 0.01 | 0.0-1.0 | probability | Mega clubs (500+ members). Enter a probability between 0.0 and 1.0; all club-size distribution weights must sum to 1.0. |
| `club_assignment_noise_std_dev` | DECIMAL | Slider | 0.10 | 0.0-0.5 | probability_shift | Club assignment randomness. Allowed range is 0.0 to 0.5 probability shift. |
| `unaffiliated_player_rate` | DECIMAL | Slider | 0.12 | 0.0-0.30 | probability | Players without primary club. Allowed range is 0.0 to 0.30. |
| `multi_club_membership_rate` | DECIMAL | Slider | 0.06 | 0.0-0.20 | probability | Affiliated players with secondary club memberships. Allowed range is 0.0 to 0.20. |
| `min_club_memberships_per_affiliated_player` | INTEGER | Numeric input | 1 | 1-3 | memberships | Minimum club memberships for affiliated players. Allowed range is 1 to 3 memberships. |
| `max_club_memberships_per_player` | INTEGER | Numeric input | 3 | 1-5 | memberships | Maximum active club memberships for any player. Allowed range is 1 to 5 memberships. |
| `secondary_membership_same_region_rate` | DECIMAL | Slider | 0.85 | 0.0-1.0 | probability | Share of secondary club memberships constrained to the player's primary region. Allowed range is 0.0 to 1.0. |

---

## 7. Team Formation Parameters

| Parameter Name | Type | Recommended Edit Control | Default | Range/Options | Units | Description |
|----------------|------|--------------------------|---------|---------------|-------|-------------|
| `target_team_count` | INTEGER/null | Numeric input | null | null or >0 | teams | Optional explicit team count target. Leave null to derive demand automatically, or enter a positive integer team count. |
| `player_team_participation_rate` | DECIMAL | Slider | 0.70 | 0.0-1.0 | probability | Share of eligible players assigned to at least one active team in a batch. Allowed range is 0.0 to 1.0. |
| `multi_team_player_rate` | DECIMAL | Slider | 0.08 | 0.0-0.30 | probability | Share of team-participating players allowed on multiple active teams. Allowed range is 0.0 to 0.30. |
| `max_active_teams_per_player` | INTEGER | Numeric input | 2 | 1-5 | teams | Maximum active teams per player when multiple active teams are allowed. Allowed range is 1 to 5 teams. |
| `same_club_team_rate` | DECIMAL | Slider | 0.78 | 0.0-1.0 | probability | Share of new teams whose partners should share a club when feasible. Allowed range is 0.0 to 1.0. |
| `same_region_team_rate` | DECIMAL | Slider | 0.95 | 0.0-1.0 | probability | Share of new teams whose partners should share a region when feasible. Allowed range is 0.0 to 1.0. |
| `rating_gap_mean` | DECIMAL | Numeric input | 175.0 | 0-1000 | rating_points | Target average rating gap between team partners. Allowed range is 0 to 1,000 rating points. |
| `rating_gap_std_dev` | DECIMAL | Numeric input | 125.0 | 0-1000 | rating_points | Variation in acceptable rating gap during partner selection. Allowed range is 0 to 1,000 rating points. |
| `rating_gap_max` | DECIMAL | Numeric input | 1500.0 | 0-2500 | rating_points | Maximum allowed rating gap between partners for newly formed teams, especially open-play teams. Allowed range is 0 to 2,500 rating points. |
| `team_type_weights` | OBJECT | Weight table row | see defaults | probabilities sum to 1 | probability | Distribution across mens, womens, mixed, and open doubles teams. Team-type weights must sum to 1.0 across all options. |
| `team_persistence_probability_recreational` | DECIMAL | Slider | 0.72 | 0.3-0.95 | probability | Recreational team retention rate. Allowed range is 0.3 to 0.95. |
| `team_persistence_probability_competitive` | DECIMAL | Slider | 0.88 | 0.5-0.98 | probability | Competitive team retention rate. Allowed range is 0.5 to 0.98. |
| `dormant_team_reactivation_rate` | DECIMAL | Slider | 0.04 | 0.0-0.30 | probability | Monthly chance that an eligible dormant partnership reforms. Allowed range is 0.0 to 0.30. |
| `retired_team_rate_on_dissolution` | DECIMAL | Slider | 0.10 | 0.0-1.0 | probability | Share of dissolved teams marked retired instead of dormant. Allowed range is 0.0 to 1.0. |
| `team_chemistry_weight` | DECIMAL | Weight table row | 0.35 | 0.0-1.0 | weight | Weight of chemistry in team formation. Enter a weight between 0.0 and 1.0 within the grouped partner-scoring weights. |
| `team_skill_balance_weight` | DECIMAL | Weight table row | 0.25 | 0.0-1.0 | weight | Weight of rating balance. Enter a weight between 0.0 and 1.0 within the grouped partner-scoring weights. |
| `team_club_proximity_weight` | DECIMAL | Weight table row | 0.25 | 0.0-1.0 | weight | Weight of shared-club proximity in partner scoring. Enter a weight between 0.0 and 1.0 within the grouped partner-scoring weights. |
| `team_region_proximity_weight` | DECIMAL | Weight table row | 0.10 | 0.0-1.0 | weight | Weight of regional proximity in partner scoring. Enter a weight between 0.0 and 1.0 within the grouped partner-scoring weights. |
| `team_prior_partnership_weight` | DECIMAL | Weight table row | 0.20 | 0.0-1.0 | weight | Weight of prior partnership history in partner scoring. Enter a weight between 0.0 and 1.0 within the grouped partner-scoring weights. |
| `team_noise_factor` | DECIMAL | Slider | 0.15 | 0.0-0.5 | probability_shift | Random variation in team formation. Allowed range is 0.0 to 0.5 probability shift. |
| `monthly_team_dissolution_rate` | DECIMAL | Slider | 0.10 | 0.0-0.5 | probability | Monthly probability that an active team dissolves or becomes dormant. Allowed range is 0.0 to 0.5. |
| `allow_multiple_active_teams_per_scope` | BOOLEAN | Checkbox | false | true/false | flag | Whether a player can be active on multiple teams in the same scheduling scope. Allowed values are `true` or `false`. |

---

## 8. Match Scheduling Parameters

| Parameter Name | Type | Recommended Edit Control | Default | Range/Options | Units | Description |
|----------------|------|--------------------------|---------|---------------|-------|-------------|
| `monthly_matches_per_active_player_mean` | DECIMAL | Numeric input | 8.0 | 1.0-30.0 | matches | Average matches per player per month. Allowed range is 1.0 to 30.0 matches. |
| `monthly_matches_per_active_player_std_dev` | DECIMAL | Numeric input | 4.0 | 1.0-15.0 | matches | Standard deviation of match frequency. Allowed range is 1.0 to 15.0 matches. |
| `matches_per_team_per_month` | DECIMAL | Numeric input | 4.0 | 0.1-30.0 | matches | Main match volume driver currently used by the match generator. Allowed range is 0.1 to 30.0 matches per team per month. |
| `weekend_concentration_bias` | DECIMAL | Numeric input | 1.75 | 1.0-3.0 | multiplier | Weekend date probability multiplier. Allowed range is 1.0 to 3.0. |
| `saturday_weight` | DECIMAL | Numeric input | 2.25 | 1.0-4.0 | weight | Saturday match concentration. Allowed range is 1.0 to 4.0. |
| `sunday_weight` | DECIMAL | Numeric input | 1.85 | 1.0-4.0 | weight | Sunday match concentration. Allowed range is 1.0 to 4.0. |
| `friday_weight` | DECIMAL | Numeric input | 1.20 | 0.5-2.0 | weight | Friday match concentration. Allowed range is 0.5 to 2.0. |
| `weekday_evening_weight` | DECIMAL | Numeric input | 1.00 | 0.3-1.5 | weight | Monday-Thursday weight. Allowed range is 0.3 to 1.5. |
| `league_weekday_multiplier` | DECIMAL | Numeric input | 1.40 | 1.0-2.5 | multiplier | League play weekday boost. Allowed range is 1.0 to 2.5. |
| `tournament_weekend_multiplier` | DECIMAL | Numeric input | 2.50 | 1.5-4.0 | multiplier | Tournament weekend concentration. Allowed range is 1.5 to 4.0. |
| `max_daily_match_share` | DECIMAL | Slider | 0.08 | 0.03-0.15 | probability | Maximum matches on single day. Allowed range is 0.03 to 0.15 of the month’s scheduled matches. |
| `max_daily_matches_per_team` | INTEGER | Numeric input | 2 | 1-10 | matches | Maximum matches a team can be scheduled for on one date. Allowed range is 1 to 10 matches. |
| `date_allocation_noise_level` | ENUM | Select | "medium" | low, medium, high | - | Day-of-month allocation noise. Allowed options are `low`, `medium`, or `high`. |

---

## 9. Match Type Distribution Parameters

| Parameter Name | Type | Recommended Edit Control | Default | Range/Options | Units | Description |
|----------------|------|--------------------------|---------|---------------|-------|-------------|
| `match_type_recreational` | DECIMAL | Weight table row | 0.55 | 0.0-1.0 | probability | Recreational/open play matches. Enter a probability between 0.0 and 1.0; all match-type probabilities must sum to 1.0. |
| `match_type_league` | DECIMAL | Weight table row | 0.20 | 0.0-1.0 | probability | League matches. Enter a probability between 0.0 and 1.0; all match-type probabilities must sum to 1.0. |
| `match_type_ladder` | DECIMAL | Weight table row | 0.10 | 0.0-1.0 | probability | Ladder matches. Enter a probability between 0.0 and 1.0; all match-type probabilities must sum to 1.0. |
| `match_type_tournament` | DECIMAL | Weight table row | 0.10 | 0.0-1.0 | probability | Tournament matches. Enter a probability between 0.0 and 1.0; all match-type probabilities must sum to 1.0. |
| `match_type_challenge` | DECIMAL | Weight table row | 0.04 | 0.0-1.0 | probability | Challenge matches. Enter a probability between 0.0 and 1.0; all match-type probabilities must sum to 1.0. |
| `match_type_clinic` | DECIMAL | Weight table row | 0.01 | 0.0-1.0 | probability | Clinic/event matches. Enter a probability between 0.0 and 1.0; all match-type probabilities must sum to 1.0. |

---

## 10. Matchmaking Parameters

| Parameter Name | Type | Recommended Edit Control | Default | Range/Options | Units | Description |
|----------------|------|--------------------------|---------|---------------|-------|-------------|
| `rating_band_width_recreational` | DECIMAL | Numeric input | 400.0 | 100-1000 | rating_points | Rating tolerance for recreational. Allowed range is 100 to 1,000 rating points. |
| `rating_band_width_competitive` | DECIMAL | Numeric input | 150.0 | 50-400 | rating_points | Rating tolerance for competitive. Allowed range is 50 to 400 rating points. |
| `rating_band_width_tournament` | DECIMAL | Numeric input | 100.0 | 25-250 | rating_points | Rating tolerance for tournaments. Allowed range is 25 to 250 rating points. |
| `matchmaking_noise_factor` | DECIMAL | Slider | 0.20 | 0.0-0.5 | probability_shift | Randomness in opponent selection. Allowed range is 0.0 to 0.5 probability shift. |
| `rematch_penalty_window_days` | INTEGER | Numeric input | 30 | 7-90 | days | Repeat opponent penalty window. Allowed range is 7 to 90 days. |
| `locality_weight` | DECIMAL | Weight table row | 0.30 | 0.0-1.0 | weight | Geographic proximity weight. Enter a weight between 0.0 and 1.0 within the grouped matchmaking weights. |
| `ideal_matchup_probability` | DECIMAL | Weight table row | 0.65 | 0.3-0.9 | probability | Well-balanced match target rate. Allowed range is 0.3 to 0.9; matchup-quality probabilities must sum to 1.0. |
| `slight_mismatch_probability` | DECIMAL | Weight table row | 0.25 | 0.1-0.5 | probability | Moderate mismatch rate. Allowed range is 0.1 to 0.5; matchup-quality probabilities must sum to 1.0. |
| `significant_mismatch_probability` | DECIMAL | Weight table row | 0.08 | 0.0-0.3 | probability | Large mismatch rate. Allowed range is 0.0 to 0.3; matchup-quality probabilities must sum to 1.0. |
| `chaos_matchup_probability` | DECIMAL | Weight table row | 0.02 | 0.0-0.1 | probability | Random pairing rate. Allowed range is 0.0 to 0.1; matchup-quality probabilities must sum to 1.0. |

---

## 11. Game and Score Generation Parameters

| Parameter Name | Type | Recommended Edit Control | Default | Range/Options | Units | Description |
|----------------|------|--------------------------|---------|---------------|-------|-------------|
| `games_per_match_recreational` | INTEGER | Numeric input | 1 | 1-5 | games | Games for recreational matches. Allowed range is 1 to 5 games. |
| `games_per_match_league` | INTEGER | Numeric input | 2 | 1-5 | games | Games for league matches. Allowed range is 1 to 5 games. |
| `games_per_match_tournament` | INTEGER | Numeric input | 3 | 1-5 | games | Games for tournament matches (best-of-3). Allowed range is 1 to 5 games. |
| `score_noise_std_dev` | DECIMAL | Numeric input | 1.5 | 0.0-5.0 | points | Score outcome randomness. Allowed range is 0.0 to 5.0 points. |
| `upset_probability_boost` | DECIMAL | Slider | 0.15 | 0.0-0.4 | probability_shift | Underdog win probability boost. Allowed range is 0.0 to 0.4 probability shift. |
| `win_by_two_rule_enabled` | BOOLEAN | Checkbox | true | true, false | - | Enforce win-by-two rule. Allowed values are `true` or `false`. |
| `win_by_two_extension_rate` | DECIMAL | Slider | 0.10 | 0.0-1.0 | probability | Likelihood that a generated game reaches a win-by-two extension beyond the target score. Allowed range is 0.0 to 1.0. |
| `game_target_score` | INTEGER | Numeric input | 11 | 11-21 | points | Standard game winning score. Allowed range is 11 to 21 points. |

---

## 12. Export and Partition Parameters

| Parameter Name | Type | Recommended Edit Control | Default | Range/Options | Units | Description |
|----------------|------|--------------------------|---------|---------------|-------|-------------|
| `export_format_primary` | ENUM | Select | "parquet" | parquet, csv, json | - | Primary export format. Allowed options are `parquet`, `csv`, or `json`. |
| `export_partition_strategy` | ENUM | Select | "monthly" | none, monthly, regional, hybrid | - | Parquet partitioning strategy. Allowed options are `none`, `monthly`, `regional`, or `hybrid`. |
| `export_compression_codec` | ENUM | Select | "snappy" | snappy, gzip, zstd, none | - | Compression algorithm. Allowed options are `snappy`, `gzip`, `zstd`, or `none`. |
| `export_included_table_groups` | ARRAY | Multi-select | ["student_core"] | student_core, reference, operational, raw_seed, audit, simulation_truth | - | Named export table groups to include. Choose zero or more known group names from `student_core`, `reference`, `operational`, `raw_seed`, `audit`, or `simulation_truth`. |
| `export_included_tables` | ARRAY | Multi-select | [] | table names | - | Explicit table allow-list; when populated, it overrides table groups. Choose zero or more known ORM table names. |
| `export_batch_on_completion` | BOOLEAN | Checkbox | true | true, false | - | Auto-export after validation. Allowed values are `true` or `false`. |

Exports use explicit allow-lists. Instructor or audit datasets are included only
when their table group or table name is explicitly listed.

---

## 13. Validation Parameters

| Parameter Name | Type | Recommended Edit Control | Default | Range/Options | Units | Description |
|----------------|------|--------------------------|---------|---------------|-------|-------------|
| `validation_strictness` | ENUM | Select | "standard" | lenient, standard, strict | - | Validation enforcement level. Allowed options are `lenient`, `standard`, or `strict`. |
| `validation_blocker_threshold` | INTEGER | Numeric input | 0 | 0-1000 | blockers | Max blockers before failure. Allowed range is 0 to 1,000 blockers. |
| `validation_error_threshold` | INTEGER | Numeric input | 100 | 0-10000 | errors | Max errors before warning. Allowed range is 0 to 10,000 errors. |
| `validation_sample_size_distribution` | INTEGER | Numeric input | 10000 | 100-1000000 | rows | Sample size for distribution tests. Allowed range is 100 to 1,000,000 rows. |
| `weekend_concentration_min` | DECIMAL | Numeric input | 0.40 | 0.2-0.8 | probability | Minimum weekend match share. Allowed range is 0.2 to 0.8 probability. |
| `weekend_concentration_max` | DECIMAL | Numeric input | 0.60 | 0.3-0.9 | probability | Maximum weekend match share. Allowed range is 0.3 to 0.9 probability and must remain above `weekend_concentration_min`. |

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
  first_batch_month: "2024-01-01"

player_generation:
  player_count: 50000
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

club_generation:
  clubs_per_75k_population: 1.0
  unaffiliated_player_rate: 0.12
  multi_club_membership_rate: 0.06
  min_club_memberships_per_affiliated_player: 1
  max_club_memberships_per_player: 3
  secondary_membership_same_region_rate: 0.85

match_scheduling:
  matches_per_team_per_month: 4.0
  monthly_matches_per_active_player_mean: 8.0
  weekend_concentration_bias: 1.75
  saturday_weight: 2.25
  max_daily_matches_per_team: 2

games_and_scores:
  games_per_match:
    recreational: 1
    league: 2
    tournament: 3
  game_target_score: 11
  win_by_two_rule_enabled: true
  win_by_two_extension_rate: 0.10

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
    "target_total_players": 50000,
    "first_batch_month": "2024-01-01"
  },
  "player_generation": {
    "player_count": 50000,
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
    "matches_per_team_per_month": 4.0,
    "weekend_concentration_bias": 1.75,
    "max_daily_matches_per_team": 2
  },
  "games_and_scores": {
    "game_target_score": 11,
    "win_by_two_rule_enabled": true,
    "win_by_two_extension_rate": 0.10
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
web UI can create, edit, validate, and activate configurations without
schema changes for every individual parameter.

- `configuration_profiles` stores named configuration profiles and whether a
  profile is active.
- `configuration_profile_versions` stores immutable versioned JSONB payloads
  in `config_payload`, with a `config_schema_version`, payload hash, version
  title, lifecycle status, and lifecycle timestamps.
- Individual configuration parameters are keys inside `config_payload`, not
  columns on `configuration_profile_versions`.
- `generation_runs.parameter_snapshot` stores the frozen effective
  configuration used by a specific generation run after defaults and profile
  values are resolved.
- A generation run must never depend on mutable profile state after it starts;
  it must copy the resolved configuration into `parameter_snapshot`.
- The canonical payload shape and grouped sample JSON are defined in
  [Configuration Payload Architecture](../architecture/configuration_payload_architecture.md).

This structure supports profile-level reloads, version history, web-based
editing, and future schema migrations inside the JSON payload.

For the first web-control-panel implementation:

- Exactly one configuration profile version should have lifecycle status
  `valid`.
- Saving a new valid version should automatically mark the prior valid version
  as `deprecated` in the same transaction.
- Deprecated versions are retained for audit/history but hidden from the normal
  UI and not eligible for generation.
- Validation failure should not create a saved database version.
- The configuration payload must be parsed and validated by typed backend
  configuration models before it can be saved as valid.
- Arbitrary unvalidated JSON must not become the source of truth for generation.

Recommended structured fields for `configuration_profile_versions`:

```text
id
profile_id
version_number
title
notes
lifecycle_status
created_at
created_by
last_used_at
deprecated_at
config_schema_version
config_hash
config_payload
```

## 18. Configuration Precedence

When loading configuration:

1. **Default values** (documented in this specification)
2. **Configuration profile version** (`configuration_profile_versions.config_payload`)
3. **Configuration file** (YAML/JSON, for development or import/export only)
4. **Environment variables** (prefixed with `PBSIM_`, for development or
   deployment wiring only)

Example environment variable: `PBSIM_MASTER_SEED=12345`

The web control panel should not support one-off runtime overrides for
generation settings. If seed, first generated month, generated month count,
player scale, or another runtime setting needs to change, the operator must save
a new valid configuration version.

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
