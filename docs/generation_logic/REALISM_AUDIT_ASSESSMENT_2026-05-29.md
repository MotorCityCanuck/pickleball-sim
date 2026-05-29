# Realism Audit Assessment

Date: 2026-05-29

## Scope

- Repository: `/home/brett/projects/pickleball-sim`
- Audit command: `backend/scripts/run_realism_audit.py --format json`
- Audit mode: latest auditable generation run only, latest batch within that run only
- Snapshot executed at: `2026-05-29T16:47:37.855644+00:00`
- Live dataset resolved by the audit:
  - `generation_run_id = 15`
  - `batch_id = 146`
  - latest batch month = `2024-12-01`
- JSON snapshot used for this assessment:
  - `backend/data/realism_audit_snapshots/generation_run_000015/run_000015_batch_000146_2024-12-01_20260529T164737Z.json`
- Audit query count: `32`

## High-Level Read

This large run completed successfully and the realism audit is broadly healthy
at the largest scale tested so far. The final roster contains `313,277`
players, with `298,102` active players and a December batch containing
`438,258` matches.

The strongest signals are:

1. Player status, gender, regional allocation, and monthly growth are stable at
   scale.
2. Club capacity integrity is now strong: `0` over-capacity clubs and `0`
   zero-membership clubs.
3. Match-type mix, weekend share, day-of-week distribution, and regional spread
   look credible in the latest month.
4. Score outcomes are well calibrated: upset rates align closely with predicted
   probabilities across probability buckets.
5. Rating movement is stable: `1,753,032` player-match updates with no large
   deltas above the configured warning threshold.

The main watch items are:

1. The `75_plus` age bucket remains high at `11.24%` versus configured `8.00%`.
2. Club utilization may now be too saturated overall, with average fill ratio
   `0.973` and many large clubs exactly at capacity.
3. Same-region secondary membership is low at `64.95%` versus configured
   `85.00%`, indicating more cross-region membership than expected.
4. Rating confidence remains static in the `0_24` band for all rating-delta
   rows.

## Query-By-Query Assessment

### Players

#### `player_roster_summary`

- Result:
  - `player_count = 313,277`
  - `active_player_count = 298,102`
  - `unaffiliated_player_count = 37,815`
  - `unaffiliated_player_pct = 12.07`
  - `multi_club_player_count = 16,463`
- Assessment: acceptable
- Interpretation:
  - The final roster scale is consistent with a 250k initial load plus monthly
    growth over 12 months.
  - Unaffiliated share remains almost exactly on target.

#### `player_status_distribution`

- Result:
  - `ACTIVE = 95.16%` vs config `94.00%`
  - `INJURED = 1.63%` vs config `2.00%`
  - `RETIRED = 1.62%` vs config `2.00%`
  - `INACTIVE = 1.59%` vs config `2.00%`
- Assessment: watch item
- Interpretation:
  - The drift is modest and similar to prior audits.
  - This still looks like end-state drift rather than a severe distribution
    failure.

#### `player_gender_distribution`

- Result:
  - `M = 50.09%`
  - `F = 49.91%`
- Assessment: acceptable
- Interpretation:
  - Gender mix remains effectively on target at large scale.

#### `player_age_distribution`

- Result:
  - `18_29 = 7.15%` vs config `8.00%`
  - `30_44 = 17.13%` vs config `18.00%`
  - `45_59 = 30.65%` vs config `32.00%`
  - `60_74 = 33.82%` vs config `34.00%`
  - `75_plus = 11.24%` vs config `8.00%`
- Assessment: real issue
- Interpretation:
  - Most age buckets are close enough to be credible.
  - The `75_plus` bucket remains consistently elevated and is still the
    clearest player-population shape issue.

#### `player_region_distribution`

- Result:
  - Top-region allocation remains close to configured weights.
  - Example largest-region drifts remain small: New York area `-0.03`, Los
    Angeles area `0.00`, Houston area `0.02`, Toronto area `0.01`.
- Assessment: acceptable
- Interpretation:
  - Regional allocation continues to scale well.

#### `player_registration_by_batch`

- Result:
  - `2024-01-01 = 250,000 registrations (79.80%)`
  - Later monthly registrations range from approximately `5,041` to `6,861`
    each.
  - Latest visible monthly batch, `2024-12-01`, contains `6,861`
    registrations.
- Assessment: acceptable
- Interpretation:
  - The first month is intentionally dominant because it is the initial history
    foundation.
  - Monthly player inflow is present and continues through the full 12-month
    run.

### Ratings

#### `initial_rating_distribution_summary`

- Result:
  - `avg_initial_rating = 1507.200`
  - `min_initial_rating = 623.684`
  - `max_initial_rating = 4499.990`
  - `elite_rating_count = 903`
  - `elite_rating_pct = 0.29%`
  - `sub_1000_count = 1,996`
- Assessment: acceptable
- Interpretation:
  - Initial ratings remain centered near the intended population shape.
  - The elite tail remains close to the configured target.

#### `rating_delta_summary`

- Result:
  - `player_update_count = 1,753,032`
  - `avg_abs_rating_delta = 2.811`
  - `max_abs_rating_delta = 42.869`
  - `large_delta_count = 0`
  - configured warning threshold = `300.0`
- Assessment: acceptable
- Interpretation:
  - Rating updates are stable despite the large monthly match volume.
  - No large movement warnings were triggered.

#### `rating_delta_distribution`

- Result:
  - `under_25 = 99.93%`
  - `25_49 = 0.07%`
- Assessment: acceptable
- Interpretation:
  - Rating movement is tightly controlled.

#### `rating_delta_by_confidence_band`

- Result:
  - all `1,753,032` player updates remain in confidence band `0_24`
- Assessment: watch item
- Interpretation:
  - Confidence still appears static or insufficiently progressive.
  - If static confidence is intentional, the audit should label this explicitly
    rather than continuing to surface it as an ambiguous signal.

### Clubs

#### `club_membership_summary`

- Result:
  - `unaffiliated_player_pct = 12.07%` vs config `12.00%`
  - `multi_club_player_pct = 5.26%` vs config `6.00%`
  - `avg_memberships_per_affiliated_player = 1.090`
  - `multi_primary_player_count = 0`
- Assessment: acceptable with minor drift
- Interpretation:
  - Club affiliation is close to target.
  - Multi-club participation remains slightly low but not severe.

#### `club_primary_membership_integrity`

- Result:
  - `multi_primary_player_count = 0`
  - `zero_primary_player_count = 37,815`
  - `valid_primary_player_count = 275,462`
- Assessment: acceptable
- Interpretation:
  - There is no primary-membership integrity problem.
  - The zero-primary count aligns with unaffiliated players.

#### `club_fill_ratio_summary`

- Result:
  - `club_count = 4,000`
  - `capacity_tracked_club_count = 4,000`
  - `avg_fill_ratio = 0.973`
  - `max_fill_ratio = 1.000`
  - `over_capacity_club_count = 0`
  - `zero_membership_club_count = 0`
- Assessment: acceptable integrity; realism watch item
- Interpretation:
  - The previous over-capacity concern is resolved.
  - Utilization may now be too saturated at this scale, because the average club
    is near full capacity and many clubs are exactly full.

#### `club_fill_ratio_outliers`

- Result:
  - Top listed clubs have `fill_ratio = 1.000`.
  - No listed club exceeds capacity.
- Assessment: acceptable with saturation watch
- Interpretation:
  - Saturated clubs are no longer integrity failures.
  - The number of saturated clubs may indicate that club supply/capacity should
    scale more aggressively for 250k+ initial populations.

#### `club_membership_geography`

- Result:
  - `same_region_secondary_pct = 64.95%` vs config `85.00%`
  - `cross_region_membership_count = 66,653`
  - `secondary_membership_count = 24,670`
  - total `membership_count = 300,132`
- Assessment: real issue or configuration mismatch
- Interpretation:
  - Cross-region membership is much more common than the same-region secondary
    target implies.
  - This may be a club-capacity side effect: saturated local clubs could be
    pushing memberships into other regions.

### Matches

#### `match_volume_summary`

- Result:
  - `match_count = 438,258`
  - `unique_match_days = 31`
  - `distinct_match_regions = 572`
  - `avg_matches_per_match_day = 14,137.355`
- Assessment: acceptable
- Interpretation:
  - Match volume is very large but broadly distributed across regions and days.
  - This result also confirms why the matches stage dominates runtime.

#### `match_type_distribution`

- Result:
  - `clinic = 1.01%` vs config `1.00%`
  - `ladder = 10.15%` vs config `10.00%`
  - `league = 19.87%` vs config `20.00%`
  - `challenge = 3.99%` vs config `4.00%`
  - `tournament = 9.99%` vs config `10.00%`
  - `recreational = 54.99%` vs config `55.00%`
- Assessment: acceptable
- Interpretation:
  - Match-type sampling remains excellent at scale.

#### `match_day_of_week_distribution` and `weekend_match_share`

- Result:
  - Sunday = `22.51%`
  - Saturday = `21.94%`
  - combined weekend share = `44.45%`
  - configured weekend range = `40.00%` to `60.00%`
- Assessment: acceptable
- Interpretation:
  - Weekend concentration is inside the configured realism range.
  - The full day-of-week shape remains plausible.

#### `matches_per_team_distribution`

- Result:
  - `0 matches = 0.35%` of teams
  - `1 match = 1.08%`
  - `2 matches = 3.07%`
  - `3_4 matches = 18.92%`
  - `5_plus matches = 76.57%`
- Assessment: acceptable
- Interpretation:
  - Most teams are active in the latest month.
  - A small zero-match team tail remains, but it is not large.

#### `matches_per_player_distribution`

- Result:
  - `0 matches = 2.32%` of players
  - `1_2 matches = 4.07%`
  - `3_4 matches = 18.54%`
  - `5_8 matches = 63.97%`
  - `9_plus matches = 11.10%`
- Assessment: acceptable
- Interpretation:
  - The zero-match player problem is much smaller than prior runs.
  - Most active players fall in a plausible `5_8` monthly match range.

#### `zero_match_players_by_registration_cohort`

- Result:
  - initial-batch zero-match rate = `1.33%`
  - later-batch zero-match rate = `6.00%`
- Assessment: acceptable with watch item
- Interpretation:
  - Later entrants are more likely to have no latest-month matches, which is
    plausible.
  - The gap is worth monitoring but not a top-tier issue.

#### `zero_match_players_by_team_membership`

- Result:
  - teamed zero-match rate = `0.35%`
  - unteamed zero-match rate = `100.00%`
  - unteamed active player count = `5,882`
- Assessment: explanatory
- Interpretation:
  - Zero-match players are strongly explained by missing team membership.
  - Improving unteamed-player handling would directly reduce zero-match tails.

#### `daily_team_match_cap_violations`

- Result:
  - no rows
- Assessment: acceptable
- Interpretation:
  - The daily team cap constraint appears respected.

#### `batch_region_match_distribution`

- Result:
  - all `572` regions have match activity.
  - largest region shares are broadly aligned with player distribution.
- Assessment: acceptable
- Interpretation:
  - Regional match allocation scales well.

### Scores

#### `game_competitiveness_summary`

- Result:
  - `game_count = 657,370`
  - `avg_margin = 4.323`
  - `extended_game_pct = 10.00%`
- Assessment: acceptable
- Interpretation:
  - Game margins and extension rate remain plausible at large scale.

#### `game_margin_distribution`

- Result:
  - `0_2 = 28.05%`
  - `3_5 = 43.85%`
  - `6_8 = 24.43%`
  - `9_plus = 3.68%`
- Assessment: acceptable
- Interpretation:
  - The score distribution has a credible mix of close, moderate, and larger
    margin games.
  - Blowouts are present without dominating.

#### `upset_rate_summary`

- Result:
  - `total_matches = 438,258`
  - `upset_match_count = 172,203`
  - `upset_match_pct = 39.29%`
  - `avg_predicted_win_probability = 0.6053`
- Assessment: acceptable
- Interpretation:
  - The upset rate is credible given the average favorite probability.

#### `predicted_vs_actual_outcome_buckets`

- Result:
  - `50_59`: favorite win `54.90%`, avg predicted `54.68%`
  - `60_69`: favorite win `64.49%`, avg predicted `64.33%`
  - `70_79`: favorite win `74.25%`, avg predicted `74.19%`
  - `80_89`: favorite win `83.61%`, avg predicted `83.81%`
  - `90_plus`: favorite win `91.71%`, avg predicted `90.53%`
- Assessment: strong
- Interpretation:
  - Predicted probabilities are very well calibrated to actual outcomes.
  - This is one of the strongest signals in the audit.

## Overall Assessment

The large run is realistic enough to serve as a strong candidate baseline for
student-facing dataset work, subject to the known student export exclusions and
the need to solve export packaging separately.

The most important realism improvements to consider next are:

1. Reduce or explain the persistent `75_plus` age skew.
2. Investigate club capacity/supply scaling, because club utilization is now
   almost fully saturated at 250k+ initial player scale.
3. Investigate secondary club geography, especially why same-region secondary
   membership is far below the configured target.
4. Clarify whether confidence is intentionally static; if not, add confidence
   progression.
5. Continue using match-stage runtime optimization as the primary engineering
   priority, since the audit confirms very high latest-month match volume.

## Notes For Future Comparison

- This audit covers only the latest auditable batch within the latest generation
  run, not every monthly batch.
- The latest audited batch contains the largest monthly workload and is
  therefore useful for stress realism checks.
- Runtime observations from the completed 12-month build should be tracked
  separately in the generation runtime optimization document.
