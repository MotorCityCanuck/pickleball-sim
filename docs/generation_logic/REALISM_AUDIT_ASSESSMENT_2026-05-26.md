# Realism Audit Assessment

Date: 2026-05-26

## Scope

- Repository: `/home/brett/projects/pickleball-sim`
- Audit wrapper: `./scripts/run_realism_audits.sh`
- Audit mode: latest auditable generation run only, latest batch within that run only
- Live dataset resolved by the rerun:
  - `generation_run_id = 10`
  - `batch_id = 86`
  - latest batch month = `2024-12-01`
- Fresh JSON output captured to:
  - `/tmp/pickleball_realism_audit_2026-05-26.json`
  - `data/realism_audit_snapshots/generation_run_000010/run_000010_batch_000086_2024-12-01_20260526T130601Z.json`

## High-Level Read

This 20k / 12 month rerun is materially healthier than the previous audited dataset.

The recent realism fixes are visible in live output:

1. Match volume is no longer locked to a flat monthly total for a fixed-size roster.
2. Monthly player registration is no longer concentrated entirely in the first batch.
3. Club assignment is no longer producing over-capacity clubs.
4. Score margins are materially broader than before, with a real blowout tail now present.

The main realism concerns that remain are narrower:

1. Club affiliation still drifts away from config, with unaffiliated players above target and multi-club players below target.
2. Player-status mix is drifting away from the configured weights by the end of the year.
3. Match participation still has a very large zero-match tail in the latest batch.
4. Rating-confidence progression remains static because confidence is still not increasing within the run.

## Query-By-Query Assessment

### Players

#### `player_roster_summary`

- Result:
  - `player_count = 24888`
  - `active_player_count = 23723`
  - `unaffiliated_player_count = 3651`
  - `unaffiliated_player_pct = 14.67`
  - `multi_club_player_count = 1263`
- Assessment: acceptable topline counts, but club-affiliation drift remains
- Interpretation:
  - The overall roster scale looks right for a 20k-target run with monthly growth.
  - The remaining realism concern here is affiliation mix, not population size.

#### `player_status_distribution`

- Result:
  - `ACTIVE = 95.32%` vs config `94.00%`
  - `INJURED = 1.51%` vs config `2.00%`
  - `RETIRED = 1.63%` vs config `2.00%`
  - `INACTIVE = 1.54%` vs config `2.00%`
- Assessment: watch item
- Interpretation:
  - The drift is not catastrophic, but at this population size it is too large to dismiss as simple sampling noise.
  - This likely reflects year-end status evolution rather than initial assignment error, so the audit may be comparing a live end-state against an initial-weight config.

#### `player_gender_distribution`

- Result:
  - `M = 50.45%`
  - `F = 49.55%`
- Assessment: acceptable
- Interpretation:
  - Gender mix remains effectively on target.

#### `player_age_distribution`

- Result:
  - `18_29 = 7.18%` vs config `8.00%`
  - `30_44 = 17.27%` vs config `18.00%`
  - `45_59 = 30.67%` vs config `32.00%`
  - `60_74 = 33.66%` vs config `34.00%`
  - `75_plus = 11.23%` vs config `8.00%`
- Assessment: real issue
- Interpretation:
  - The under-18 artifact is gone, so this query is now much more credible than the prior audit.
  - Most buckets are within roughly 1.3 points of config, but `75_plus` is still elevated by `3.23` points.
  - This now looks like a real population-shape issue worth investigating, not just an audit artifact.

#### `player_region_distribution`

- Result:
  - Top regions are all close to configured allocation weights.
- Assessment: acceptable
- Interpretation:
  - Regional allocation still looks healthy.
  - The visible drifts in the leading regions are small.

#### `player_registration_by_batch`

- Result:
  - `2024-01-01 = 20000 registrations (80.36%)`
  - Each later month adds roughly `405` to `487` registrations (`1.63%` to `1.96%` each)
- Assessment: improved and now acceptable
- Interpretation:
  - The previous first-batch-only pattern is gone.
  - The model still front-loads registrations heavily, but there is now real monthly inflow across the year.

### Ratings

#### `initial_rating_distribution_summary`

- Result:
  - `avg_initial_rating = 1508.709`
  - `min_initial_rating = 706.321`
  - `max_initial_rating = 4498.948`
  - `elite_rating_count = 75`
  - `elite_rating_pct = 0.30%`
- Assessment: acceptable
- Interpretation:
  - Initial rating spread remains plausible and stable.

### Clubs

#### `club_membership_summary`

- Result:
  - `unaffiliated_player_pct = 14.67%` vs config `12.00%`
  - `multi_club_player_pct = 5.07%` vs config `6.00%`
  - `avg_memberships_per_affiliated_player = 1.088`
- Assessment: real issue
- Interpretation:
  - This is improved only marginally from the prior audit and remains the clearest club-side realism gap.
  - The output still has too many unaffiliated players and not enough multi-club participation.

#### `club_primary_membership_integrity`

- Result:
  - `multi_primary_player_count = 0`
  - `zero_primary_player_count = 3651`
- Assessment: acceptable
- Interpretation:
  - There is no primary-membership corruption.
  - The zero-primary count lines up with the unaffiliated population above.

#### `club_fill_ratio_summary`

- Result:
  - `avg_fill_ratio = 0.085`
  - `max_fill_ratio = 0.952`
  - `over_capacity_club_count = 0`
  - `zero_membership_club_count = 417`
- Assessment: improved and acceptable
- Interpretation:
  - The over-capacity defect is resolved in this run.
  - Club utilization is still low overall, but the specific capacity-violation realism problem is gone.

#### `club_fill_ratio_outliers`

- Result:
  - Highest fill ratio club:
    - `Boston Paddle Pickleball Club`
    - `member_capacity = 21`
    - `membership_count = 20`
    - `fill_ratio = 0.952`
- Assessment: acceptable
- Interpretation:
  - The outlier set now looks realistic.
  - No clubs are breaching configured capacity.

#### `club_membership_geography`

- Result:
  - `same_region_secondary_pct = 100.00%`
  - `cross_region_membership_count = 0`
- Assessment: acceptable under current config
- Interpretation:
  - This matches the current no-cross-region setting.

#### `cross_region_membership_flows`

- Result:
  - no rows
- Assessment: acceptable under current config

### Matches

#### `match_volume_summary`

- Result:
  - `match_count = 19744`
  - `unique_match_days = 31`
  - `distinct_match_regions = 516`
  - `avg_matches_per_match_day = 636.903`
- Assessment: acceptable
- Interpretation:
  - Batch-level match volume looks plausible for the active population size.

#### `match_type_distribution`

- Result:
  - All match types are within `0.50` percentage points of config.
- Assessment: acceptable
- Interpretation:
  - Match-type sampling is behaving as configured.

#### `match_day_of_week_distribution`

- Result:
  - `Saturday = 22.52%`
  - `Sunday = 22.61%`
  - combined weekend = `45.14%`
- Assessment: acceptable
- Interpretation:
  - Weekend emphasis remains present without overshooting the configured band.

#### `weekend_match_share`

- Result:
  - `weekend_match_pct = 45.14%`
  - configured allowed range = `40.00%` to `60.00%`
- Assessment: acceptable

#### `matches_per_team_distribution`

- Result:
  - `0 = 0.36%`
  - `1 = 0.80%`
  - `2 = 2.99%`
  - `3_4 = 19.11%`
  - `5_plus = 76.73%`
- Assessment: acceptable
- Interpretation:
  - Team participation is strong and no longer shows the earlier low-volume shape.

#### `matches_per_player_distribution`

- Result:
  - Config inputs:
    - `configured_match_mean = 8.0`
    - `configured_match_std_dev = 4.0`
    - `configured_match_volume_noise_factor = 0.15`
  - Latest batch observed distribution:
    - `0 = 44.63%`
    - `1_2 = 2.11%`
    - `3_4 = 10.62%`
    - `5_8 = 36.60%`
    - `9_plus = 6.04%`
- Assessment: watch item
- Interpretation:
  - The new audit is working and confirms that the batch is no longer deterministically flat.
  - The main thing to watch is the very large zero-match bucket for active players in the latest batch.
  - This may be an intended byproduct of active-player selection, team continuity, or availability filtering, but it is large enough to justify follow-up analysis.

#### `daily_team_match_cap_violations`

- Result:
  - no rows
- Assessment: acceptable

#### `batch_region_match_distribution`

- Result:
  - Region concentration broadly tracks player concentration.
- Assessment: acceptable

### Scores

#### `game_competitiveness_summary`

- Result:
  - `avg_margin = 4.161`
  - `extended_game_pct = 10.21%`
- Assessment: improved materially; acceptable for now
- Interpretation:
  - This is clearly broader than the previous audit.
  - The score generator is no longer producing an obviously over-compressed outcome band.

#### `game_margin_distribution`

- Result:
  - `0_2 = 30.06%`
  - `3_5 = 44.68%`
  - `6_8 = 22.44%`
  - `9_plus = 2.82%`
- Assessment: improved materially; acceptable for now
- Interpretation:
  - This is a major improvement over the previous run, where almost no blowouts existed.
  - The margin shape still leans competitive, but it now has a believable tail.

#### `upset_rate_summary`

- Result:
  - `upset_match_pct = 40.30%`
  - `avg_predicted_win_probability = 0.5925`
- Assessment: acceptable

#### `predicted_vs_actual_outcome_buckets`

- Result:
  - `50_59`: favorite won `55.00%`
  - `60_69`: favorite won `64.46%`
  - `70_79`: favorite won `74.61%`
  - `80_89`: favorite won `84.70%`
  - `90_plus`: favorite won `100.00%` on `9` matches
- Assessment: acceptable
- Interpretation:
  - Calibration remains monotonic and directionally healthy.

### Rating Updates

#### `rating_delta_summary`

- Result:
  - `avg_abs_rating_delta = 2.577`
  - `max_abs_rating_delta = 20.575`
  - `large_delta_count = 0`
- Assessment: acceptable
- Interpretation:
  - No rating-instability problem is visible.

#### `rating_delta_distribution`

- Result:
  - `under_25 = 100.00%`
- Assessment: acceptable under current logic
- Interpretation:
  - Rating movement remains conservative, but not broken.

#### `rating_delta_by_confidence_band`

- Result:
  - all rows still fall into confidence band `0_24`
- Assessment: config-driven watch item
- Interpretation:
  - Confidence is still effectively static within the run.
  - The query is behaving correctly, but it is reporting a configuration or engine-behavior limitation rather than a data corruption issue.

#### `rating_outlier_players`

- Result:
  - largest observed absolute delta = `20.575`
- Assessment: acceptable
- Interpretation:
  - Outlier swings are still modest.

## Real Issues vs Validated Improvements

### Remaining Realism Issues

- Club affiliation drift remains above target, especially unaffiliated share.
- Age distribution still shows an oversized `75_plus` bucket.
- Player-status end-state drifts away from configured weights.
- Latest-batch player match participation has a large zero-match bucket.

### Validated Improvements In This Run

- Monthly player inflow is now present across all 12 months.
- Club capacity is now being respected in live output.
- Match-volume variability is now visible in the generated dataset and audit pack.
- Team participation volume looks much healthier.
- Score-margin realism is materially better than the previous audit.

### Acceptable Under Current Logic

- Gender distribution
- Region distribution
- Match-type mix
- Weekend scheduling share
- Match outcome calibration
- Rating stability
- No cross-region club flows with cross-region assignment disabled

## Highest-Value Next Refinements

### 1. Reduce Unaffiliated Drift

- Revisit club-assignment supply logic and fallback behavior.
- Check whether some regions still have too little club coverage for the configured affiliation targets.

Why this matters:

- It is still the clearest unresolved realism gap in the live dataset.

### 2. Investigate the `75_plus` Skew

- Trace age generation against birth-date, registration-date, and latest-batch-date usage.
- Verify whether late-year growth cohorts or status evolution are biasing the older tail.

Why this matters:

- The age audit now appears to be measuring something real.

### 3. Investigate the Zero-Match Player Bucket

- Break out the `0` bucket by status, team membership, team persistence, and club affiliation.
- Confirm whether inactive scheduling at the player level is higher than intended.

Why this matters:

- The team-level distribution looks healthy while player-level participation still has a large inactive tail.
- That mismatch is a strong clue for the next realism pass.

### 4. Reconcile Player-Status End-State vs Config Intent

- Decide whether the config weights are supposed to describe initial status assignment or year-end steady state.
- If they are meant to govern the end-state too, the status transition logic needs tuning.

Why this matters:

- The current audit is likely surfacing a semantic mismatch between configuration intent and observed end-state.

### 5. Decide Whether Confidence Should Progress Within a Run

- If confidence growth is intended, the current zero-band result needs a generation-side fix.
- If static confidence is intentional, add explicit audit messaging so this does not keep surfacing as a vague warning.

Why this matters:

- It will separate config-driven behavior from genuine rating-engine realism problems.
