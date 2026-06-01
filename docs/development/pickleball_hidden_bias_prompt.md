# Pickleball Simulation Hidden Performance Bias Enhancement Prompt

Modify the pickleball simulation winner-generation logic to add configurable hidden performance bias factors while preserving the existing two-step architecture.

## Current architecture

1. `matches.py` computes team average ratings and converts them to Elo-style expected win probability.
2. `games.py` uses that expected probability, adds bounded upset noise, simulates each game, generates legal scorelines, and derives the match winner from games won.

## Current behavior

- Team ratings are converted into an Elo-style probability:

```python
probability = 1 / (1 + 10 ** ((rating_two - rating_one) / 400))
```

- `predicted_winning_team_number` is derived from the expected probability
- `predicted_win_probability` stores the larger probability
- `expected_competitiveness = 1 - abs(p - 0.5) * 2`

- `games.py` then:
  - adds bounded upset noise
  - clamps probability
  - samples the game winner probabilistically
  - generates realistic scorelines
  - derives the final match winner from games won

## Goal

Add hidden bias factors that adjust the effective team rating before the Elo win probability is calculated. These hidden factors must not be exposed to students in exported datasets unless explicitly enabled for debugging.

## Files of interest

- `projects/pickleball-sim/backend/app/generators/matches.py`
- `projects/pickleball-sim/backend/app/generators/games.py`
- existing configuration files/classes used by the simulation generator

## Implementation requirements

### 1. Preserve existing behavior by default

Add a master configuration flag:

```yaml
hidden_performance_bias_enabled: false
```

When disabled, the simulation must produce behavior equivalent to the current implementation apart from normal RNG variability already present.

### 2. Add configurable hidden bias factors

#### General

- `hidden_performance_bias_enabled`
- `hidden_bias_total_max_rating_points`
- `hidden_performance_bias_debug_enabled`

#### Age advantage

- `age_advantage_enabled`
- `age_advantage_max_rating_points`
- `age_advantage_points_per_year_gap`
- `age_advantage_close_match_multiplier`
- `age_advantage_close_match_competitiveness_threshold`

#### Fatigue

- `fatigue_enabled`
- `fatigue_window_days`
- `fatigue_points_per_recent_game`
- `fatigue_max_rating_penalty`
- `fatigue_recovery_days_threshold`

#### Regional strength

- `regional_strength_enabled`
- `regional_strength_max_rating_points`
- `regional_strength_map`

Example:

```json
{
  "Southern California": 18,
  "Florida": 15,
  "Texas": 10,
  "Arizona": 8,
  "Ontario": 4,
  "Developing Region": -8
}
```

#### Partnership affinity

- `partnership_affinity_enabled`
- `partnership_same_club_bonus`
- `partnership_matches_together_threshold_1`
- `partnership_matches_together_bonus_1`
- `partnership_matches_together_threshold_2`
- `partnership_matches_together_bonus_2`
- `partnership_recent_matches_bonus`
- `partnership_new_team_penalty`
- `partnership_max_rating_points`

#### Experience

- `experience_enabled`
- `experience_max_rating_points`
- `experience_log_multiplier`
- `experience_close_match_multiplier`
- `experience_close_match_competitiveness_threshold`

### 3. Apply hidden factors before Elo probability

In `matches.py`, locate the point where team ratings are converted to win probability:

```python
probability = 1 / (1 + 10 ** ((rating_two - rating_one) / 400))
```

Refactor this so that:

```python
team_one_effective_rating = (
    team_one_visible_rating + team_one_hidden_adjustment
)

team_two_effective_rating = (
    team_two_visible_rating + team_two_hidden_adjustment
)

probability = 1 / (
    1 + 10 ** (
        (team_two_effective_rating - team_one_effective_rating) / 400
    )
)
```

The existing:
- `predicted_winning_team_number`
- `predicted_win_probability`
- `expected_competitiveness`

should be based on the hidden-adjusted effective probability.

### 4. Keep visible ratings unchanged

Do not overwrite or mutate the original player/team ratings.

Visible ratings in exported student datasets must remain unchanged.

The hidden effective ratings and hidden adjustments must remain internal-only unless debug mode is enabled.

### 5. Create helper functions

Add modular helper functions:

- `compute_hidden_team_adjustment(team, opponent, match_context, config, rng)`
- `compute_age_adjustment(team, opponent, config)`
- `compute_fatigue_adjustment(team, match_context, config)`
- `compute_region_strength_adjustment(team, opponent, config)`
- `compute_partnership_affinity_adjustment(team, match_context, config)`
- `compute_experience_adjustment(team, opponent, match_context, config)`
- `clamp(value, min_value, max_value)`

Each helper should return a rating-point adjustment, NOT a probability adjustment.

### 6. Age advantage (HIGH IMPACT FACTOR)

Age should be treated as one of the strongest hidden performance factors.

#### Rationale

In real pickleball competition, age differences materially affect performance even among similarly rated players.

#### Formula

```python
age_gap = opponent_avg_age - team_avg_age

base_age_adjustment = (
    age_gap * age_advantage_points_per_year_gap
)

if (
    expected_competitiveness
    >= age_advantage_close_match_competitiveness_threshold
):
    base_age_adjustment *= age_advantage_close_match_multiplier

age_adjustment = clamp(
    base_age_adjustment,
    -age_advantage_max_rating_points,
    age_advantage_max_rating_points
)
```

#### Recommended defaults

```yaml
age_advantage_enabled: true
age_advantage_max_rating_points: 35
age_advantage_points_per_year_gap: 1.25
age_advantage_close_match_multiplier: 1.5
age_advantage_close_match_competitiveness_threshold: 0.75
```

### 7. Fatigue

Fatigue should be based on recent workload.

```python
fatigue_adjustment = -clamp(
    recent_games * fatigue_points_per_recent_game,
    0,
    fatigue_max_rating_penalty
)
```

#### Recommended defaults

```yaml
fatigue_enabled: true
fatigue_window_days: 14
fatigue_points_per_recent_game: 2
fatigue_max_rating_penalty: 25
fatigue_recovery_days_threshold: 3
```

### 8. Regional strength

```python
region_adjustment = clamp(
    team_region_strength - opponent_region_strength,
    -regional_strength_max_rating_points,
    regional_strength_max_rating_points
)
```

#### Recommended defaults

```yaml
regional_strength_enabled: true
regional_strength_max_rating_points: 20
```

### 9. Partnership affinity

Use available historical fields if present:
- matches together
- recent matches together
- same club
- recurring partnership history
- stable team history

Clamp final result to:

```text
+/- partnership_max_rating_points
```

#### Recommended defaults

```yaml
partnership_affinity_enabled: true
partnership_same_club_bonus: 5
partnership_matches_together_threshold_1: 10
partnership_matches_together_bonus_1: 8
partnership_matches_together_threshold_2: 25
partnership_matches_together_bonus_2: 12
partnership_recent_matches_bonus: 5
partnership_new_team_penalty: -10
partnership_max_rating_points: 25
```

### 10. Experience

```python
experience_adjustment = clamp(
    log1p(team_total_games) * experience_log_multiplier,
    0,
    experience_max_rating_points
)
```

#### Recommended defaults

```yaml
experience_enabled: true
experience_max_rating_points: 15
experience_log_multiplier: 2
experience_close_match_multiplier: 1.25
experience_close_match_competitiveness_threshold: 0.75
```

### 11. Total hidden adjustment cap

```python
hidden_adjustment = clamp(
    hidden_adjustment,
    -hidden_bias_total_max_rating_points,
    hidden_bias_total_max_rating_points
)
```

#### Recommended default

```yaml
hidden_bias_total_max_rating_points: 50
```

### 12. Recommended hidden factor priority

1. Age advantage — high impact in similarly rated matches
2. Partnership affinity — high impact for doubles realism
3. Fatigue — moderate to high impact
4. Regional strength — moderate impact
5. Experience — moderate impact

Ratings should still remain the dominant overall predictor.

### 13. Debug instrumentation

Add optional debug instrumentation:

```yaml
hidden_performance_bias_debug_enabled: false
```

When enabled, log or optionally persist:
- visible ratings
- hidden adjustments
- effective ratings
- individual factor adjustments
- final hidden-adjusted probability

Do NOT expose these in normal student-facing datasets.

### 14. games.py behavior

Do NOT fundamentally change the game simulation architecture.

`games.py` should continue to:
- start from expected probability
- add bounded upset noise
- clamp probability
- probabilistically sample the game winner
- generate realistic scorelines
- derive the final match winner from games won

### 15. Tests / validation

Add or update tests to validate:
- existing behavior remains unchanged when disabled
- effective ratings differ when enabled
- hidden adjustments respect configured caps
- missing data does not crash generation
- unknown regions default safely to 0
- exported ratings remain unchanged
- legal score generation still works correctly

### 16. Code quality expectations

Requirements:
- keep changes modular and readable
- avoid large inline logic blocks
- prefer helper functions and configuration-driven behavior
- avoid hardcoded values outside configuration defaults
- preserve existing architecture and simulation feel

## Deliverables

- Updated configuration schema/defaults
- Updated probability computation using effective ratings
- Modular helper functions
- Optional debug instrumentation
- Updated tests/validation
- Brief implementation summary and assumptions
