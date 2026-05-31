# Realism Audit Review: Run 29 with Registration-Age Calculation

- Generation run: `29`
- Audit target batch: `314` (`2024-12-01`)
- New snapshot: [run_000029_batch_000314_2024-12-01_20260531T111635Z.json](/home/brett/projects/pickleball-sim/data/realism_audit_snapshots/generation_run_000029/run_000029_batch_000314_2024-12-01_20260531T111635Z.json)
- Prior snapshot using end-of-run age: [run_000029_batch_000314_2024-12-01_20260531T101137Z.json](/home/brett/projects/pickleball-sim/data/realism_audit_snapshots/generation_run_000029/run_000029_batch_000314_2024-12-01_20260531T101137Z.json)

## Scope

This audit uses the updated `player_age_distribution` logic that measures age at each player's `registration_date`, not at the end-of-run batch date.

Important constraint: this run still carries the old age-distribution config in its own parameter snapshot:

- `18_29`: `8%`
- `30_44`: `18%`
- `45_59`: `32%`
- `60_74`: `34%`
- `75_plus`: `8%`

Your new config change to `26%, 34%, 24%, 13%, 3%` will not show up until the next generation run.

## Overall Read

The updated calculation changes the age diagnosis substantially.

- The earlier `75_plus` inflation was mostly an artifact of measuring age at the end of the run.
- With age measured at registration, `75_plus` drops from `11.26%` to `3.15%`.
- The more important exposed issue is now an `under_18` cohort of `8.29%`, which is not represented in the configured age buckets.
- The distribution is also materially younger than the old run snapshot expected in the `60_74` and `75_plus` bands.

Outside the age query, the rest of the audit remains broadly healthy:

- status mix is close to target
- gender mix is effectively exact
- club integrity and capacity remain sound
- match-type mix and weekend share remain stable
- the zero-match unteamed cohort is still the clearest structural match-generation concern

## Age Distribution: New Calculation

| Age bucket | Observed | Configured in run 29 | Drift |
|---|---:|---:|---:|
| `under_18` | `8.29%` | n/a | n/a |
| `18_29` | `13.62%` | `8.0%` | `+5.62 pts` |
| `30_44` | `25.00%` | `18.0%` | `+7.00 pts` |
| `45_59` | `29.99%` | `32.0%` | `-2.01 pts` |
| `60_74` | `19.95%` | `34.0%` | `-14.05 pts` |
| `75_plus` | `3.15%` | `8.0%` | `-4.85 pts` |

Interpretation:

- The run is no longer reading as too old.
- It now reads as too young at registration time, with a large shortfall in `60_74` and `75_plus`.
- The `under_18` population is the biggest signal that the current birthdate/age-generation logic does not align cleanly with the configured bucket semantics.

## Comparison to the Old End-of-Run Calculation

| Age bucket | End-of-run age | Registration age | Change |
|---|---:|---:|---:|
| `18_29` | `7.14%` | `13.62%` | `+6.48 pts` |
| `30_44` | `17.11%` | `25.00%` | `+7.89 pts` |
| `45_59` | `30.54%` | `29.99%` | `-0.55 pts` |
| `60_74` | `33.95%` | `19.95%` | `-14.00 pts` |
| `75_plus` | `11.26%` | `3.15%` | `-8.11 pts` |
| `under_18` | `0.00%` | `8.29%` | `+8.29 pts` |

Interpretation:

- Measuring at the final batch date was pulling a large amount of mass upward into the older buckets.
- The corrected registration-age audit reveals a very different shape.
- The old audit overstated the `75_plus` problem and understated the amount of young-at-registration leakage.

## Implications for the Generator

The new audit is more faithful to your intended question, but it also exposes a real modeling issue:

- If age buckets are intended to represent age at registration, the generator currently produces too many players who land below the intended bucket floor when birth month/day is randomized.
- The largest example is `under_18`, which should not be this large if the configured age distribution starts at `18_29`.

This is consistent with the current birthdate algorithm:

- it derives birth year from `registration_year - sampled_age`
- then assigns a random birth month/day
- which can make the realized age at registration lower than the sampled bucket implied

That means the audit change was worth making. It is now showing the generator's true registration-age outcome instead of a later aged-forward outcome.

## Other Audit Findings That Still Matter

### Player and club shape

- Total players: `124,017`
- Active players: `117,901` (`95.07%`, configured `94%`)
- Unaffiliated players: `15,016` (`12.11%`, configured `12%`)
- Multi-club players: `6,528` (`5.26%`, configured `6%`)
- Multi-primary players: `0`

Interpretation: club integrity is still good and the overall roster shape remains plausible.

### Club geography

- Same-region secondary memberships: `78.33%`
- Configured same-region secondary rate in run 29: `85.00%`

Interpretation: secondary memberships still spread across regions more than configured.

### Match volume and scheduling

- Matches in audited batch: `173,269`
- Weekend share: `44.25%`
- Configured weekend band: `40%` to `60%`
- Match-type mix remains essentially exact to config

Interpretation: scheduling and activity shape remain stable at this scale.

### Zero-match cohorts

| Cohort | Active players | Zero-match players | Zero-match pct |
|---|---:|---:|---:|
| `initial_batch` | `93,884` | `1,325` | `1.41%` |
| `later_batch` | `24,017` | `1,382` | `5.75%` |

| Team status | Active players | Zero-match players | Zero-match pct |
|---|---:|---:|---:|
| `teamed` | `115,618` | `424` | `0.37%` |
| `unteamed` | `2,283` | `2,283` | `100.00%` |

Interpretation: the unteamed cohort is still acting like a hard no-match bucket in the audited month.

### Rating stability

- Player rating updates in batch: `693,076`
- Average absolute rating delta: `2.791`
- Max absolute rating delta: `42.182`
- Large-delta count over warning threshold: `0`

Interpretation: ratings still look stable.

## Practical Takeaway Before the Next Run

The new audit calculation is an improvement. It answers the correct question.

What it says about run 29:

1. The earlier old-age skew was overstated by the end-of-run audit method.
2. The current generator likely leaks a meaningful number of players below their intended registration-age bucket.
3. Your new config should help correct the oversized older buckets on the next run, but it will not by itself fix the exposed `under_18` leakage if the birthdate algorithm stays unchanged.

## Recommended Next Step

Run the next batch with the new age-distribution config and then re-run this updated realism audit.

What to watch first in that next audit:

1. whether `under_18` remains materially above zero
2. whether `60_74` and `75_plus` move closer to your new targets
3. whether `18_29` and `30_44` align better once the config shift is in effect

