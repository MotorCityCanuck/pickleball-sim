# Generation Runtime Optimization Specification

## 1. Purpose

This document defines a prioritized optimization strategy for large historical
generation runs in `pickleball-sim`, with emphasis on monthly batch generation
at scales beyond the currently observed 250k-player workload and toward an
eventual 1M-player target.

This is an exploratory planning document only. It does not propose immediate
code changes. It identifies likely runtime bottlenecks, ranks optimization
opportunities by expected wall-clock reduction value, and defines an
instrumentation approach that can be implemented separately and used to guide
subsequent analysis.

## 2. Current Observations

Observed runtime characteristics from the current large run:

- generation run size: approximately 250,000 players
- elapsed runtime: approximately 12 hours at about 50% completion
- completed monthly batches after approximately 12 hours: 5
- most recently completed batch duration: approximately 2 hours 49 minutes
- first monthly batch completed in roughly 40% of the time required by later
  batches
- each successive monthly batch appears slightly slower than the one before it
- machine resource monitor observations:
  - memory utilization approximately 35% to 40%
  - roughly half of the vCPUs are lightly utilized
  - NVMe write throughput appears modest, approximately 10 MB/sec

Interpretation:

- the workload does not appear primarily memory-bound
- the workload does not appear primarily storage-bandwidth-bound
- the workload appears constrained by serial execution, Python/ORM overhead,
  growing historical lookback cost, and stage-specific algorithmic inefficiency
- the per-month cost appears to grow over time, implying some superlinear
  behavior across the full run

## 3. Non-Negotiable Constraint

Monthly batches must remain serialized.

This is a correct business constraint. Match generation, team state, and rating
history in month `N + 1` depend on the completed outcomes from month `N`.
Cross-month parallelism should therefore be treated as invalid unless the core
generation model is intentionally redesigned.

Optimization work must focus on:

- reducing the cost of each monthly batch
- reducing the growth of per-batch cost over time
- using more CPU within a single monthly batch where dependencies allow

## 4. Likely Runtime Drivers

The following runtime drivers appear most relevant based on the current
implementation and observed runtime behavior.

### 4.1 Ratings stage cost

The ratings stage is likely one of the highest-cost stages because it:

- loads the full match graph for a batch
- computes per-player rating changes for each match
- writes both `player_rating_history` and `ratings_update_log`
- appears to perform expensive prior-state lookup work for each player

This stage likely grows with:

- number of active players
- number of matches in the batch
- number of prior months already completed
- number of prior rating history rows per player

Updated interpretation from the current observed large run:

- although ratings remains structurally important, the currently observed
  runtime suggests that ratings may not be the dominant wall-clock bottleneck
  in the present implementation
- one observed batch produced approximately 1.5 million player rating updates
  in less than 15 minutes
- this indicates that, at least for the current run profile, the ratings stage
  is materially faster than the matches stage

As a result, ratings optimization should remain on the roadmap, but match-stage
analysis and optimization now take precedence.

### 4.2 Match generation cost

The matches stage is likely the second major driver because it combines:

- constrained match planning
- rematch-window enforcement
- active-team assembly
- game scoring
- persistence of `matches`, `match_teams`, `match_team_players`, and `games`

This stage likely grows with:

- number of active teams
- number of target matches
- increasing rejection work late in planning
- increasing historical scan cost for prior pairings

Updated interpretation from the current observed large run:

- one observed `matches` stage duration was approximately 3 hours 20 minutes
- surrounding observations indicate that `matches` is consuming roughly 75% to
  80% of total monthly batch runtime
- `matches` should therefore be treated as the primary optimization target for
  the current workload shape

This is now an empirical working conclusion, not just an architectural
inference.

### 4.3 ORM-heavy persistence

The current generation path appears to rely heavily on:

- large ORM object creation
- `session.add_all(...)`
- repeated `flush()`
- identity-map cleanup work

This creates CPU overhead that scales poorly with row volume.

### 4.4 Increasing-history tax

The observed pattern of later monthly batches taking longer than earlier ones
strongly suggests a cumulative history tax, especially in:

- rating-state lookup
- rematch-history lookup
- other queries whose search scope grows with prior completed months

## 5. Optimization Priorities

The following items are listed in expected time-reduction value order, not
implementation ease order.

### 5.1 Priority 1: Reduce match-planning rejection work

Expected value:

- very high

Why this ranks first:

- the current observed large run strongly suggests that `matches` is the
  dominant wall-clock bottleneck
- match planning appears to be more than simple row insertion
- later batches likely incur growing search effort before legal pairings are
  found
- this directly aligns with the observation that the first month is much faster
  than later months

Target outcome:

- reduce failed-attempt work in the match planner
- reduce the amount of repeated filtering and opponent-search work inside the
  inner planning loop

Expected benefits:

- lower CPU time in the matches stage
- less growth in per-batch runtime as the schedule becomes denser

Risks:

- moderate implementation complexity
- must preserve business rules for rematches, participation limits, and target
  match counts

### 5.2 Priority 2: Bound rematch-history lookback to the actual rule window

Expected value:

- high

Why this ranks second:

- the current historical rematch lookup likely grows every month
- if the rule only cares about a recent rematch window, scanning the full
  historical run is unnecessary

Target outcome:

- query only the history required by the configured rematch rule

Expected benefits:

- lower startup cost for the matches stage in later months
- reduced database read volume
- reduced in-memory processing for historical pairings

Risks:

- low to moderate
- requires clear confirmation that the business rule is window-bounded rather
  than entire-history-bounded

### 5.3 Priority 3: Replace hot-path ORM writes with bulk persistence

Expected value:

- high

Why this ranks third:

- multiple stages create very large Python object collections and persist them
  through ORM-heavy paths
- the machine observations suggest CPU is being spent on application-layer row
  handling rather than storage saturation
- the matches stage is a prime candidate because it writes high volumes of
  related rows after planning completes

Target outcome:

- move hot persistence paths toward Core bulk insert patterns or other
  lower-overhead write mechanisms

Expected benefits:

- broad wall-clock reduction across all heavy stages
- lower Python overhead
- better scaling with larger row counts

Risks:

- moderate
- higher implementation and testing cost because ORM lifecycle behavior changes

### 5.4 Priority 4: Rewrite ratings prior-state lookup to a set-based approach

Expected value:

- high

Why this now ranks fourth:

- current behavior likely performs repeated prior-history lookup per player
- that cost grows with both player count and history depth
- this still matters for larger scales even though current observed wall-clock
  evidence suggests `matches` is the more immediate bottleneck

Target outcome:

- fetch current player rating state for the batch in one set-based operation
  instead of repeated per-player history scans

Expected benefits:

- large reduction in rating-stage wall time
- reduced database round-trips
- reduced growth in rating-stage cost across later months

Risks:

- moderate
- must preserve exact rating semantics and ordering

### 5.5 Priority 5: Reduce or make optional `ratings_update_log` write volume

Expected value:

- medium to high

Why this ranks fifth:

- this table creates one audit row per player per match
- its write volume is likely substantial at large scales
- it may not be required for every full-scale generation run

Target outcome:

- determine whether full audit logging is required for every run, only selected
  runs, or only selected modes

Expected benefits:

- lower rating-stage write volume
- reduced total inserted rows
- less index maintenance work

Risks:

- business and audit tradeoff
- any reduction must not break required downstream validation or realism audit
  use cases

Important clarification:

- current ratings audit logging is already at the match level in the sense that
  ratings are updated once per player per match, not once per game
- the current `ratings_update_log` granularity is one row per player-match
- a future optional redesign could move to one aggregate audit row per match if
  the project decides that per-player before/after detail is not required for
  all large runs

That potential redesign should be treated as a separate business and audit
decision, not just a mechanical performance change.

### 5.6 Priority 6: Parallelize safe intra-month work

Expected value:

- medium

Why this ranks sixth:

- monthly serialization is required
- however, some work inside a month is still embarrassingly parallel
- current CPU observations suggest headroom exists

Safe candidate areas:

- player row fabrication before persistence
- match scoring after pairings are finalized
- selected precomputation tasks that do not alter business ordering

Expected benefits:

- better vCPU utilization
- reduced wall-clock time for CPU-heavy subphases

Risks:

- moderate to high
- determinism and RNG sequencing must be preserved or consciously redefined

### 5.7 Priority 7: Stage-specific index tuning after instrumentation

Expected value:

- medium

Why this ranks seventh:

- the schema already has many basic FK and lookup indexes
- indexing is unlikely to be the primary fix
- however, targeted index improvements may still help once measured query
  patterns are known

Target outcome:

- add or refine indexes only after instrumentation shows specific high-cost
  query patterns

Expected benefits:

- lower latency on known hot queries
- cheaper latest-state and history-window lookups

Risks:

- low
- risk is mostly in spending time on low-impact tuning before the larger
  architectural issues are addressed

## 6. Optimization Items Not Recommended as First-Line Work

The following should not be treated as primary solutions at this stage:

- adding more RAM alone
- treating NVMe throughput as the main bottleneck
- pursuing cross-month parallel execution
- extensive UI-level instrumentation
- relying only on console logging for runtime diagnosis

These may have supporting value, but they do not align with the observed
runtime profile.

## 7. Instrumentation Requirements

Additional instrumentation is required before implementation prioritization can
be finalized with confidence.

The goal is to collect structured runtime evidence from real large runs without:

- polluting the web UI
- flooding the console log
- relying on ad hoc manual timing

### 7.1 Recommended approach

Yes, an instrumentation table should be added to the schema.

This is the recommended approach because it provides:

- structured historical timing data
- run-to-run comparability
- easy filtering by run, batch, stage, and subphase
- a durable source you can export and share for analysis
- a much better operator experience than console logs

### 7.2 Instrumentation design principles

Instrumentation should be:

- invisible to normal UI flows
- queryable directly from the database
- lightweight enough to keep overhead low
- granular enough to isolate planning, read, write, and compute costs
- associated with `generation_run_id` and `batch_id` whenever applicable

### 7.3 Proposed table purpose

Recommended table purpose:

- store stage and subphase timing events for generation runs
- store row counts, attempt counts, and other compact numeric diagnostics
- support later analytical review without full trace logging

This should be operational instrumentation, not student-facing data.

### 7.4 Proposed instrumentation grain

Instrumentation should support at least these levels:

- generation run
- monthly batch
- stage
- subphase

Suggested stages:

- players
- club_memberships
- teams
- matches
- ratings

Suggested subphases:

- read_inputs
- build_candidates
- planning
- scoring
- write_matches
- write_related_rows
- latest_state_lookup
- rating_compute
- write_rating_history
- write_rating_logs
- finalize

### 7.5 Proposed table shape

Suggested logical structure for an instrumentation table:

`generation_runtime_metrics`

Suggested columns:

- `id`
- `generation_run_id`
- `batch_id` nullable
- `stage_name`
- `subphase_name`
- `event_type`
  - examples: `started`, `completed`, `checkpoint`
- `started_at`
- `completed_at` nullable
- `elapsed_ms` nullable
- `row_count` nullable
- `input_count` nullable
- `output_count` nullable
- `attempt_count` nullable
- `warning_count` nullable
- `extra_metrics_json` nullable
- `created_at`

Optional additional columns:

- `host_name`
- `process_id`
- `worker_name`
- `config_snapshot_hash`

### 7.6 Why a table is preferable to logs

Console logs are a poor fit here because they are:

- noisy during long runs
- hard to aggregate
- hard to compare across runs
- awkward to share back for analysis
- likely to omit the structured numeric context needed for diagnosis

A table allows focused queries such as:

- stage duration by month
- planning time vs persistence time for matches
- latest-state lookup time vs row-write time for ratings
- rows written per stage vs elapsed time
- attempt count vs match count

### 7.7 Suggested minimum instrumentation payload

At minimum, each completed subphase should record:

- generation run id
- batch id when applicable
- stage name
- subphase name
- start timestamp
- completion timestamp
- elapsed milliseconds
- rows read or produced where applicable

This minimum dataset is enough to answer most immediate optimization questions.

## 8. Required Instrumentation Coverage

The first instrumentation pass should focus on the two most suspect stages:

### 8.1 Matches stage

Capture at minimum:

- total stage duration
- active team candidate count
- target match count
- actual match count
- planning duration
- planning attempt count
- planning success rate
- rematch-history load duration
- scoring duration
- `matches` write duration
- `match_teams` write duration
- `match_team_players` write duration
- `games` write duration

Key questions this must answer:

- how much time is spent planning vs persisting?
- how quickly does the planning attempt count grow by month?
- how much of the later-month slowdown comes from historical rematch lookup?

### 8.1.1 Observed two-pass progress behavior in matches

An important observed behavior in the current implementation is that the
`matches` stage appears to approach 100% complete in the UI, then revert to 0%
and advance again.

This is most likely explained by the current internal structure of the stage:

- first pass: planning and persisting `Match` rows up to the target match count
- second pass: iterating back through the planned pairings to generate scoring
  outcomes, `match_teams`, `match_team_players`, and `games`

The second pass is expected to progress more quickly than the first because:

- the constrained matchmaking search has already completed
- the remaining work is more deterministic row fabrication and persistence

This behavior should be treated as a progress-modeling issue rather than proof
that the match stage is regenerating the entire match set from scratch.

Implications for instrumentation:

- `matches` must be instrumented as multiple explicit subphases rather than one
  flat stage timer
- the first instrumentation pass should separately capture:
  - planning and match-row creation
  - scoring and related-row creation
  - persistence of `match_teams`, `match_team_players`, and `games`

Implications for future UI interpretation:

- the current single-stage progress bar is semantically misleading
- future progress reporting should distinguish matches subphases instead of
  treating them as a single monotonic percent

### 8.2 Ratings stage

Capture at minimum:

- total stage duration
- match count
- participating player count
- latest-state lookup duration
- match-graph load duration
- rating compute duration
- `player_rating_history` write duration
- `ratings_update_log` write duration
- total rows written to each ratings-related table

Key questions this must answer:

- how much time is spent in prior-state lookup?
- how much time is spent computing vs writing?
- how much total cost is attributable to `ratings_update_log`?

### 8.2.1 Observed `matches complete` to `ratings pending` handoff delay

Another observed behavior in the current large run is that the `matches` stage
appears complete in the UI while the `ratings` stage remains in `pending
execution` for a noticeable period of time, followed later by a visible
`ratings` `running` signal.

The updated interpretation is that this delay is most likely caused by
post-progress cleanup and finalization inside the `matches` stage rather than
true pipeline idleness.

The likely remaining work after match progress appears visually complete
includes:

- persistence of related match rows
- winner/final-state assignment
- batch-level counter updates
- final flush and durable commit work

Only after that work completes does the `ratings` stage become visibly
`running`.

Once `ratings` does begin, it still provides little or no internal
heartbeat/progress visibility, so it may continue to appear opaque even when it
is actively working.

This creates a misleading UI impression that the pipeline is stalled between
stages even when the prior stage is still finalizing successfully.

Implications for instrumentation:

- explicitly measure the elapsed interval between:
  - `matches` stage visible progress completion
  - `matches` stage related-row persistence completion
  - `matches` stage durable completion
  - `ratings` stage start visibility
- capture a ratings stage `started` event independently from ratings internal
  subphase checkpoints
- later instrumentation should also capture ratings subphases so long-running
  ratings work does not appear visually idle

Key questions this must answer:

- how much time is being spent after `matches` appears complete but before
  `ratings` begins visibly?
- is that gap dominated by `matches` finalization work, durable commit work, or
  actual ratings startup?

### 8.3 Secondary stages

Capture at minimum for:

- players
- club memberships
- teams

For each:

- total stage duration
- rows created
- read duration
- object/build duration
- write duration

## 9. Analysis Workflow for Future Review

Once instrumentation exists, future analysis should follow this sequence:

1. Run a large controlled build.
2. Extract instrumentation rows for the full run.
3. Compare batch duration growth by stage.
4. Identify which subphases grow fastest month over month.
5. Prioritize only the top one or two drivers first.
6. Re-run after each major optimization to confirm actual gain.

The goal is to avoid optimizing by intuition after the first pass.

## 10. Suggested Analysis Queries

The instrumentation design should support questions like:

- which stage consumed the most wall-clock time for each monthly batch?
- which stage grew the fastest from batch 1 to batch N?
- what percentage of the matches stage is planning vs writing?
- what percentage of the ratings stage is latest-state lookup vs writing?
- how many rows per second were written in each stage?
- how many planning attempts were required per successful match?
- does write throughput degrade as table size grows?

## 11. Decision Framework

Once instrumentation data is available, optimization work should be chosen using
the following decision order:

1. highest total wall-clock contributor
2. fastest month-over-month growth contributor
3. lowest-risk change with large expected gain
4. broadest reuse across multiple stages

This keeps effort aligned to actual runtime reduction rather than local code
cleanliness.

## 12. Recommended First Implementation Sequence

After instrumentation is added and one or more large-run datasets are captured,
the expected implementation sequence should be:

1. match-planning optimization
2. rematch-history bounding
3. bulk persistence on hottest match-stage write paths
4. ratings latest-state lookup rewrite
5. optional reduction of ratings audit row volume
6. safe intra-month parallelism
7. targeted index tuning based on measured query patterns

This sequence should be revisited only if instrumentation results show a
materially different bottleneck distribution.

## 13. Deliverable Expectations for Instrumented Runs

For future review, the preferred handoff is not screenshots or log excerpts.

Preferred handoff artifacts:

- exported rows from the instrumentation table for one or more large runs
- a short description of run parameters
- total player count
- number of historical months
- growth rate if applicable
- environment notes such as CPU count and RAM

With that dataset, targeted optimization analysis can be performed without
adding any UI elements or relying on console output.

## 14. Recommended Instrumented Run Sizes

The first instrumented run does not need to match the largest currently running
workload.

The goal of the first instrumented run is to expose:

- stage dominance
- month-over-month growth behavior
- the relative contribution of planning, lookup, compute, and write subphases

### 14.1 First recommended run

Recommended first instrumented run:

- player count: 75,000 to 100,000
- monthly batch count: 6 to 8

Preferred initial target:

- 100,000 players
- 6 to 8 monthly batches

Why this is the preferred first target:

- it is large enough for matches and ratings bottlenecks to emerge
- it is more likely than a small run to show month-over-month degradation
- it should be materially faster than a 250,000-player run while still
  producing useful diagnostic evidence

### 14.2 Second recommended run if needed

If the first instrumented run is too fast, too flat, or does not clearly expose
the dominant bottleneck, the next recommended step is:

- player count: 150,000
- monthly batch count: same as the first instrumented run

This second run should be used only if the first run does not provide enough
signal.

### 14.3 Run sizes to avoid for initial analysis

The following are not recommended as the first instrumented run:

- 10,000 to 25,000 players, because the workload may be too small to surface
  the true scaling behavior
- 250,000 players or higher, because the first goal is diagnosis rather than
  maximum-stress confirmation

### 14.4 Minimum evidence required for useful analysis

One instrumented run is sufficient for initial analysis if it provides:

- at least 6 monthly batches
- stage-level and subphase-level timing rows
- row counts and attempt counts for matches and ratings
- a visible duration difference between early and late monthly batches

If those conditions are met, the results should be sufficient to determine:

- whether matches or ratings is the primary bottleneck
- whether the growth pattern is driven mostly by current-month row volume,
  cumulative history lookback, or both
- which optimization should be implemented first
