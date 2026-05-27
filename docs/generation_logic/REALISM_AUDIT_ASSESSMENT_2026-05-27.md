# Realism Audit Assessment

Date: 2026-05-27

## Scope

- Repository: `/home/brett/projects/pickleball-sim`
- Audit wrapper: `./scripts/run_realism_audits.sh`
- Audit mode: latest auditable generation run only, latest batch within that run only
- Snapshot executed at: `2026-05-27T00:29:04.777969+00:00`
- Local execution date in `America/Toronto`: `2026-05-26`
- Live dataset resolved by the rerun:
  - `generation_run_id = 11`
  - `batch_id = 98`
  - latest batch month = `2024-12-01`
- JSON snapshot used for this assessment:
  - `scripts/data/realism_audit_snapshots/generation_run_000011/run_000011_batch_000098_2024-12-01_20260527T002904Z.json`

## High-Level Read

This run looks materially healthier than the earlier audited datasets and it scales cleanly at much larger volume.

The strongest signals in this snapshot are:

1. Club assignment is much healthier. Unaffiliated share is nearly on target, multi-club share is close to target, and over-capacity clubs are gone.
2. Match generation is scaling plausibly. The latest batch has `98,617` matches across `566` regions with healthy type mix and weekend share.
3. Score realism remains credible. Average game margin is `4.188` and the `9_plus` blowout tail is present at `2.67%`.
4. Monthly player inflow is present across all 12 batches rather than collapsing into the first month.

The main realism issues that still stand out are narrower:

1. The `75_plus` age bucket is still too large at `11.18%` versus config `8.00%`.
2. The latest batch still has a very large zero-match player tail at `44.51%`.
3. Club geography is now more permissive, but same-region secondary membership is below target at `78.03%` versus config `85.00%`.
4. Rating confidence still appears static, with all rating-delta rows remaining in the `0_24` confidence band.

## Query-By-Query Assessment

### Players

#### `player_roster_summary`

- Result:
  - `player_count = 124092`
  - `active_player_count = 117976`
  - `unaffiliated_player_count = 15003`
  - `unaffiliated_player_pct = 12.09`
  - `multi_club_player_count = 6564`
- Assessment: acceptable
- Interpretation:
  - The overall roster scale looks right for a 100k-seed run with monthly growth.
  - The topline club-affiliation mix is now close to configured targets.

#### `player_status_distribution`

- Result:
  - `ACTIVE = 95.07%` vs config `94.00%`
  - `INJURED = 1.65%` vs config `2.00%`
  - `RETIRED = 1.70%` vs config `2.00%`
  - `INACTIVE = 1.58%` vs config `2.00%`
- Assessment: watch item
- Interpretation:
  - The drift is modest but persistent.
  - This still looks more like end-state evolution drift than broken initial assignment.

#### `player_gender_distribution`

- Result:
  - `M = 50.08%`
  - `F = 49.92%`
- Assessment: acceptable
- Interpretation:
  - Gender mix is effectively on target.

#### `player_age_distribution`

- Result:
  - `18_29 = 7.16%` vs config `8.00%`
  - `30_44 = 17.09%` vs config `18.00%`
  - `45_59 = 30.57%` vs config `32.00%`
  - `60_74 = 34.00%` vs config `34.00%`
  - `75_plus = 11.18%` vs config `8.00%`
- Assessment: real issue
- Interpretation:
  - The older tail remains the clearest player-population skew.
  - Most buckets are close enough to be believable, but `75_plus` is still elevated by `3.18` points.

#### `player_region_distribution`

- Result:
  - Top regions remain very close to configured allocation weights.
  - Example drifts among the largest regions remain small, generally within a few hundredths of a point.
- Assessment: acceptable
- Interpretation:
  - Regional allocation still looks healthy at full run scale.

#### `player_registration_by_batch`

- Result:
  - `2024-01-01 = 100000 registrations (80.59%)`
  - Later months range from `1877` to `2642` registrations each (`1.51%` to `2.13%`)
  - Later-month inflow trends upward through year-end instead of disappearing
- Assessment: improved and acceptable
- Interpretation:
  - The model still front-loads the first batch heavily, but it now produces real month-by-month inflow.
  - This is good enough for realism unless the design target is a flatter acquisition curve.

### Ratings

#### `initial_rating_distribution_summary`

- Result:
  - `avg_initial_rating = 1509.492`
  - `min_initial_rating = 696.190`
  - `max_initial_rating = 4499.951`
  - `elite_rating_count = 372`
  - `elite_rating_pct = 0.30%`
- Assessment: acceptable
- Interpretation:
  - Initial rating spread remains plausible and stable at larger population size.

### Clubs

#### `club_membership_summary`

- Result:
  - `unaffiliated_player_pct = 12.09%` vs config `12.00%`
  - `multi_club_player_pct = 5.29%` vs config `6.00%`
  - `avg_memberships_per_affiliated_player = 1.090`
- Assessment: acceptable with minor drift
- Interpretation:
  - This is a major improvement over the earlier audits.
  - Club affiliation is no longer a top-tier realism problem.

#### `club_primary_membership_integrity`

- Result:
  - `multi_primary_player_count = 0`
  - `zero_primary_player_count = 15003`
- Assessment: acceptable
- Interpretation:
  - There is no primary-membership corruption.
  - The zero-primary count matches the unaffiliated share above.

#### `club_fill_ratio_summary`

- Result:
  - `avg_fill_ratio = 0.424`
  - `max_fill_ratio = 1.000`
  - `over_capacity_club_count = 0`
  - `zero_membership_club_count = 7`
- Assessment: improved materially; acceptable
- Interpretation:
  - The capacity problem appears resolved.
  - Club utilization is now far healthier than the earlier audited runs.

#### `club_fill_ratio_outliers`

- Result:
  - Multiple clubs are exactly at `fill_ratio = 1.000`, but none exceed capacity.
  - Example top filled clubs include `Bayview Collective` and `Pioneer Dink League`.
- Assessment: acceptable
- Interpretation:
  - Saturated clubs now look like realistic edge cases rather than integrity failures.

#### `club_membership_geography`

- Result:
  - `same_region_secondary_pct = 78.03%` vs config `85.00%`
  - `cross_region_membership_count = 7658`
  - `secondary_membership_count = 9824`
- Assessment: watch item
- Interpretation:
  - Cross-region club membership is now present rather than disabled.
  - The issue is not the existence of cross-region flows, but that they are more common than config suggests.

#### `cross_region_membership_flows`

- Result:
  - The largest visible flows are modest in absolute size.
  - Several top rows involve `San Juan-Bayamón-Caguas` players joining clubs in major mainland metros.
- Assessment: watch item
- Interpretation:
  - The flow list looks plausible in shape, but it reinforces the same-region drift flagged above.

### Matches

#### `match_volume_summary`

- Result:
  - `match_count = 98617`
  - `unique_match_days = 31`
  - `distinct_match_regions = 566`
  - `avg_matches_per_match_day = 3181.194`
- Assessment: acceptable
- Interpretation:
  - Batch-level match volume looks plausible for the active population size.
  - Regional spread is broad enough that the total does not look artificially concentrated.

#### `match_type_distribution`

- Result:
  - `clinic = 0.94%` vs config `1.00%`
  - `ladder = 10.02%` vs config `10.00%`
  - `league = 20.13%` vs config `20.00%`
  - `challenge = 3.98%` vs config `4.00%`
  - `tournament = 9.91%` vs config `10.00%`
  - `recreational = 55.02%` vs config `55.00%`
- Assessment: acceptable
- Interpretation:
  - Match-type sampling is behaving exactly as intended.

#### `match_day_of_week_distribution`

- Result:
  - `Saturday = 22.02%`
  - `Sunday = 22.46%`
  - combined weekend = `44.48%`
- Assessment: acceptable
- Interpretation:
  - Weekend emphasis is present without overshooting configured bounds.

#### `weekend_match_share`

- Result:
  - `weekend_match_pct = 44.48%`
  - configured allowed range = `40.00%` to `60.00%`
- Assessment: acceptable

#### `matches_per_team_distribution`

- Result:
  - `0 = 0.39%`
  - `1 = 1.01%`
  - `2 = 3.17%`
  - `3_4 = 18.82%`
  - `5_plus = 76.60%`
- Assessment: acceptable
- Interpretation:
  - Team participation remains strong.
  - The low-volume team tail is small enough that no team-level participation defect is obvious.

#### `matches_per_player_distribution`

- Result:
  - Config inputs:
    - `configured_match_mean = 8.0`
    - `configured_match_std_dev = 4.0`
    - `configured_match_volume_noise_factor = 0.15`
  - Latest batch observed distribution:
    - `0 = 44.51%`
    - `1_2 = 2.33%`
    - `3_4 = 10.48%`
    - `5_8 = 36.21%`
    - `9_plus = 6.46%`
- Assessment: watch item
- Interpretation:
  - This remains the clearest open match-participation question.
  - Team-level volume looks healthy while player-level inactivity is still very high, which suggests selection or availability logic worth tracing.

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
  - `avg_margin = 4.188`
  - `extended_game_pct = 9.96%`
- Assessment: acceptable
- Interpretation:
  - Score realism remains much healthier than the earlier compressed-output runs.

#### `game_margin_distribution`

- Result:
  - `0_2 = 29.27%`
  - `3_5 = 45.15%`
  - `6_8 = 22.92%`
  - `9_plus = 2.67%`
- Assessment: acceptable
- Interpretation:
  - The generator now has a believable blowout tail.
  - The shape still leans competitive, but not implausibly so.

#### `upset_rate_summary`

- Result:
  - `upset_match_pct = 40.21%`
  - `avg_predicted_win_probability = 0.5939`
- Assessment: acceptable

#### `predicted_vs_actual_outcome_buckets`

- Result:
  - `50_59`: favorite won `55.35%`
  - `60_69`: favorite won `64.24%`
  - `70_79`: favorite won `73.39%`
  - `80_89`: favorite won `80.76%`
  - `90_plus`: favorite won `81.82%` on `33` matches
- Assessment: acceptable
- Interpretation:
  - Calibration is monotonic and directionally healthy.
  - The `90_plus` bucket is too small to over-interpret.

### Rating Updates

#### `rating_delta_summary`

- Result:
  - `avg_abs_rating_delta = 2.606`
  - `max_abs_rating_delta = 21.713`
  - `large_delta_count = 0`
- Assessment: acceptable
- Interpretation:
  - No rating-instability issue is visible.

#### `rating_delta_distribution`

- Result:
  - `under_25 = 100.00%`
- Assessment: acceptable under current logic

#### `rating_delta_by_confidence_band`

- Result:
  - all rows still fall into confidence band `0_24`
- Assessment: config-driven watch item
- Interpretation:
  - Confidence still appears static within the run.
  - This is probably an engine-behavior limitation rather than bad data.

#### `rating_outlier_players`

- Result:
  - largest observed absolute delta = `21.713`
- Assessment: acceptable
- Interpretation:
  - Outlier swings remain modest.

## Real Issues vs Validated Improvements

### Remaining Realism Issues

- Age distribution still shows an oversized `75_plus` bucket.
- Latest-batch player participation still has a very large zero-match bucket.
- Same-region secondary club membership is below target, implying too much cross-region club mixing.
- Player-status end-state still drifts away from configured weights.
- Rating confidence still does not appear to progress within the run.

### Validated Improvements In This Run

- Club affiliation is now very close to target.
- Club capacity is being respected in live output.
- Club utilization is dramatically healthier than earlier audits.
- Monthly player inflow is present across all 12 months.
- Match generation scales plausibly at high volume.
- Score-margin realism remains materially better than the early compressed-output runs.

### Acceptable Under Current Logic

- Gender distribution
- Region distribution
- Initial rating distribution
- Match-type mix
- Weekend scheduling share
- Team-level participation distribution
- Match outcome calibration
- Rating stability

## Highest-Value Next Refinements

### 1. Investigate the Zero-Match Player Bucket

- Break the `0` bucket out by player status, availability, team membership, and club affiliation.
- Verify whether player-level scheduling eligibility is stricter than intended.

Why this matters:

- It is still the clearest unresolved participation realism gap.

### 2. Reduce the `75_plus` Skew

- Trace age generation and age-at-batch calculations end to end.
- Check whether late-year growth cohorts or birth-date handling are biasing the upper tail.

Why this matters:

- The age distribution now looks stable enough that this skew is probably real.

### 3. Tune Cross-Region Club Assignment

- Review how secondary memberships are selected once a player is already affiliated.
- Check whether long-distance fallback behavior is firing too aggressively.

Why this matters:

- The current geography mix is plausible in shape but looser than config intends.

### 4. Reconcile Player-Status End-State vs Config Intent

- Decide whether status weights are intended to describe initial assignment, year-end steady state, or both.
- If they are intended to govern end-state too, tune the status transition logic.

Why this matters:

- It will separate configuration semantics from actual realism defects.

### 5. Decide Whether Confidence Should Progress Within a Run

- If confidence growth is intended, the current all-`0_24` result needs a generation-side fix.
- If static confidence is intentional, make that explicit in audit messaging.

Why this matters:

- It will stop a recurring ambiguous warning and clarify whether the rating engine is behaving as designed.
