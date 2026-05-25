# Realism Audit Assessment

Date: 2026-05-25

## Scope

- Repository: `/home/brett/projects/pickleball-sim`
- Audit wrapper: `./scripts/run_realism_audits.sh`
- Audit mode: latest auditable generation run only, latest batch within that run only
- Live dataset resolved by the rerun:
  - `generation_run_id = 3`
  - `batch_id = 36`
  - `batch_month = 2024-12-01`
  - `batch_created_at = 2026-05-21 12:51:32.527847`
- Fresh JSON output captured to:
  - `/tmp/realism_audit_2026_05_25.json`
  - `data/realism_audit_snapshots/generation_run_000003/run_000003_batch_000036_2024-12-01_20260525T181551Z.json`
- Audit runner note:
  - The newest `generation_runs` row is `generation_run_id = 4`, created on `2026-05-22`, but it has `0` monthly batches.
  - The audit resolver was updated to target the latest auditable run rather than the newest run row.

## High-Level Read

The live audit is healthy on status mix, gender mix, regional allocation, match mix, weekend scheduling, outcome calibration, and rating stability.

The main unacceptable findings are unchanged in substance: player registrations are still concentrated in the first batch, club affiliation still drifts because of coverage and capacity constraints, and scorelines are still too compressed. The age query is no longer using `registration_date`; it now measures current age from `birth_date` and the batch creation date, which changes how that result should be interpreted.

## Unacceptable Audit Results

### `player_roster_summary`

- Result:
  - `player_count = 25000`
  - `active_player_count = 23521`
  - `unaffiliated_player_count = 3698`
  - `unaffiliated_player_pct = 14.79`
  - `multi_club_player_count = 1234`
- Why it is unacceptable:
  - The topline player count is fine.
  - The affiliation metrics are not. They are materially shaped by club supply gaps and club assignment behavior.

### `player_registration_by_batch`

- Result:
  - `2024-01-01 = 25000 registrations`
  - all later batches = `0 registrations`
- Why it is unacceptable:
  - The full player population is still seeded in the first batch.
  - Monthly player inflow realism is not being modeled.

### `club_membership_summary`

- Result:
  - `unaffiliated_player_pct = 14.79%` vs config `12.00%`
  - `multi_club_player_pct = 4.94%` vs config `6.00%`
  - `avg_memberships_per_affiliated_player = 1.085`
  - supporting coverage diagnostics:
    - `712` players live in regions with no clubs
    - `1,534` players live in regions with fewer than two clubs
- Why it is unacceptable:
  - The drift is too large to treat as noise.
  - Regional club scarcity is pushing unaffiliated rates up and multi-club rates down.

### `club_fill_ratio_summary`

- Result:
  - `avg_fill_ratio = 0.085`
  - `max_fill_ratio = 1.333`
  - `over_capacity_club_count = 1`
  - `zero_membership_club_count = 405`
- Why it is unacceptable:
  - At least one club exceeds capacity.
  - The selector is still not respecting capacity as a hard constraint.

### `club_fill_ratio_outliers`

- Result:
  - `Victory Pickleball Club`
  - `member_capacity = 18`
  - `membership_count = 24`
  - `fill_ratio = 1.333`
- Why it is unacceptable:
  - This is a direct overflow case, not just a soft imbalance.

### `game_competitiveness_summary`

- Result:
  - `avg_margin = 3.442`
  - `extended_game_pct = 10.10%`
- Why it is unacceptable:
  - Scorelines are still too compressed overall.
  - Extended games occur, but the broader outcome spread is unrealistically narrow.

### `game_margin_distribution`

- Result:
  - `0_2 = 27.07%`
  - `3_5 = 67.50%`
  - `6_8 = 5.42%`
  - `9_plus = 0.01%`
- Why it is unacceptable:
  - Nearly all games still fall in the `0` to `5` margin range.
  - Blowouts are almost nonexistent.

## Acceptable Audit Results

### `player_status_distribution`

- Result:
  - `ACTIVE = 94.08%` vs config `94.00%`
  - `INJURED = 1.95%` vs config `2.00%`
  - `RETIRED = 2.11%` vs config `2.00%`
  - `INACTIVE = 1.86%` vs config `2.00%`
- Why it is acceptable:
  - All drifts are within `0.14` percentage points.

### `player_gender_distribution`

- Result:
  - `M = 50.24%`
  - `F = 49.76%`
- Why it is acceptable:
  - This is effectively on target.

### `player_age_distribution`

- Result:
  - `18_29 = 7.12%` vs config `8.00%`
  - `30_44 = 17.30%` vs config `18.00%`
  - `45_59 = 30.89%` vs config `32.00%`
  - `60_74 = 33.44%` vs config `34.00%`
  - `75_plus = 11.25%` vs config `8.00%`
- Why it is acceptable:
  - The query now uses current age from `birth_date` and `batch_created_at`, which is the requested behavior.
  - Because the batch was created on `2026-05-21` for a simulated batch month of `2024-12-01`, the population has aged materially since the simulated month.
  - That makes direct comparison to intake-age configuration less exact, but the result is a valid current-age snapshot.

### `player_region_distribution`

- Result:
  - Top regions remain close to configured selection weights.
- Why it is acceptable:
  - Regional allocation still tracks the configured probability model well.

### `initial_rating_distribution_summary`

- Result:
  - `avg_initial_rating = 1507.941`
  - `min_initial_rating = 688.232`
  - `max_initial_rating = 4499.801`
  - `elite_rating_count = 71`
  - `elite_rating_pct = 0.28%`
- Why it is acceptable:
  - The initial distribution still looks consistent with the configured mean and elite tail.

### `club_primary_membership_integrity`

- Result:
  - `multi_primary_player_count = 0`
  - `zero_primary_player_count = 3698`
- Why it is acceptable:
  - No primary-membership corruption is visible.

### `club_membership_geography`

- Result:
  - `same_region_secondary_pct = 100.00%`
  - `cross_region_membership_count = 0`
- Why it is acceptable:
  - This matches the run snapshot because cross-region assignment is disabled.

### `cross_region_membership_flows`

- Result:
  - no rows
- Why it is acceptable:
  - Also expected with cross-region assignment disabled.

### `match_volume_summary`

- Result:
  - `match_count = 16464`
  - `unique_match_days = 31`
  - `distinct_match_regions = 510`
  - `avg_matches_per_match_day = 531.097`
- Why it is acceptable:
  - Nothing obviously implausible appears in the batch topline.

### `match_type_distribution`

- Result:
  - All match types are within `0.27` percentage points of config.
- Why it is acceptable:
  - The type sampler is behaving as intended.

### `match_day_of_week_distribution`

- Result:
  - `Saturday = 21.74%`
  - `Sunday = 22.49%`
  - combined weekend = `44.24%`
- Why it is acceptable:
  - Weekend emphasis is present without breaching configured bounds.

### `weekend_match_share`

- Result:
  - `weekend_match_pct = 44.24%`
  - configured allowed range = `40.00%` to `60.00%`
- Why it is acceptable:
  - The batch remains inside the configured validation range.

### `matches_per_team_distribution`

- Result:
  - `0 = 1.91%`
  - `1 = 7.56%`
  - `2 = 14.60%`
  - `3_4 = 38.80%`
  - `5_plus = 37.14%`
- Why it is acceptable:
  - No clear realism failure is visible from this bucketization alone.

### `daily_team_match_cap_violations`

- Result:
  - no rows
- Why it is acceptable:
  - The same-day cap is not being violated.

### `batch_region_match_distribution`

- Result:
  - Region concentration broadly tracks player concentration.
- Why it is acceptable:
  - No obvious regional overconcentration problem is visible.

### `upset_rate_summary`

- Result:
  - `upset_match_pct = 41.34%`
  - `avg_predicted_win_probability = 0.5870`
- Why it is acceptable:
  - This is directionally reasonable given the modest average favorite edge.

### `predicted_vs_actual_outcome_buckets`

- Result:
  - `50_59`: favorite won `54.42%`
  - `60_69`: favorite won `62.91%`
  - `70_79`: favorite won `75.97%`
  - `80_89`: favorite won `86.64%`
  - `90_plus`: favorite won `100.00%` on only `10` matches
- Why it is acceptable:
  - Calibration improves monotonically by bucket.

### `rating_delta_summary`

- Result:
  - `avg_abs_rating_delta = 2.167`
  - `max_abs_rating_delta = 16.409`
  - `large_delta_count = 0`
- Why it is acceptable:
  - No runaway rating-movement problem is visible.

### `rating_delta_distribution`

- Result:
  - `under_25 = 100.00%`
- Why it is acceptable:
  - This is conservative, but not broken.

### `rating_outlier_players`

- Result:
  - largest observed absolute delta = `16.409`
- Why it is acceptable:
  - Outlier swings remain modest.

## Config-Driven or Interpretation-Sensitive Results

### `rating_delta_by_confidence_band`

- Result:
  - all rows fall into confidence band `0_24`
- Interpretation:
  - The latest generation run snapshot still has `confidence_increment_per_match = 0`.
  - The query is working, but the output is dominated by a configuration choice rather than a rating-engine defect.

## Highest-Value Next Refinements

### 1. Implement Multi-Batch Player Inflow

- Use `monthly_player_growth_rate` to create players in later batches.
- Stop concentrating all registrations in the first month.

### 2. Make Club Assignment Capacity-Aware

- Prevent clubs from exceeding capacity, either as a hard limit or via a strong saturation penalty.
- Add regional fallback behavior when players have no viable club supply.

### 3. Improve Club Coverage and Secondary Availability Logic

- Add better handling for regions with zero clubs.
- Add better handling for regions with only one eligible club when multi-club assignment is targeted.

### 4. Broaden the Score Generator

- Increase variance in loser scores.
- Tie margin spread more strongly to matchup quality and match type.
- Preserve legal scorelines while allowing more realistic blowout frequency.

### 5. Split Current-Age and Registration-Age Reporting

- Keep the current-age metric tied to `birth_date` and batch creation date.
- Add a separate registration-age view if configuration validation still needs intake-age comparison.

### 6. Add Confidence-Specific Audit Coverage

- Add a query that reports confidence progression directly.
- Flag runs where confidence is effectively static because increment is zero.

## Code References

- Audit scope resolution and age audit SQL:
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
