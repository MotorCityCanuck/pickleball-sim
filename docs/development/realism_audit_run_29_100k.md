# Realism Audit Review: Run 29 100k Baseline

- Generation run: `29`
- Run window: `2026-05-31 01:05:18` to `2026-05-31 02:43:46` America/Toronto
- Audit target batch: `314` (`2024-12-01`)
- Snapshot: [run_000029_batch_000314_2024-12-01_20260531T101137Z.json](/home/brett/projects/pickleball-sim/data/realism_audit_snapshots/generation_run_000029/run_000029_batch_000314_2024-12-01_20260531T101137Z.json)

## Overall Read

The 100k-player stress run looks broadly healthy from a realism perspective. The strongest signals are:

- Match-type mix, day-of-week mix, weekend share, rating-delta behavior, and favorite-win calibration all look stable.
- Club capacity constraints held: `0` over-capacity clubs and `0` multi-primary-membership players.
- The main drift worth investigating is age skew at `75_plus`, which landed at `11.26%` versus the configured `8.0%`.
- Secondary club geography also drifted: same-region secondary memberships were `78.33%` versus a configured `85.00%`.
- A small but notable cohort of active unteamed players had zero matches in the audited month: `2,283`.

## Generation-Run Findings

### Player and registration shape

- Total players in run: `124,017`
- Active players: `117,901` (`95.07%`, configured `94%`)
- Unaffiliated players: `15,016` (`12.11%`, configured `12.00%`)
- Multi-club players: `6,528` (`5.26%`, configured `6.00%`)
- Initial registrations in first batch: `100,000`
- Registrations added across later batches: `24,017`

Interpretation:

- The run is behaving as a `100k initial load` plus monthly growth, not a fixed final population of 100k.
- Status distribution is close to target. Active is slightly high, while injured, retired, and inactive are each slightly low.

### Gender distribution

| Gender | Observed | Configured | Drift |
|---|---:|---:|---:|
| `M` | `50.12%` | `50.0%` | `+0.12 pts` |
| `F` | `49.88%` | `50.0%` | `-0.12 pts` |

Interpretation: effectively on target.

### Age distribution

| Age bucket | Observed | Configured | Drift |
|---|---:|---:|---:|
| `18_29` | `7.14%` | `8.0%` | `-0.86 pts` |
| `30_44` | `17.11%` | `18.0%` | `-0.89 pts` |
| `45_59` | `30.54%` | `32.0%` | `-1.46 pts` |
| `60_74` | `33.95%` | `34.0%` | `-0.05 pts` |
| `75_plus` | `11.26%` | `8.0%` | `+3.26 pts` |

Interpretation:

- The distribution is shifted older than intended.
- The excess is concentrated in `75_plus`, not spread evenly across the upper bands.
- This is the clearest realism drift in the run-level output.

### Initial rating distribution

- Average initial rating: `1507.415`
- Min initial rating: `662.662`
- Max initial rating: `4497.174`
- Elite ratings (`>= 4000`): `333` players (`0.27%`)
- Ratings `>= 2000`: `1,078`
- Ratings `< 1000`: `779`

Interpretation:

- Nothing here looks obviously pathological.
- Elite tail behavior appears modest and controlled.

### Club membership and capacity

- Average memberships per affiliated player: `1.090`
- Zero-primary-membership players: `15,016`
- Valid primary-membership players: `109,001`
- Multi-primary-membership players: `0`
- Clubs tracked with capacity: `4,000`
- Over-capacity clubs: `0`
- Zero-membership clubs: `3`
- Average club fill ratio: `0.423`
- Max club fill ratio: `1.000`

Interpretation:

- Primary-membership integrity is good.
- Capacity enforcement is holding.
- The club system is not showing obvious saturation stress at this scale.

### Club geography

- Secondary memberships in same region: `78.33%`
- Configured same-region secondary rate: `85.00%`
- Cross-region memberships: `7,593`
- Total memberships: `118,783`

Interpretation:

- Cross-region behavior is somewhat higher than the config implies.
- The largest cross-region flows in the top outliers were dominated by players from `San Juan-Bayamón-Caguas` mapping into large mainland metros.
- This may indicate a fallback or sparse-local-capacity behavior that is too permissive for some regions.

## Latest Batch Findings (`2024-12-01`, batch `314`)

### Match volume and schedule

- Matches in batch: `173,269`
- Distinct match regions: `572`
- Unique match days: `31`
- Average matches per match day: `5,589.323`
- Weekend matches: `76,669` (`44.25%`)
- Configured weekend range: `40%` to `60%`
- Outside configured range flag: `0`

Interpretation:

- Scheduling remains within the configured weekend concentration band even at 100k scale.
- Regional spread is broad rather than collapsing into a small number of metros.

### Match type mix

| Match type | Observed | Configured | Drift |
|---|---:|---:|---:|
| `clinic` | `0.99%` | `1.0%` | `-0.01 pts` |
| `ladder` | `9.95%` | `10.0%` | `-0.05 pts` |
| `league` | `19.98%` | `20.0%` | `-0.02 pts` |
| `challenge` | `3.96%` | `4.0%` | `-0.04 pts` |
| `tournament` | `10.01%` | `10.0%` | `+0.01 pts` |
| `recreational` | `55.11%` | `55.0%` | `+0.11 pts` |

Interpretation: match-type allocation is effectively exact.

### Day-of-week mix

| Day | Share |
|---|---:|
| Sunday | `22.45%` |
| Saturday | `21.80%` |
| Monday | `12.10%` |
| Tuesday | `12.26%` |
| Wednesday | `9.77%` |
| Thursday | `9.80%` |
| Friday | `11.84%` |

Interpretation:

- Saturday and Sunday dominate as expected.
- Weekday distribution looks plausible and not unnaturally flat.

### Team and player match participation

#### Teams

| Team match bucket | Share |
|---|---:|
| `0` | `0.37%` |
| `1` | `1.11%` |
| `2` | `3.03%` |
| `3_4` | `19.02%` |
| `5_plus` | `76.48%` |

#### Players

| Player match bucket | Share |
|---|---:|
| `0` | `2.30%` |
| `1_2` | `4.06%` |
| `3_4` | `18.65%` |
| `5_8` | `64.16%` |
| `9_plus` | `10.84%` |

Interpretation:

- The player distribution centers where the config suggests it should: most players are in `5_8`.
- A `2.30%` zero-match share among active players is not alarming by itself, but the cohort breakdown matters.

### Zero-match cohorts

#### By registration cohort

| Cohort | Active players | Zero-match players | Zero-match pct |
|---|---:|---:|---:|
| `initial_batch` | `93,884` | `1,325` | `1.41%` |
| `later_batch` | `24,017` | `1,382` | `5.75%` |

#### By team membership

| Team membership status | Active players | Zero-match players | Zero-match pct |
|---|---:|---:|---:|
| `teamed` | `115,618` | `424` | `0.37%` |
| `unteamed` | `2,283` | `2,283` | `100.00%` |

#### By club affiliation

| Club affiliation status | Active players | Zero-match players | Zero-match pct |
|---|---:|---:|---:|
| `affiliated` | `103,597` | `2,269` | `2.19%` |
| `unaffiliated` | `14,304` | `438` | `3.06%` |

Interpretation:

- Later-batch players are substantially more likely to have zero matches than initial-batch players.
- The unteamed cohort is the sharpest issue: all `2,283` active unteamed players had zero matches in the audited month.
- That suggests team membership is acting as an almost hard gate for match generation by December, which is worth validating against intended behavior.

### Constraint checks

- Daily team match cap violations: `0`

Interpretation: the per-team daily cap is being respected.

## Score and Outcome Realism

### Game competitiveness

- Games in batch: `259,814`
- Average margin: `4.318`
- Extended games: `25,909` (`9.97%`)

### Margin distribution

| Margin bucket | Share |
|---|---:|
| `0_2` | `28.07%` |
| `3_5` | `43.87%` |
| `6_8` | `24.42%` |
| `9_plus` | `3.64%` |

Interpretation:

- Most games land in the moderate-competition bands.
- Blowout frequency is low enough to look plausible.

### Upsets and prediction calibration

- Average predicted favorite win probability: `0.6049`
- Upset rate: `39.09%`

Favorite win rate by bucket:

| Bucket | Avg predicted | Observed favorite win pct | Match count |
|---|---:|---:|---:|
| `50_59` | `0.5466` | `55.02%` | `96,853` |
| `60_69` | `0.6433` | `64.83%` | `54,361` |
| `70_79` | `0.7420` | `74.58%` | `16,504` |
| `80_89` | `0.8373` | `84.57%` | `5,380` |
| `90_plus` | `0.9086` | `86.55%` | `171` |

Interpretation:

- Calibration is very good through the dense buckets.
- The `90_plus` bucket is slightly under target, but the sample size is tiny.

## Rating Movement Realism

- Player rating updates in audited batch: `693,076`
- Average absolute rating delta: `2.791`
- Max absolute rating delta: `42.182`
- Warning threshold: `300.0`
- Large deltas `>= 300`: `0`

Distribution:

| Delta bucket | Share |
|---|---:|
| `under_25` | `99.93%` |
| `25_49` | `0.07%` |

Confidence bands:

- All audited updates landed in the `0_24` confidence band.

Interpretation:

- Rating movement is tightly controlled and not producing explosive updates.
- No threshold violations occurred.
- The single-band confidence result is a little surprising and may be worth checking if the confidence model is intentionally that sticky by December.

## Main Concerns To Review

1. Age skew into `75_plus`
   - Observed `11.26%` vs configured `8.0%`
   - This is the largest clean drift in the run-level summary.

2. Same-region secondary membership drift
   - Observed `78.33%` vs configured `85.0%`
   - Cross-region secondary behavior appears too common.

3. Active unteamed players getting no matches
   - `2,283` active unteamed players
   - `2,283` zero-match players in that cohort
   - This looks more structural than random.

4. Confidence-band concentration
   - All rating updates were in `0_24`
   - This may be valid, but it deserves a quick sanity check.

## Main Signals That Look Good

- Match-type distribution is extremely close to configured weights.
- Weekend share is inside the configured range.
- No club is over capacity.
- No player has multiple primary club memberships.
- No daily team match cap violations were reported.
- Favorite-win calibration looks strong.
- Rating deltas are small and well bounded.

## Recommended Next Checks

1. Inspect player age generation and name/age assignment logic for why `75_plus` is overrepresented.
2. Inspect club-assignment geography, especially fallback behavior for sparse regions and cross-region secondary memberships.
3. Inspect match eligibility for active unteamed players in late batches to confirm whether they are intentionally excluded.
4. Inspect confidence-score progression to confirm whether the single-band outcome is expected or a modeling bug.
