# Realism Audit Findings

Date: 2026-05-29

## Source

- Assessment document: `docs/generation_logic/REALISM_AUDIT_ASSESSMENT_2026-05-29.md`
- JSON snapshot: `backend/data/realism_audit_snapshots/generation_run_000015/run_000015_batch_000146_2024-12-01_20260529T164737Z.json`
- Audit execution timestamp: `2026-05-29T16:47:37.855644+00:00`
- Audit scope:
  - `generation_run_id = 15`
  - `batch_id = 146`
  - `batch_month = 2024-12-01`
  - `query_count = 32`

## Dataset Scale

- Total players: `313,277`
- Active players: `298,102`
- Latest-month matches: `438,258`
- Latest-month games: `657,370`
- Latest-month rating updates: `1,753,032`
- Distinct match regions in latest month: `572`

## Strong Findings

- Player gender distribution is effectively balanced: `50.09%` male and
  `49.91%` female.
- Player region allocation remains close to configured regional weights, even
  at 313k-player scale.
- Monthly player growth is present across all 12 batches. The run starts with
  `250,000` registrations and continues with monthly inflow through December.
- Club membership integrity is strong:
  - `0` multi-primary membership violations
  - `0` over-capacity clubs
  - `0` zero-membership clubs
- Match type distribution is very close to configured targets:
  - recreational: `54.99%` vs `55.00%`
  - league: `19.87%` vs `20.00%`
  - ladder: `10.15%` vs `10.00%`
  - tournament: `9.99%` vs `10.00%`
  - challenge: `3.99%` vs `4.00%`
  - clinic: `1.01%` vs `1.00%`
- Weekend match share is healthy at `44.45%`, inside the configured `40.00%`
  to `60.00%` range.
- Daily team match cap audit returned no violations.
- Predicted win probabilities are well calibrated to actual outcomes across
  probability buckets.
- Rating movement is stable:
  - average absolute rating delta: `2.811`
  - maximum absolute rating delta: `42.869`
  - large rating deltas above configured warning threshold: `0`

## Watch Items

- The `75_plus` age bucket remains high:
  - observed: `11.24%`
  - configured: `8.00%`
  - drift: `+3.24` percentage points
- Club utilization may be too saturated at this scale:
  - average fill ratio: `0.973`
  - maximum fill ratio: `1.000`
  - all `4,000` clubs have tracked capacity
  - no clubs exceed capacity, but many are exactly full
- Same-region secondary membership is well below target:
  - observed: `64.95%`
  - configured: `85.00%`
  - cross-region membership count: `66,653`
- Multi-club participation remains slightly low:
  - observed: `5.26%`
  - configured: `6.00%`
- Rating confidence appears static:
  - all `1,753,032` player rating updates remain in confidence band `0_24`

## Interpretation

The dataset is realistic enough to serve as a strong baseline for
student-facing export development. The core distributions, score behavior,
match mix, regional allocation, rating stability, and integrity checks are
healthy at the largest scale tested so far.

The main realism concerns are concentrated in a small set of areas:

1. Age distribution has a persistent older-tail skew.
2. Club capacity and supply may be too tight for 250k+ initial player scale.
3. Club geography allows more cross-region membership than the current target.
4. Rating confidence progression is either intentionally static or not yet
   operating as a dynamic metric.

## Recommended Follow-Up

1. Investigate the `75_plus` age skew in player generation and audit
   interpretation.
2. Review club supply/capacity scaling rules for large initial populations.
3. Check whether cross-region membership is being driven by saturated local
   club capacity.
4. Decide whether confidence should progress with match history; if static
   confidence is intentional, update audit wording to label it explicitly.
5. Continue prioritizing match-stage runtime optimization, because latest-month
   match volume confirms why generation runtime grows sharply across months.

