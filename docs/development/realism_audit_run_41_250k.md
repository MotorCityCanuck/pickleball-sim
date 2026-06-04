# Realism Audit Review: Run 41 250k Baseline

- Generation run: `41`
- Initial player load: `250,000`
- Historical months: `12`
- Audit target batch: `377` (`2024-12-01`)
- Audit executed at: `2026-06-04T12:29:47.107927+00:00`
- Query count: `41`
- Snapshot: [run_000041_batch_000377_2024-12-01_20260604T122947Z.json](/home/brett/projects/pickleball-sim/data/realism_audit_snapshots/generation_run_000041/run_000041_batch_000377_2024-12-01_20260604T122947Z.json)

## Overall Read

The dataset looks broadly healthy in geography, club integrity, match scheduling,
score calibration, and rating stability. The recent performance work does not
show signs of having broken the core match pipeline.

The main realism concerns are concentrated in four areas:

1. Age realism remains the largest issue. The audit reports a very large
   `under_18` cohort at `20.75%`, while the configured age targets start at
   `18_29`.
2. Club locality and saturation still look strained at this scale. Same-region
   secondary memberships are only `64.31%` against an `85.00%` target, and the
   average club fill ratio is `0.971`.
3. Team persistence is extremely high by December. `95.42%` of active rosters
   persist from the prior month, and `93.61%` of match-team appearances come
   from pairings with `6+` prior matches together.
4. Ratings remain numerically stable, but the rating spread slowly compresses
   over the year, with both the low and high tails shrinking.

## Strong Signals

- Player geography is very well aligned to configured regional weights. The
  worst visible regional drift in the top outliers is only about `0.07`
  percentage points.
- Name-distribution alignment looks healthy in aggregate:
  - first names: `99.06%` exact state-year alignment
  - `0.91%` country-year fallback across states
  - last names: `100.00%` exact state alignment
- Match generation remains broad and active:
  - `436,721` matches in the latest month
  - all `572` regions represented in latest-month matches
  - `31` unique match days in December
- Match-type mix is effectively exact to target.
- Weekend share is plausible at `44.58%`, inside the configured `40%` to `60%`
  band.
- Club integrity is strong:
  - `0` multi-primary-membership players
  - `0` over-capacity clubs
  - `0` zero-membership clubs
- Match constraints held:
  - `0` daily team match cap violations
- Outcome realism is healthy:
  - average game margin `4.456`
  - extended games `9.99%`
  - favorite-win calibration tracks predicted win probability well
- Rating deltas are well controlled:
  - average absolute delta `2.875`
  - max absolute delta `44.861`
  - `0` deltas above the configured warning threshold

## Run-Level Findings

### Population shape

- Total players: `311,538`
- Active players: `296,475` (`95.16%`)
- Unaffiliated players: `37,618` (`12.07%`, target `12.00%`)
- Multi-club players: `16,488` (`5.29%`, target `6.00%`)
- First-batch registrations: `250,000`
- Later-batch registrations: `61,538`

Interpretation:

- The run behaves as a `250k` initial load plus steady monthly growth.
- Status and gender distributions look normal.
- Unaffiliated rate is essentially on target.
- Multi-club participation is still slightly low but not severely so.

### Age realism

| Age bucket | Observed | Configured | Drift |
|---|---:|---:|---:|
| `under_18` | `20.75%` | n/a | n/a |
| `18_29` | `26.16%` | `26.0%` | `+0.16 pts` |
| `30_44` | `27.31%` | `34.0%` | `-6.69 pts` |
| `45_59` | `17.07%` | `24.0%` | `-6.93 pts` |
| `60_74` | `7.56%` | `13.0%` | `-5.44 pts` |
| `75_plus` | `1.15%` | `3.0%` | `-1.85 pts` |

Interpretation:

- This is the clearest realism problem in the run.
- The issue is no longer an oversized older tail. Instead, a large share of the
  population lands in `under_18`, which is outside the configured bucket set.
- That makes the adult buckets look low across the board, especially
  `30_44` through `60_74`.
- This likely reflects either:
  - intentional youth generation that is not represented in the config targets,
    or
  - a continuing mismatch between age-bucket semantics and realized birthdate
    generation.

### Name realism

- Distinct first names: `6,911`
- Distinct last names: `52,558`
- Distinct full names: `244,000`
- Largest shared full name count: `460` players (`0.15%`)

Interpretation:

- The preload optimization does not appear to have collapsed name diversity.
- Aggregate alignment is strong enough that there is no obvious geography-blind
  name assignment problem.
- The remaining gap is audit depth, not an observed failure:
  - the audit does not yet quantify placeholder or fallback-name usage directly
  - the audit does not yet show top repeated full names, only the maximum count

### Club membership realism

- Average memberships per affiliated player: `1.090`
- Valid primary-membership players: `273,920`
- Zero-primary players: `37,618`
- Average club fill ratio: `0.971`
- Max fill ratio: `1.000`
- Clubs at or near full capacity dominate the outlier list

Interpretation:

- Integrity is good, but realism pressure is high.
- The system is not violating capacity, but it is operating very close to the
  ceiling across the network.
- This is consistent with a club ecosystem that may be too tight for the player
  population at this scale.

### Club geography

- Same-region secondary memberships: `64.31%`
- Configured same-region secondary rate: `85.00%`
- Cross-region memberships: `66,309`
- Total memberships: `298,610`
- Secondary memberships: `24,690`

Interpretation:

- This remains a clear realism drift.
- Cross-region flow is materially higher than intended.
- The outlier flows are concentrated in large metros such as New York, Chicago,
  Orlando, Tampa, Los Angeles, Houston, and Toronto.
- That pattern reads more like network spillover than random noise, and it is
  consistent with the high club fill ratios.

## Latest Batch Findings (`2024-12-01`, batch `377`)

### Match volume and schedule

- Matches in batch: `436,721`
- Distinct match regions: `572`
- Unique match days: `31`
- Average matches per match day: `14,087.774`
- Weekend matches: `194,682` (`44.58%`)

Month-over-month view:

- Match volume rises smoothly from `246,915` in January to `436,721` in
  December.
- Regional coverage stays at `572` regions in every batch.
- There is no sign of a late-run collapse in regional participation.

Interpretation:

- The match generator is scaling up smoothly with the growing population.
- The `_active_teams()` refactor does not show evidence of a broad exclusion
  bug. If it had dropped large numbers of eligible teams, the strongest
  symptoms would have been a collapsing team-match distribution or regional
  coverage loss, and neither appears here.

### Team persistence and repeat partners

- Active rosters in December: `145,382`
- Persisted from prior month: `138,721` (`95.42%`)
- New rosters in December: `6,661`

Repeat-partner distribution in latest month:

| Prior shared-match bucket | Team share |
|---|---:|
| `0` | `4.47%` |
| `1_2` | `0.18%` |
| `3_5` | `1.73%` |
| `6_plus` | `93.61%` |

Interpretation:

- Partner continuity is extremely strong by year end.
- That may be directionally realistic for established leagues, ladders, and
  recurring social pairings, but this degree of stability is worth checking.
- This is the strongest current watch area for possible over-stickiness in team
  behavior, even though it does not by itself prove a bug.

### Team and player match participation

#### Teams

| Team match bucket | Share |
|---|---:|
| `0` | `0.41%` |
| `1` | `1.04%` |
| `2` | `3.05%` |
| `3_4` | `18.78%` |
| `5_plus` | `76.72%` |

#### Players

| Player match bucket | Share |
|---|---:|
| `0` | `2.33%` |
| `1_2` | `4.01%` |
| `3_4` | `18.42%` |
| `5_8` | `64.15%` |
| `9_plus` | `11.10%` |

Interpretation:

- The player distribution remains centered in the configured `5_8` bucket.
- The team distribution is also healthy enough that there is no broad sign of
  active teams failing to receive matches.

### Zero-match cohorts

#### By registration cohort

| Cohort | Active players | Zero-match players | Zero-match pct |
|---|---:|---:|---:|
| `initial_batch` | `234,937` | `3,283` | `1.40%` |
| `later_batch` | `61,538` | `3,616` | `5.88%` |

#### By team membership

| Team membership status | Active players | Zero-match players | Zero-match pct |
|---|---:|---:|---:|
| `teamed` | `290,764` | `1,188` | `0.41%` |
| `unteamed` | `5,711` | `5,711` | `100.00%` |

#### By club affiliation

| Club affiliation status | Active players | Zero-match players | Zero-match pct |
|---|---:|---:|---:|
| `affiliated` | `260,652` | `5,800` | `2.23%` |
| `unaffiliated` | `35,823` | `1,099` | `3.07%` |

Additional teaming signal:

- Average days to first team: `12.86`
- Still-unteamed active players: `2,825`
- Max unresolved unteamed duration: `335` days

Interpretation:

- There is no sign of a major teamed-player match starvation problem after the
  `_active_teams()` refactor. Only `0.41%` of teamed active players had zero
  matches in the audited month.
- The real issue is the persistent unteamed population. Active unteamed players
  are effectively excluded from match play by December.
- Later-batch players remain materially more likely to be zero-match than the
  initial cohort.

### Score realism

- Games in batch: `655,164`
- Average margin: `4.456`
- Extended games: `65,427` (`9.99%`)
- Upset rate: `38.43%`

Favorite-win calibration:

| Probability bucket | Avg predicted favorite win pct | Actual favorite win pct |
|---|---:|---:|
| `50_59` | `54.74%` | `55.10%` |
| `60_69` | `64.43%` | `64.93%` |
| `70_79` | `73.97%` | `74.49%` |
| `80_89` | `83.71%` | `83.97%` |
| `90_plus` | `91.24%` | `91.45%` |

Interpretation:

- Outcome calibration is very clean.
- The score model is producing believable competitiveness and favorite-win
  behavior at scale.

## Rating Drift and Spread Over Time

Year-long summary:

- Average rating rises only from `1507.883` in January to `1508.791` in
  December.
- Rating range narrows from `3933.670` to `3825.522`.
- Players below `1000` drop from `1,382` to `576`.
- Players at `2000+` drop from `2,063` to `1,438`.

Latest-month movement:

- Average absolute rating delta: `2.875`
- Max absolute rating delta: `44.861`
- `99.93%` of updates are under `25` rating points
- `0.07%` fall in the `25_49` bucket

Interpretation:

- There is no sign of rating instability or runaway drift.
- The system is gradually compressing the tails toward the middle rather than
  widening over time.
- That is not obviously wrong, but it is worth deciding whether this degree of
  tail compression is intended.

## Optimization-Focused Read

### Player preload and name/geography realism

- No evidence of a region-allocation regression.
- No evidence of a broad first-name or last-name realism collapse.
- The remaining concern is not visible failure, but audit granularity:
  fallback-name usage is still not measured directly.

### `_active_teams()` refactor and downstream realism

- No evidence of a major active-team exclusion bug:
  - teamed zero-match rate is only `0.41%`
  - team `0`-match bucket is only `0.41%`
  - regional match coverage stays full
  - match volume trends stay smooth across all 12 months
- The main watch item is behavioral, not operational:
  pairings appear very persistent, so team churn may now be lower than ideal.

## Coverage Gaps That Still Remain

- The audit still does not directly quantify placeholder or fallback name usage.
- The audit still does not separate first-time partnerships from long-lived
  league pairs by match type or club context.
- The audit still reports only one confidence band in rating movement, which
  suggests confidence progression is either static or not yet represented in a
  more informative way.

## Recommended Follow-Up

1. Treat the age distribution result as the top realism issue for this dataset.
   Confirm whether `under_18` is intended at this scale. If not, inspect the
   birthdate and age-bucketing semantics first.
2. Review club capacity scaling and locality behavior together. The combination
   of `0.971` average fill ratio and `64.31%` same-region secondary membership
   strongly suggests local club supply is too tight.
3. Review whether the observed team persistence is desired. `95%+` month-to-
   month roster persistence and `93.61%` `6_plus` repeat-partner share may be
   too sticky for a broad synthetic population.
4. Keep the recent performance optimizations. The audit does not show evidence
   that the player preload work or `_active_teams()` safety refactor caused a
   broad realism failure.
