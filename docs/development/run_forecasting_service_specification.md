# Run Forecasting Service Specification

## Status

Proposed specification for review.

## Purpose

This document defines a forecasting service that estimates projected run size
and workload metrics from a configuration payload before a generation run is
started.

The service should answer a practical operator question:

```text
If I launch this configuration, what should the final dataset roughly look like?
```

The first version should focus on end-of-run estimates for the latest monthly
batch and should be suitable for later integration into the control panel UI.

The service is intended to provide fast, deterministic, read-only estimates.
It should not execute any generation modules, create any database rows, or
require a background job.

---

# Recommended Product Position

## Primary Output

The most useful first output is a forecast for the final monthly batch after
the configured historical sequence has completed.

This should estimate:

- projected total players
- projected active players
- projected active teams
- projected matches in the final batch
- projected games in the final batch

Optional secondary outputs can include:

- projected cumulative players registered across all batches
- projected cumulative matches across all batches
- projected cumulative games across all batches
- per-batch forecast rows for all configured months

## Why Final-Batch Forecasting Comes First

This is the best first implementation because it:

- aligns with how realism audits currently inspect the latest batch
- gives operators an intuitive sense of final dataset scale
- is more useful than only showing initial configured player count
- helps catch obviously too-small or too-large workloads before launch
- supports future UI display with low latency

---

# Non-Goals For Initial Version

The first version should NOT:

- run real generation logic against the database
- persist forecast results to database tables
- guarantee exact row counts
- simulate full match-level or player-level stochastic output
- incorporate every downstream realism nuance
- block run launch
- replace post-run metrics or realism audits

The service should be descriptive and operational, not authoritative.

---

# Scope

## In Scope

The first version should support:

- read-only forecast generation from a configuration payload
- direct use from Python service code
- optional later use from a control-panel route
- deterministic estimates derived from the payload and current generator rules
- final-batch estimates
- optional batch-by-batch estimate tables
- explicit caveat messaging when outputs are approximate

## Out Of Scope For Initial Version

The first version does not need:

- historical trend forecasting across multiple different configs
- Monte Carlo simulation
- confidence intervals
- graph rendering
- async job execution
- persistence of forecast snapshots
- run-to-run comparative analytics

---

# Design Principles

The forecasting service should follow these rules:

- Be fast enough to run inline during UI interactions.
- Be deterministic for the same input payload.
- Use generator-aligned formulas, not arbitrary heuristics.
- Prefer transparent formulas over black-box prediction.
- Surface assumptions explicitly in the output.
- Distinguish tightly estimated values from loosely estimated values.
- Favor end-of-run operational usefulness over theoretical completeness.

---

# Current Generator Alignment

The service should mirror the current live generator behavior closely enough to
be operationally useful.

Relevant current behaviors:

- Initial player population is driven by `player_generation.player_count`.
- Later monthly player additions are driven by
  `player_generation.monthly_player_growth_rate` plus seeded noise.
- Team formation coverage is driven primarily by
  `team_formation.player_team_participation_rate`.
- Match volume is currently team-driven via
  `match_scheduling.matches_per_team_per_month`.
- Games are driven by match-type mix and `games_and_scores.games_per_match`.

The service should document where it is exact to current logic and where it is
only approximate.

---

# Forecast Targets

## Required Final-Batch Metrics

The first version should return:

- `projected_total_players_final_batch`
- `projected_active_players_final_batch`
- `projected_active_teams_final_batch`
- `projected_matches_final_batch`
- `projected_games_final_batch`

## Recommended Secondary Metrics

The service should also be designed to support:

- `projected_player_registrations_cumulative`
- `projected_matches_cumulative`
- `projected_games_cumulative`
- `projected_batches`

Where `projected_batches` is a list of per-month forecast rows.

---

# Inputs

## Primary Inputs

The service should accept:

- full validated configuration payload

## Optional Inputs

The service may also accept:

- explicit seed override
- a flag for whether to produce only final-batch outputs or full batch table
- a flag for whether to include explanatory assumptions

## Required Configuration Fields

The first version depends most directly on:

- `simulation.historical_batch_count`
- `player_generation.player_count`
- `player_generation.monthly_player_growth_rate`
- `player_generation.player_status_weights`
- `team_formation.player_team_participation_rate`
- `match_scheduling.matches_per_team_per_month`
- `match_types.weights`
- `games_and_scores.games_per_match`

## Seed Handling

The service should use the configured master seed where a seeded deterministic
formula is already part of live generation logic and can be mirrored cheaply.

If exact seeded replay is not practical for a specific metric, the service
should use the expected-value approximation and mark that metric accordingly.

---

# Outputs

## Suggested Service Return Shape

Recommended return model:

```text
RunForecast
- summary
- projected_batches
- assumptions
- caveats
```

Recommended summary fields:

```text
summary
- projected_total_players_final_batch
- projected_active_players_final_batch
- projected_active_teams_final_batch
- projected_matches_final_batch
- projected_games_final_batch
- projected_matches_cumulative
- projected_games_cumulative
```

Recommended per-batch row:

```text
ProjectedBatchForecast
- batch_sequence
- batch_month
- projected_new_players
- projected_total_players
- projected_active_players
- projected_active_teams
- projected_matches
- projected_games
```

Recommended explanatory fields:

- `assumptions`
- `caveats`
- `formula_version`

---

# Forecast Methodology

## 1. Player Forecast

### Initial Batch

Projected initial players should be:

```text
player_generation.player_count
```

### Later Batches

Projected monthly player additions should be based on current generator logic:

```text
new_players_n ≈ prior_total_players * monthly_player_growth_rate
```

with optional deterministic seeded noise if the implementation mirrors the
current `_incremental_player_count` logic exactly.

### Final Total Players

Projected final total players should be the recursively accumulated total after
all configured batches.

## 2. Active Player Forecast

The first version should estimate active-player counts using configured status
weights rather than trying to perfectly simulate transition logic.

Recommended first approximation:

```text
projected_active_players ≈ projected_total_players * active_status_weight
```

where `active_status_weight` comes from:

- `player_generation.player_status_weights.active`

### Important Caveat

This is only an approximation because live month-to-month player status evolves
through generation logic and does not stay perfectly locked to initial weights.

The output should clearly label this as an estimate.

## 3. Active Team Forecast

The first version should estimate active teams from active-player coverage.

Recommended baseline approximation:

```text
covered_players ≈ projected_active_players * player_team_participation_rate
projected_active_teams ≈ covered_players / 2
```

If future versions incorporate monthly dissolution and reactivation behavior,
the model can be refined. The first version does not need to simulate full team
lifecycle churn as long as it states the simplification.

## 4. Match Forecast

The match generator is currently team-driven.

Recommended baseline approximation:

```text
projected_matches_final_batch ≈ projected_active_teams * matches_per_team_per_month / 2
```

This reflects that each match consumes two teams.

If the implementation later mirrors the seeded team-target sampling logic, that
can improve realism, but expected-value estimation is sufficient for V1.

## 5. Game Forecast

Projected games should be derived from projected match count and match-type
weights.

Recommended approximation:

```text
projected_games = Σ(projected_match_count_for_type * configured_games_per_match_for_type)
```

Where:

- match-type proportions come from `match_types.weights`
- game counts come from `games_and_scores.games_per_match`

If a match type is not configured explicitly, the service should follow the same
fallback behavior as the live game generator.

---

# Determinism Rules

The service should be deterministic for the same payload.

Two acceptable V1 approaches:

## Option A: Expected-Value Only

- No sampling
- No random draws
- Use closed-form approximations only

This is the simplest and safest first implementation.

## Option B: Seed-Aligned Lightweight Forecast

- Reuse deterministic seeded formulas for player growth where cheap
- Still avoid full row generation

This can more closely mirror current code, but it is not required for V1.

## Recommendation

Start with Option A unless exact alignment with current seeded growth counts is
required by product expectations.

---

# Caveat Model

The service should attach explicit caveats to forecast outputs.

At minimum, caveats should cover:

- player status is estimated from configured weights, not full transition logic
- team lifecycle is approximated unless a future version models churn explicitly
- match counts are team-volume estimates, not exact sampled outputs
- final real counts may differ because generation logic includes randomness and
  downstream constraints

This messaging is important for UI use so operators do not mistake the forecast
for a promise.

---

# Service Interface

## Recommended Python API

Suggested module:

```text
app/generation/run_forecasting.py
```

Suggested service class:

```text
RunForecastService
```

Suggested entrypoint:

```python
forecast = RunForecastService().forecast_from_payload(payload)
```

Optional later entrypoints:

```python
forecast = RunForecastService().forecast_from_profile_version(profile_version_id)
forecast = RunForecastService().forecast_from_generation_run(run_id)
```

## Suggested Return Types

Use typed dataclasses or Pydantic models for:

- `RunForecast`
- `RunForecastSummary`
- `ProjectedBatchForecast`

---

# UI Integration Guidance

The service should be designed so the control panel can call it synchronously.

## Recommended UI Placement

This belongs naturally in the Workload Orchestration area and optionally in the
configuration editing workflow.

Good first UI placements:

- read-only forecast card beside launch controls
- pre-launch confirmation panel
- optional “Preview estimated workload” action

## Recommended UI Labels

Use explicit estimate framing:

- Projected final-batch players
- Projected final-batch active teams
- Projected final-batch matches
- Projected final-batch games
- Estimated from current configuration

## Avoid In UI

Do not present the values as exact row counts.

Do not hide the assumptions or caveat messaging.

---

# Error Handling

The service should fail clearly when required forecast inputs are invalid or
missing.

Recommended failure cases:

- invalid configuration payload
- missing required simulation or generation keys
- invalid probability weights
- invalid batch count
- invalid games-per-match mapping

Recommended behavior:

- raise typed backend exceptions in service code
- return structured validation messages for UI callers

---

# Versioning

The forecasting service should expose a `formula_version` or equivalent output
field.

This is needed because estimates may change when generation logic changes.

Example:

```text
formula_version = "forecast_v1_expected_value"
```

This allows future UI or audit code to explain why older saved screenshots or
operator expectations may differ from new estimates.

---

# Test Strategy

The first version should include tests for:

- payload parsing and validation
- player forecast across multiple month counts
- zero-growth runs
- non-default team participation rates
- match forecast from configured team volume
- game forecast from configured match-type mix
- deterministic output for same payload

Recommended test style:

- unit tests for projection formulas
- no database dependency required for core forecast logic

This should remain a pure calculation module in V1.

---

# Recommended First Implementation Plan

## Phase 1

Build a pure forecast service with:

- payload input
- final-batch summary output
- optional per-batch rows
- expected-value formulas only

## Phase 2

Expose the service through:

- control-panel route or partial
- launch-preview UI card

## Phase 3

Refine the formulas if needed to better align with:

- seeded player growth behavior
- active team lifecycle maintenance
- more realistic active-player estimation

---

# Open Questions

The following decisions should be resolved during implementation:

1. Should the first version use expected values only, or mirror seeded player
   growth exactly?
2. Should active-player forecast rely only on configured weights, or should it
   incorporate a simple decay model?
3. Should cumulative match and game estimates be included in V1, or deferred?
4. Should the UI show only final-batch summary metrics, or also per-batch rows?
5. Should the forecast be recalculated live as config edits are made, or only on
   explicit preview action?

---

# Final Recommendation

Implement a pure, synchronous, expected-value forecasting service first.

It should estimate final-batch players, active players, teams, matches, and
games from the current configuration payload, return those values with clear
assumptions and caveats, and remain cheap enough to call from the control
panel without background execution.

That version is highly likely to be useful immediately and can later be refined
to mirror more of the live generation logic if the operator experience demands
tighter alignment.
