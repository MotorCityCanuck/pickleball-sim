# Realism Audit Assessment

Date: 2026-05-21

## Scope

- Repository: `/home/brett/projects/pickleball-sim`
- Audit wrapper: `./scripts/run_realism_audits.sh`
- Audit mode: latest generation run only, latest batch within that run only
- Live dataset resolved by the runner:
  - `generation_run_id = 3`
  - `batch_id = 36`
  - latest batch month = `2024-12-01`
- Full JSON output captured to `/tmp/pickleball_realism_audit.json`

## High-Level Read

The live realism audit is generally healthy on status mix, gender mix, regional allocation, match-type mix, weekend scheduling, outcome calibration, and rating stability. The main problems are concentrated in four areas:

1. The current age audit is measuring the wrong moment in time for this generator.
2. Player registrations are effectively single-batch, so monthly inflow realism is not present.
3. Club assignment is constrained by club coverage and does not enforce capacity.
4. Game scores are too compressed, producing too many medium-close games and almost no blowouts.

## Query-By-Query Assessment

### Players

#### `player_roster_summary`

- Result:
  - `player_count = 25000`
  - `active_player_count = 23521`
  - `unaffiliated_player_count = 3698`
  - `unaffiliated_player_pct = 14.79`
  - `multi_club_player_count = 1234`
- Assessment: real issue
- Interpretation:
  - The topline counts are fine.
  - The affiliation metrics indicate drift that needs explanation from club supply and assignment logic.

#### `player_status_distribution`

- Result:
  - `ACTIVE = 94.08%` vs config `94.00%`
  - `INJURED = 1.95%` vs config `2.00%`
  - `RETIRED = 2.11%` vs config `2.00%`
  - `INACTIVE = 1.86%` vs config `2.00%`
- Assessment: acceptable
- Interpretation:
  - All drifts are within 0.14 percentage points.
  - This is behaving as configured.

#### `player_gender_distribution`

- Result:
  - `M = 50.24%`
  - `F = 49.76%`
- Assessment: acceptable
- Interpretation:
  - This is effectively on target.

#### `player_age_distribution`

- Result from current audit:
  - `18_29 = 13.87%` vs config `8.00%`
  - `30_44 = 25.28%` vs config `18.00%`
  - `45_59 = 29.88%` vs config `32.00%`
  - `60_74 = 19.56%` vs config `34.00%`
  - `75_plus = 3.12%` vs config `8.00%`
  - `under_18 = 8.30%`
- Assessment: audit artifact, not a real population problem
- Interpretation:
  - The audit currently computes age from `registration_date - birth_date`.
  - The generator samples birth date relative to the batch month, but can assign a registration date much earlier.
  - That makes many players appear younger at registration than the intended age cohort.
  - When measured at the latest batch date `2024-12-01`, the actual live population age mix is:
    - `under_18 = 0.06%`
    - `18_29 = 8.11%`
    - `30_44 = 18.08%`
    - `45_59 = 31.95%`
    - `60_74 = 33.80%`
    - `75_plus = 8.00%`
  - That distribution is very close to config.

#### `player_region_distribution`

- Result:
  - Top regions are close to configured selection weights.
- Assessment: acceptable
- Interpretation:
  - Regional allocation appears to be tracking the configured probability model well.

#### `player_registration_by_batch`

- Result:
  - `2024-01-01 = 25000 registrations`
  - All later batches = `0 registrations`
- Assessment: real issue
- Interpretation:
  - This confirms that the current pipeline seeds the full population in the first batch only.
  - Monthly player inflow is not currently being modeled.

### Ratings

#### `initial_rating_distribution_summary`

- Result:
  - `avg_initial_rating = 1507.941`
  - `min_initial_rating = 688.232`
  - `max_initial_rating = 4499.801`
  - `elite_rating_count = 71`
  - `elite_rating_pct = 0.28%`
- Assessment: acceptable
- Interpretation:
  - This looks consistent with the configured initial mean and elite tail.

### Clubs

#### `club_membership_summary`

- Result:
  - `unaffiliated_player_pct = 14.79%` vs config `12.00%`
  - `multi_club_player_pct = 4.94%` vs config `6.00%`
  - `avg_memberships_per_affiliated_player = 1.085`
- Assessment: real issue, but largely supply-driven
- Interpretation:
  - The drift is not just random sampler noise.
  - Diagnostics against the live dataset show:
    - `712` players live in regions with no clubs.
    - `1,534` players live in regions with fewer than two clubs.
  - That directly pushes unaffiliated upward and suppresses multi-club assignment.

#### `club_primary_membership_integrity`

- Result:
  - `multi_primary_player_count = 0`
  - `zero_primary_player_count = 3698`
- Assessment: acceptable
- Interpretation:
  - No primary-membership corruption is present.
  - The zero-primary population lines up with the unaffiliated segment above.

#### `club_fill_ratio_summary`

- Result:
  - `avg_fill_ratio = 0.085`
  - `max_fill_ratio = 1.333`
  - `over_capacity_club_count = 1`
  - `zero_membership_club_count = 405`
- Assessment: real issue
- Interpretation:
  - Most clubs are lightly loaded.
  - There is at least one true overflow case, which means selection is not respecting capacity.

#### `club_fill_ratio_outliers`

- Result:
  - Top outlier:
    - `Victory Pickleball Club`
    - `member_capacity = 18`
    - `membership_count = 24`
    - `fill_ratio = 1.333`
- Assessment: real issue
- Interpretation:
  - This club is over capacity by `6`.
  - The current club selector weights by capacity but does not enforce capacity as a hard limit.

#### `club_membership_geography`

- Result:
  - `same_region_secondary_pct = 100.00%`
  - `cross_region_membership_count = 0`
- Assessment: acceptable
- Interpretation:
  - This is expected because cross-region assignment is disabled in the run snapshot.

#### `cross_region_membership_flows`

- Result:
  - no rows
- Assessment: acceptable
- Interpretation:
  - Also expected with cross-region assignment disabled.

### Matches

#### `match_volume_summary`

- Result:
  - `match_count = 16464`
  - `unique_match_days = 31`
  - `distinct_match_regions = 510`
  - `avg_matches_per_match_day = 531.097`
- Assessment: acceptable
- Interpretation:
  - Nothing obviously implausible here.

#### `match_type_distribution`

- Result:
  - All match types are within 0.27 percentage points of config.
- Assessment: acceptable
- Interpretation:
  - The type sampler is behaving as intended.

#### `match_day_of_week_distribution`

- Result:
  - `Saturday = 21.74%`
  - `Sunday = 22.49%`
  - combined weekend = `44.24%`
- Assessment: acceptable
- Interpretation:
  - Weekend emphasis is present without breaching configured realism bounds.

#### `weekend_match_share`

- Result:
  - `weekend_match_pct = 44.24%`
  - configured allowed range = `40.00%` to `60.00%`
- Assessment: acceptable

#### `matches_per_team_distribution`

- Result:
  - `0 = 1.91%`
  - `1 = 7.56%`
  - `2 = 14.60%`
  - `3_4 = 38.80%`
  - `5_plus = 37.14%`
- Assessment: acceptable
- Interpretation:
  - No clear realism failure from this bucketization alone.

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
  - `avg_margin = 3.442`
  - `extended_game_pct = 10.10%`
- Assessment: real issue
- Interpretation:
  - The score generator is producing a narrow band of outcomes.
  - Extended games happen, but overall scorelines still look too compressed.

#### `game_margin_distribution`

- Result:
  - `0_2 = 27.07%`
  - `3_5 = 67.50%`
  - `6_8 = 5.42%`
  - `9_plus = 0.01%`
- Assessment: real issue
- Interpretation:
  - Nearly all games land in the 0 to 5 margin range, with almost no blowouts.
  - This is consistent with the current bounded loser-score logic in the game generator.

#### `upset_rate_summary`

- Result:
  - `upset_match_pct = 41.34%`
  - `avg_predicted_win_probability = 0.5870`
- Assessment: acceptable
- Interpretation:
  - This is not obviously out of line given how modest the average favorite edge is.

#### `predicted_vs_actual_outcome_buckets`

- Result:
  - `50_59`: favorite won `54.42%`
  - `60_69`: favorite won `62.91%`
  - `70_79`: favorite won `75.97%`
  - `80_89`: favorite won `86.64%`
  - `90_plus`: favorite won `100.00%` on only `10` matches
- Assessment: acceptable
- Interpretation:
  - Calibration improves monotonically by bucket.
  - This looks directionally healthy.

### Rating Updates

#### `rating_delta_summary`

- Result:
  - `avg_abs_rating_delta = 2.167`
  - `max_abs_rating_delta = 16.409`
  - `large_delta_count = 0`
- Assessment: acceptable
- Interpretation:
  - No runaway rating-movement problem is visible.

#### `rating_delta_distribution`

- Result:
  - `under_25 = 100.00%`
- Assessment: acceptable under current logic, but conservative
- Interpretation:
  - This is not broken.
  - It does suggest rating movement is tightly compressed.

#### `rating_delta_by_confidence_band`

- Result:
  - all rows fall into confidence band `0_24`
- Assessment: audit artifact relative to run configuration
- Interpretation:
  - The latest generation run snapshot has `confidence_increment_per_match = 0`.
  - That means confidence never rises above the initial value `0.1`.
  - The query is working, but it is reflecting a configuration choice more than a generator defect.

#### `rating_outlier_players`

- Result:
  - largest observed absolute delta = `16.409`
- Assessment: acceptable
- Interpretation:
  - Outlier swings are modest and do not indicate instability.

## Real Issues vs Acceptable Artifacts

### True Realism Issues

- Single-batch registration pattern with no monthly player inflow
- Club coverage gaps driving involuntary unaffiliation
- Club assignment not respecting capacity
- Scoreline compression producing too few large-margin games

### Acceptable or Expected Under Current Logic

- Player status distribution
- Gender distribution
- Region distribution
- Match-type mix
- Weekend scheduling share
- Match outcome calibration
- Rating stability and lack of extreme deltas
- No cross-region club flows when cross-region assignment is disabled

### Audit Artifacts or Config-Driven Effects

- `player_age_distribution` as currently implemented
- `rating_delta_by_confidence_band` when `confidence_increment_per_match = 0`

## Highest-Value Next Refinements

### 1. Fix the Age Audit

Highest value on the audit side.

- Replace the current age metric with age measured at the latest batch date, not at `registration_date`.
- Alternatively split into two queries:
  - `current_age_distribution`
  - `registration_age_distribution`

Why this matters:

- It removes the largest false positive in the audit pack.
- It aligns the metric with how player ages are actually intended to be modeled.

### 2. Implement Multi-Batch Player Inflow

Highest value on the generation side.

- Use `monthly_player_growth_rate` to create players in later batches.
- Stop concentrating all registrations in the first month.

Why this matters:

- It is a real realism gap.
- It affects population age, team continuity, rating evolution, and club dynamics.

### 3. Make Club Assignment Capacity-Aware

High value on the generation side.

- Prevent clubs from exceeding capacity, either as a hard limit or via a strong saturation penalty.
- Consider regional fallback logic for players in regions with no clubs.

Why this matters:

- It directly addresses both the over-capacity outlier and part of the unaffiliated drift.

### 4. Improve Club Coverage / Secondary Availability Logic

High value on the generation side.

- Add better handling for regions with zero clubs.
- Add better handling for regions with only one eligible club when multi-club assignment is targeted.

Why this matters:

- It explains a meaningful share of the current affiliation drift.
- It will make club-related audits more informative and less dominated by supply shortage artifacts.

### 5. Broaden the Score Generator

High value on the generation side.

- Increase variance in loser scores.
- Tie margin spread more strongly to matchup quality and match type.
- Preserve legal scorelines while allowing more realistic blowout frequency.

Why this matters:

- The current scoreline shape is too narrow.
- It is one of the clearest realism issues in live output.

### 6. Add Confidence-Specific Audit Coverage

Moderate value on the audit side.

- Add a query that reports confidence progression directly.
- Flag runs where confidence is effectively static because increment is zero.

Why this matters:

- It distinguishes configuration-driven behavior from rating-engine defects.

## Code References

- Current age audit SQL:
  - `backend/app/generation/realism_audit.py`
- First-batch-only player seeding:
  - `backend/app/generation/monthly_pipeline.py`
- Player birth date and registration date logic:
  - `backend/app/generators/players.py`
- Club assignment and club-capacity weighting:
  - `backend/app/generators/club_memberships.py`
- Score generation:
  - `backend/app/generators/games.py`
- Confidence increment handling:
  - `backend/app/generators/ratings.py`

## Recommended Immediate Next Move

If the goal is to improve signal quality first, fix `player_age_distribution` in the audit pack before changing generation logic.

If the goal is to improve simulation realism first, implement multi-batch player inflow and capacity-aware club assignment next.
