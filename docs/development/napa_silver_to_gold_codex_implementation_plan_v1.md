# NAPA Olympic Analytics Platform

# Silver-to-Gold Codex Implementation Plan

**Document Version:** 1.0  
**Status:** Instructor Implementation Plan  
**Audience:** Instructor, Technical Lead, Codex  
**Primary Specification:** `NAPA_Silver_to_Gold_Layer_Engineering_Spec_v1.0.md`  
**Upstream Specification:** `NAPA_Bronze_to_Silver_Spec_v1.1.md`  
**Platform:** Databricks Free Edition, Unity Catalog, Delta Lake, PySpark, Spark SQL, optional Spark MLlib  
**Supported Releases:** `napa_5k`, `napa_50k`, `napa_250k`  
**Authoritative Recommendation Release:** `napa_250k`

---

# Table of Contents

1. Purpose  
2. How to Use This Plan  
3. Implementation Strategy  
4. Codex Operating Rules  
5. Required Inputs  
6. Expected Repository Structure  
7. Git and Branch Strategy  
8. Definition of Implementation Phases  
9. Phase 0 — Repository and Silver Contract Discovery  
10. Phase 1 — Gold Configuration and Runtime Context  
11. Phase 2 — Operations, Logging, and Publication Framework  
12. Phase 3 — Competition Foundation  
13. Phase 4 — Persistent-Team Resolution  
14. Phase 5 — Analytical Rating Engine  
15. Phase 6 — Player Features and Development Analytics  
16. Phase 7 — Team and Partnership Features  
17. Phase 8 — Data Quality Confidence  
18. Phase 9 — Match Outcome Prediction  
19. Phase 10 — Feature Normalization and Player Scorecards  
20. Phase 11 — Team Selection Scorecards and Eligibility  
21. Phase 12 — Olympic Candidate Rankings and Recommendations  
22. Phase 13 — Sensitivity and Explainability  
23. Phase 14 — Workflow Assembly and Databricks Deployment  
24. Phase 15 — Release Validation and Acceptance  
25. Phase 16 — Documentation and Final Handoff  
26. Cross-Phase Test Strategy  
27. Execution Gates  
28. Recommended Codex Session Sequence  
29. Master Codex Prompt  
30. Phase Prompt Templates  
31. Progress Tracking Checklist  
32. Completion Report Template  
33. Known Risks and Mitigations  
34. Decisions Requiring Instructor Review  
35. Final Definition of Done  

---

# 1. Purpose

This document converts the NAPA Silver-to-Gold engineering specification into a practical, phased implementation plan for Codex.

The objective is to build a production-quality instructor reference implementation that transforms validated Silver data into Gold analytical products supporting:

- player performance evaluation;
- independently calculated analytical ratings;
- match outcome probability and prediction;
- player trend and development analysis;
- doubles partnership evaluation;
- national player rankings;
- Olympic team candidate rankings;
- primary, alternate, and watchlist recommendations;
- confidence, quality, sensitivity, and explanation outputs.

This plan is intentionally organized as a sequence of controlled Codex work sessions.

Codex shall not attempt to build the entire Gold layer in one uncontrolled request.

Each phase must:

1. inspect the relevant existing code and data contracts;
2. implement a bounded capability;
3. add or update tests;
4. run the available tests;
5. report actual results;
6. identify assumptions and unresolved issues;
7. stop at a defined implementation gate.

---

# 2. How to Use This Plan

## 2.1 Recommended Usage

Use one Codex session per phase or small group of tightly related phases.

At the beginning of every session:

1. provide Codex with the master prompt;
2. identify the current phase;
3. provide the Silver-to-Gold specification;
4. provide this implementation plan;
5. instruct Codex to inspect the repository before editing;
6. instruct Codex not to proceed beyond the current phase;
7. require a completion report.

## 2.2 Do Not Use a Single “Build Everything” Prompt

A single large implementation request creates unnecessary risk:

- Codex may invent schemas or fields;
- phase dependencies may be missed;
- rating leakage may be introduced;
- tests may be skipped;
- Databricks workflow definitions may be created before modules are stable;
- operational logging may be bolted on too late;
- recommendations may be generated before eligibility is validated;
- errors become difficult to isolate.

The build shall therefore proceed through explicit gates.

## 2.3 Instructor Control

The instructor shall approve:

- discovery findings;
- category and country mappings;
- analytical rating configuration;
- scorecard weights;
- eligibility rules;
- recommendation counts;
- any roster overlap constraints;
- model selection;
- deviations from the specification.

Codex may propose options, but shall not silently make policy decisions.

---

# 3. Implementation Strategy

## 3.1 Overall Sequence

```text
Discover the actual Silver contract
        ↓
Build configuration and runtime context
        ↓
Build operations and publication controls
        ↓
Construct competition foundation
        ↓
Resolve persistent teams
        ↓
Calculate analytical ratings
        ↓
Build player features
        ↓
Build team and partnership features
        ↓
Calculate quality confidence
        ↓
Build match probability and optional model
        ↓
Normalize features and score players
        ↓
Score and validate teams
        ↓
Rank Olympic candidates
        ↓
Publish recommendations
        ↓
Run sensitivity and explanations
        ↓
Assemble Databricks Workflow
        ↓
Validate 5K, 50K, and 250K
        ↓
Complete documentation and handoff
```

## 3.2 Core Technical Principles

The implementation shall be:

- configuration-driven;
- deterministic;
- full refresh;
- release-parameterized;
- Silver-only for upstream reads;
- modular and testable;
- explicit about analytical time;
- protected against future-data leakage;
- explainable;
- auditable;
- suitable for Databricks Free Edition;
- scalable from 5K to 250K releases.

## 3.3 Build the Foundation Before the Analytics

The Gold layer depends on correct interpretation of:

- match sides;
- match winners;
- game scores;
- player participation;
- persistent team identity;
- country;
- category;
- membership periods;
- analysis dates.

No rating, feature, model, or recommendation work shall begin until the competition foundation passes its acceptance tests.

## 3.4 Separate Data Engineering from Decision Logic

The implementation shall maintain clear boundaries:

```text
Foundation facts
→ analytical features
→ estimates and probabilities
→ normalized component scores
→ eligibility decisions
→ rankings
→ recommendation statuses
```

Do not mix eligibility logic directly into low-level feature calculations.

Do not hard-code scorecard weights inside transformation functions.

---

# 4. Codex Operating Rules

Codex shall follow these rules for every phase.

## 4.1 Inspect Before Editing

Before modifying code, Codex shall inspect:

- repository structure;
- applicable `AGENTS.md` files;
- existing coding conventions;
- environment configuration files;
- Databricks bundle configuration;
- existing Raw-to-Bronze and Bronze-to-Silver modules;
- existing operations utilities;
- current test framework;
- actual Silver table schemas;
- existing documentation.

## 4.2 Physical Schema Is Authoritative

Representative fields in the specification are conceptual until confirmed.

Codex shall not invent fields such as:

- `team_id` on match tables;
- gender codes;
- country codes;
- status codes;
- category values;
- timestamps;
- scoring fields.

Where a required concept is not directly present, Codex shall:

1. document the gap;
2. identify valid derivation options;
3. use the configured and approved derivation;
4. add tests for the derivation;
5. preserve uncertainty or unresolved status.

## 4.3 No Hidden Data or Simulation Logic

Codex shall not:

- access instructor-only simulation parameters;
- search for hidden factors;
- reverse-engineer the tournament simulator;
- tune selection logic against tournament outcomes;
- encode undocumented roster-selection answers;
- create recommendations from information unavailable to students.

## 4.4 No Fabricated Results

Codex shall never claim:

- a test passed when it was not run;
- a Databricks Workflow succeeded when it was not run;
- a table exists when it was not created;
- a model achieved metrics that were not measured;
- an exact row count without executing the query;
- a recommendation was produced without running the pipeline.

## 4.5 Stop at the Phase Boundary

At the end of each phase, Codex shall stop and report.

Codex shall not proceed into the next phase unless explicitly instructed.

## 4.6 Preserve Existing Working Behavior

Codex shall not unnecessarily refactor working Raw-to-Bronze or Bronze-to-Silver code.

Shared utilities may be extended only when:

- the behavior is backward compatible;
- tests cover the change;
- the change is required by the Gold pipeline.

## 4.7 Thin Notebooks

Databricks notebooks or Python workflow entry points shall:

- resolve parameters;
- create the runtime context;
- call tested Python modules;
- report task results;
- fail clearly.

Business logic shall remain in `src/`.

## 4.8 Deterministic Implementation

Codex shall control:

- match ordering;
- sort keys;
- rank tie-breaking;
- model random seed;
- feature ordering;
- train-validation cutoffs;
- scorecard rounding;
- record hashing;
- output ordering in tests.

---

# 5. Required Inputs

Codex shall locate and review the following before Phase 0 is complete.

## 5.1 Specifications

Required:

```text
NAPA_Raw_to_Bronze_Spec.md
NAPA_Bronze_to_Silver_Spec_v1.1.md
NAPA_Silver_to_Gold_Layer_Engineering_Spec_v1.0.md
NAPA_Silver_to_Gold_Codex_Implementation_Plan_v1.0.md
```

Also review where available:

```text
NAPA Dataset Specification
NAPA Student Release Guide
NAPA RFP
NAPA Milestone 3 requirements
```

## 5.2 Configuration

Required environment configurations:

```text
config/environments/napa_5k.yml
config/environments/napa_50k.yml
config/environments/napa_250k.yml
```

Required or planned Gold configurations:

```text
config/silver_to_gold/base.yml
config/silver_to_gold/gold_tables.yml
config/silver_to_gold/eligibility.yml
config/silver_to_gold/evidence_windows.yml
config/silver_to_gold/ratings.yml
config/silver_to_gold/features.yml
config/silver_to_gold/models.yml
config/silver_to_gold/scorecards.yml
config/silver_to_gold/sensitivity.yml
config/silver_to_gold/quality_rules.yml
config/silver_to_gold/logging.yml
```

## 5.3 Silver Tables

Default required Silver inventory:

```text
regions
clubs
club_memberships
players
player_registrations
player_assessment_history
teams
team_memberships
matches
match_teams
match_team_players
match_games
monthly_batches
```

Codex shall verify actual presence and physical schemas.

## 5.4 Existing Pipeline Assets

Review:

- root `databricks.yml`;
- included bundle resource files;
- current job or workflow YAML files;
- environment variables;
- existing job parameters;
- cluster or serverless settings;
- package installation approach;
- existing test commands;
- CI configuration where available.

---

# 6. Expected Repository Structure

The final repository should converge toward this structure while respecting the existing project layout.

```text
config/
├── environments/
│   ├── napa_5k.yml
│   ├── napa_50k.yml
│   └── napa_250k.yml
├── raw_to_bronze/
├── bronze_to_silver/
└── silver_to_gold/
    ├── base.yml
    ├── gold_tables.yml
    ├── eligibility.yml
    ├── evidence_windows.yml
    ├── ratings.yml
    ├── features.yml
    ├── models.yml
    ├── scorecards.yml
    ├── sensitivity.yml
    ├── quality_rules.yml
    └── logging.yml

src/
└── napa_pipeline/
    ├── common/
    ├── raw_to_bronze/
    ├── bronze_to_silver/
    └── silver_to_gold/
        ├── __init__.py
        ├── io.py
        ├── time_controls.py
        ├── competition.py
        ├── team_resolution.py
        ├── metrics.py
        ├── ratings.py
        ├── features.py
        ├── normalization.py
        ├── match_models.py
        ├── eligibility.py
        ├── scorecards.py
        ├── recommendations.py
        ├── sensitivity.py
        ├── explainability.py
        ├── validation.py
        ├── reconciliation.py
        ├── publish.py
        └── transforms/

notebooks/
└── silver_to_gold/
    ├── 01_resolve_configuration.py
    ├── 02_validate_silver_upstream.py
    ├── 03_build_competition_foundation.py
    ├── 04_build_analytical_ratings.py
    ├── 05_build_player_features.py
    ├── 06_build_team_features.py
    ├── 07_build_match_outcome_products.py
    ├── 08_build_scorecards_and_rankings.py
    ├── 09_build_olympic_candidates.py
    ├── 10_build_sensitivity_and_explanations.py
    ├── 11_validate_and_publish.py
    └── 12_publish_run_summary.py

resources/
└── silver_to_gold/
    └── napa_silver_to_gold.job.yml

tests/
├── unit/
│   └── silver_to_gold/
├── integration/
│   └── silver_to_gold/
├── acceptance/
│   └── silver_to_gold/
├── backtest/
│   └── silver_to_gold/
└── fixtures/
    └── silver_to_gold/

docs/
├── NAPA_Silver_to_Gold_Layer_Engineering_Spec_v1.0.md
├── NAPA_Silver_to_Gold_Codex_Implementation_Plan_v1.0.md
├── data_dictionary_gold.md
├── gold_lineage.md
├── analytical_methodology.md
├── model_card_match_outcomes.md
├── selection_methodology.md
├── quality_rules_gold.md
└── runbook_gold.md
```

Codex shall adapt names to the existing repository conventions rather than creating parallel duplicate structures.

---

# 7. Git and Branch Strategy

## 7.1 Recommended Branch

Create a dedicated feature branch:

```text
feature/silver-to-gold
```

If the repository uses issue-oriented names:

```text
feature/gold-layer-foundation
```

## 7.2 Phase Commits

Create one clean commit at the end of each accepted phase.

Recommended commit pattern:

```text
feat(gold): add configuration and runtime context
feat(gold): build competition foundation
feat(gold): implement persistent team resolution
feat(gold): add deterministic analytical rating engine
feat(gold): add player feature products
feat(gold): add team and partnership analytics
feat(gold): add match outcome baseline and model
feat(gold): add scorecards and candidate rankings
feat(gold): add recommendations and sensitivity
feat(gold): deploy silver-to-gold workflow
test(gold): complete release acceptance tests
docs(gold): complete implementation documentation
```

## 7.3 Commit Gate

Before each commit:

- format and lint applicable files;
- run relevant unit tests;
- run relevant integration tests;
- review changed files;
- remove temporary debugging code;
- update phase status;
- include actual test results in the Codex report.

## 7.4 Avoid Large Unreviewable Commits

Do not combine:

- rating engine;
- modeling;
- scorecards;
- workflow deployment;

into one commit.

---

# 8. Definition of Implementation Phases

| Phase | Primary Outcome | Depends On |
|---|---|---|
| 0 | Verified repository and Silver contract | None |
| 1 | Gold configuration and runtime context | Phase 0 |
| 2 | Operations, logging, and publication framework | Phase 1 |
| 3 | Competition foundation | Phases 1–2 |
| 4 | Persistent-team resolution | Phase 3 |
| 5 | Analytical rating engine | Phases 3–4 |
| 6 | Player features and development analytics | Phase 5 |
| 7 | Team and partnership features | Phases 4–6 |
| 8 | Data quality confidence | Phases 3–7 |
| 9 | Match outcome prediction | Phases 5–8 |
| 10 | Player scorecards and rankings | Phases 6, 8, 9 |
| 11 | Team scorecards and eligibility | Phases 7–10 |
| 12 | Candidates and recommendations | Phase 11 |
| 13 | Sensitivity and explainability | Phase 12 |
| 14 | Workflow assembly and deployment | Phases 1–13 |
| 15 | Release validation | Phase 14 |
| 16 | Documentation and handoff | Phase 15 |

---

# 9. Phase 0 — Repository and Silver Contract Discovery

## 9.1 Objective

Establish the actual implementation contract before writing Gold code.

## 9.2 Codex Tasks

Codex shall:

1. inspect the full repository tree;
2. locate all `AGENTS.md` files;
3. summarize current pipeline architecture;
4. identify package and module conventions;
5. identify test framework and commands;
6. inspect Databricks bundle definitions;
7. inspect environment YAML files;
8. inspect Bronze-to-Silver runtime context;
9. inspect operations table definitions;
10. inspect actual Silver table schemas for at least `napa_5k`;
11. enumerate actual values for:
    - player status;
    - team status;
    - country code;
    - region type;
    - gender;
    - team type/category;
    - match type;
12. determine whether historical match sides contain persistent `team_id`;
13. determine whether player country is direct or region-derived;
14. determine whether membership dates support as-of joins;
15. determine the latest successful Silver run resolution method;
16. document gaps between specification and physical data.

## 9.3 Required Deliverables

Create:

```text
docs/gold_discovery_report.md
docs/gold_source_contract.md
```

`gold_source_contract.md` shall contain:

- Silver table inventory;
- columns and data types;
- primary keys;
- foreign keys;
- nullable fields;
- status/category code values;
- field derivations;
- unsupported conceptual fields;
- approved fallbacks;
- unresolved questions.

## 9.4 Tests and Validation

No production Gold transformation is required.

Run:

- existing repository tests;
- configuration parsing checks;
- imports;
- schema inspection queries.

## 9.5 Acceptance Gate

Phase 0 is complete only when:

- actual Silver schemas are documented;
- all required concepts have a source or documented gap;
- country and category mappings are known or explicitly marked unresolved;
- match team identity options are documented;
- existing shared utilities to reuse are identified;
- no Gold business logic has been prematurely implemented.

## 9.6 Stop Conditions

Stop and request instructor review if:

- country cannot be determined;
- team category cannot be mapped;
- match winner cannot be reliably determined;
- doubles membership cannot be reconstructed;
- critical Silver tables are absent;
- the physical schema materially contradicts the Gold specification.

---

# 10. Phase 1 — Gold Configuration and Runtime Context

## 10.1 Objective

Create the configuration and runtime foundation shared by all Gold tasks.

## 10.2 Codex Tasks

Implement or extend:

```text
src/napa_pipeline/common/config.py
src/napa_pipeline/common/context.py
src/napa_pipeline/silver_to_gold/time_controls.py
src/napa_pipeline/silver_to_gold/io.py
```

Create Gold configuration files:

```text
base.yml
gold_tables.yml
eligibility.yml
evidence_windows.yml
ratings.yml
features.yml
models.yml
scorecards.yml
sensitivity.yml
quality_rules.yml
logging.yml
```

The runtime context shall resolve:

```text
release_name
release_role
catalog
silver_schema
gold_schema
stage_schema
operations_schema
analysis_as_of_date
scoring_scenario
model_enabled
pipeline_version
configuration_hash
deterministic_seed
upstream_silver_run_id
```

## 10.3 Configuration Validation

Validate:

- supported release;
- schema separation;
- required YAML sections;
- score weights;
- rating parameters;
- evidence windows;
- category mappings;
- recommendation counts;
- model split fractions;
- deterministic seed;
- no unresolved placeholders.

## 10.4 Analysis Date

Implement:

```text
MAX_VALID_MATCH_DATE
```

as the default analysis-date strategy.

Allow an explicit backtest date.

## 10.5 Required Tests

Unit tests shall cover:

- each release configuration;
- unsupported release;
- missing configuration;
- invalid score total;
- invalid negative weights;
- invalid evidence window;
- invalid model split;
- analysis-date resolution;
- configuration hash stability;
- schema-name resolution.

## 10.6 Acceptance Gate

Phase 1 is complete when:

- all three release configurations resolve;
- Gold context can be created locally with test fixtures;
- invalid configurations fail clearly;
- no release-specific logic is embedded in transformation code;
- tests pass.

---

# 11. Phase 2 — Operations, Logging, and Publication Framework

## 11.1 Objective

Create operational controls before building business outputs.

## 11.2 Codex Tasks

Implement:

```text
pipeline run registration
table run logging
quality result logging
reconciliation result logging
model run logging
recommendation run logging
stage-to-Gold publication
failure handling
```

Create or migrate operations tables:

```text
gold_table_runs
gold_quality_results
gold_reconciliation_results
gold_model_runs
gold_model_metrics
gold_recommendation_runs
```

Reuse `pipeline_runs` where compatible.

## 11.3 Publication Pattern

Implement:

```text
build in stage
→ validate
→ overwrite Gold target
→ verify target
→ mark table success
```

## 11.4 Error Handling

Requirements:

- preserve root exception;
- mark task/table failure;
- do not mark pipeline success;
- do not publish incomplete recommendations;
- include release and run IDs in logs;
- avoid broad exception swallowing.

## 11.5 Required Tests

Test:

- successful run registration;
- failure registration;
- table-run status transitions;
- quality-result inserts;
- publication overwrite;
- publication failure;
- previous successful output protection;
- record hash stability.

## 11.6 Acceptance Gate

Phase 2 is complete when:

- a test Gold table can be staged and published;
- success and failure are accurately logged;
- no partial run can appear successful;
- operations tables use release and lineage identifiers;
- tests pass.

---

# 12. Phase 3 — Competition Foundation

## 12.1 Objective

Build the authoritative Gold competition facts used by every analytical product.

## 12.2 Target Tables

```text
competition_match_sides
competition_player_matches
```

## 12.3 Codex Tasks

Implement:

- valid match population;
- deterministic match ordering;
- two-sided match representation;
- opponent-side joins;
- match outcome derivation;
- game outcome derivation;
- game and point aggregation;
- player participation;
- partner and opponent identifiers;
- country and region context;
- batch sequence context;
- as-of cutoff;
- exclusion reason handling.

## 12.4 Required Metrics

At minimum:

```text
won_flag
lost_flag
side_score
opponent_score
games_won
games_lost
game_differential
points_for
points_against
point_differential
point_share
close_game_count
deciding_game_flag
average_team_rating_at_match
opponent_average_team_rating_at_match
canonical_player_pair_key
```

## 12.5 Data Quality Rules

Validate:

- one match record per match ID;
- expected number of sides;
- expected number of players per doubles side;
- winner is one of the sides;
- scores agree with winner where available;
- game winners agree with game scores;
- no player appears on opposing sides in the same match;
- no future match exceeds the analysis date;
- duplicate player participation is excluded or fails according to severity.

## 12.6 Required Tests

Fixtures shall include:

- normal two-game match;
- deciding-game match;
- close game;
- invalid winner;
- duplicate side;
- missing player;
- player on both sides;
- match after analysis date;
- null score behavior;
- deterministic ordering.

## 12.7 Acceptance Gate

Phase 3 is complete when:

- the 5K competition facts build;
- row-count reconciliation is available;
- exclusions are explainable;
- match and game outcomes are consistent;
- no rating or scorecard logic has been added;
- tests pass.

---

# 13. Phase 4 — Persistent-Team Resolution

## 13.1 Objective

Map historical match sides to valid persistent NAPA teams without creating synthetic team IDs.

## 13.2 Target Table

```text
resolved_match_teams
```

## 13.3 Resolution Hierarchy

Implement:

1. direct valid team ID;
2. active membership pair at match date;
3. unique historical pair;
4. unresolved;
5. ambiguous.

## 13.4 Required Fields

```text
match_id
team_number
canonical_player_pair_key
resolved_team_id
team_resolution_method
team_resolution_status
team_resolution_confidence
candidate_attribution_allowed_flag
```

## 13.5 Constraints

Codex shall not:

- create a new team ID;
- assign an ambiguous team;
- use an inactive team without documented fallback;
- attribute unresolved match performance to a candidate team.

## 13.6 Required Tests

Test:

- direct resolution;
- active membership pair;
- unique historical pair;
- overlapping memberships;
- ambiguous historical pair;
- no team;
- dissolved team;
- membership date boundary;
- reversed player order;
- duplicate membership records.

## 13.7 Acceptance Gate

Phase 4 is complete when:

- resolution counts are published;
- direct, inferred, unresolved, and ambiguous populations reconcile;
- unresolved matches remain usable for player analytics;
- only valid persistent team IDs are candidate-attributable;
- tests pass.

---

# 14. Phase 5 — Analytical Rating Engine

## 14.1 Objective

Implement the transparent, chronological doubles Elo-style rating engine.

## 14.2 Target Tables

```text
player_rating_events
player_rating_history
player_current_ratings
```

## 14.3 Codex Tasks

Implement:

- rating initialization hierarchy;
- deterministic match ordering;
- pre-match player ratings;
- pre-match team ratings;
- expected win probability;
- experience-adjusted K-factor;
- optional disabled-by-default margin factor;
- equal team-delta allocation to players;
- post-match ratings;
- match count state;
- snapshot history;
- current rating;
- rating reliability;
- source-versus-analytical comparison.

## 14.4 Critical Design Requirement

No future match may affect an earlier rating event.

The engine shall not calculate all ratings from final aggregate features.

## 14.5 Scaling Approach

Codex shall propose and document a Spark-safe stateful approach.

Prohibited:

```text
collecting the full 250K match history to the driver
```

Acceptable approaches include:

- deterministic date/batch iteration with distributed state joins;
- controlled monthly state updates;
- another scalable method approved by the instructor.

## 14.6 Required Formula Tests

Test known examples for:

- equal ratings;
- favorite wins;
- underdog wins;
- provisional player;
- experienced player;
- zero-sum team delta;
- player initialization;
- repeat execution;
- same-date match tie-breaking;
- rating reliability.

## 14.7 Validation Outputs

Publish:

```text
rating arithmetic failures
duplicate rating events
rating distribution
correlation with supplied rating
mean absolute difference
rating baseline Brier score
rating baseline log loss
```

Only publish metrics actually computed.

## 14.8 Acceptance Gate

Phase 5 is complete when:

- exact fixture ratings match expected values;
- chronological leakage tests pass;
- deterministic rerun passes;
- current ratings equal latest rating history;
- the 5K rating run completes;
- tests pass.

Do not proceed to player scoring until rating validation is accepted.

---

# 15. Phase 6 — Player Features and Development Analytics

## 15.1 Objective

Create reusable player-level performance, consistency, recency, and development features.

## 15.2 Target Tables

```text
player_performance_features
player_development_features
```

## 15.3 Codex Tasks

Implement evidence windows:

```text
career
trailing_365
trailing_180
trailing_90
```

Implement:

- match volume;
- wins and losses;
- game performance;
- points and margins;
- opponent strength;
- strength of schedule;
- observed minus expected performance;
- upset and favorite-loss measures;
- recency-weighted performance;
- partner diversity;
- primary-partner concentration;
- consistency;
- negative-tail measures;
- rating trend;
- assessment trend;
- confidence trend;
- activity and experience growth;
- development momentum.

## 15.4 Feature Registry

Create a feature registry in configuration or code containing:

```text
feature_name
description
source
grain
window
calculation
direction
minimum_evidence
null_behavior
version
```

Do not duplicate feature formulas across scorecards and model code.

## 15.5 Required Tests

Test:

- each evidence window;
- no evidence;
- one match;
- minimum-sample behavior;
- strength of schedule;
- actual-minus-expected calculation;
- recency weighting;
- trend slope;
- consistency;
- null handling;
- no future evidence.

## 15.6 Acceptance Gate

Phase 6 is complete when:

- player feature tables build for 5K;
- all feature definitions are documented;
- no scorecard weights are embedded in features;
- low-evidence behavior is visible;
- leakage tests pass;
- tests pass.

---

# 16. Phase 7 — Team and Partnership Features

## 16.1 Objective

Create persistent-team and partnership analytical products.

## 16.2 Target Tables

```text
team_performance_features
partnership_effectiveness
```

## 16.3 Codex Tasks

Implement:

- team match volume;
- observed win percentage;
- shrinkage-adjusted win rate;
- game and point performance;
- strength of schedule;
- observed minus expected performance;
- recent form;
- consistency;
- close-match and deciding-game performance;
- partnership duration;
- membership overlap;
- shared match volume;
- recent activity;
- performance relative to individual player strength;
- partnership synergy proxy;
- evidence reliability.

## 16.4 Candidate and Non-Candidate Separation

Persistent valid teams:

```text
candidate attribution allowed
```

Unresolved canonical pairs:

```text
analytical only
candidate attribution prohibited
```

## 16.5 Required Tests

Test:

- raw win rate;
- shrinkage win rate;
- expected performance;
- synergy residual;
- continuity;
- inactive partnership;
- dissolved team;
- unresolved pair;
- low evidence;
- player-order invariance.

## 16.6 Acceptance Gate

Phase 7 is complete when:

- valid team features reconcile to resolved teams;
- unresolved pairs are not candidates;
- partnership performance and continuity are separate;
- low-sample teams are not unfairly promoted by raw win percentage;
- tests pass.

---

# 17. Phase 8 — Data Quality Confidence

## 17.1 Objective

Create explicit evidence-quality scores for players and teams.

## 17.2 Target Table

```text
entity_data_quality_confidence
```

## 17.3 Codex Tasks

Implement configurable components:

```text
identity_integrity
relationship_integrity
match_structure_integrity
game_score_integrity
rating_coverage
match_volume_coverage
recency_coverage
team_resolution_coverage
source_quality_score
```

Create:

```text
data_quality_confidence_score
quality_confidence_band
critical_quality_issue_count
warning_quality_issue_count
material_limitation_text
```

## 17.4 Rules

- critical identity or relationship failures may make a candidate ineligible;
- warnings reduce confidence;
- missing evidence shall not silently become high confidence;
- the formula shall be transparent and configured.

## 17.5 Required Tests

Test:

- complete evidence;
- limited match volume;
- stale activity;
- unresolved team history;
- critical relationship failure;
- missing source quality score;
- confidence band boundaries.

## 17.6 Acceptance Gate

Phase 8 is complete when:

- each candidate player and team has a confidence row;
- critical failures are separately identifiable;
- quality scores are reproducible;
- confidence is not mixed with performance;
- tests pass.

---

# 18. Phase 9 — Match Outcome Prediction

## 18.1 Objective

Publish the required analytical-rating probability baseline and, where enabled, a transparent challenger model.

## 18.2 Target Tables

```text
match_outcome_training_set
match_outcome_predictions
match_model_metrics
```

## 18.3 Required Baseline

Implement:

```text
rating_expected_probability
```

from pre-match analytical ratings.

## 18.4 Optional Challenger

Recommended first challenger:

```text
Spark MLlib logistic regression
```

Candidate features shall be time-valid differences between the two sides.

## 18.5 Time-Based Splits

Use:

```text
train
validation
test
```

in chronological order.

Random match splitting is prohibited.

## 18.6 Required Metrics

```text
accuracy
precision
recall
F1
ROC AUC
log loss
Brier score
calibration by probability band
```

Compare:

- source-rating baseline where available;
- analytical-rating baseline;
- logistic regression;
- optional approved challenger.

## 18.7 Model Promotion Rule

Do not make the ML model the primary match prediction merely because accuracy is marginally higher.

Prefer:

- calibration;
- Brier score;
- log loss;
- time stability;
- interpretability.

## 18.8 Required Tests

Test:

- training row symmetry;
- deterministic team-A assignment;
- feature-time validity;
- training-only preprocessing;
- time split;
- repeatable coefficients;
- prediction probability bounds;
- metric calculations;
- disabled-model behavior.

## 18.9 Acceptance Gate

Phase 9 is complete when:

- rating baseline metrics publish;
- no leakage is detected;
- optional model metrics are actual;
- model configuration and version are recorded;
- a model card draft exists;
- tests pass.

---

# 19. Phase 10 — Feature Normalization and Player Scorecards

## 19.1 Objective

Convert player features into transparent player evaluation and development scorecards.

## 19.2 Target Tables

```text
player_evaluation_scorecards
national_player_rankings
```

Update or use:

```text
player_development_features
```

for development rankings.

## 19.3 Codex Tasks

Implement:

- peer-group definition;
- percentile-rank normalization;
- feature direction;
- minimum-evidence behavior;
- missing component handling;
- component weights;
- raw player score;
- confidence adjustment;
- national ranks;
- gender/category ranks where supported;
- development-potential score and rank;
- deterministic tie-breakers;
- top-strength and risk reason codes.

## 19.4 Separation Requirements

Publish separately:

```text
source rating
analytical rating
raw feature values
normalized feature values
component scores
raw composite score
confidence score
confidence-adjusted score
rank
```

## 19.5 Required Tests

Test:

- normalization direction;
- percentile behavior;
- peer groups;
- missing component reweighting;
- confidence adjustment;
- tie-breaking;
- rank reset by group;
- top-25 filtering;
- development rank behavior.

## 19.6 Acceptance Gate

Phase 10 is complete when:

- player rankings publish for USA and Canada;
- score components reconcile to the composite;
- score range is valid;
- low-confidence players are visible;
- no score is based solely on supplied rating;
- tests pass.

---

# 20. Phase 11 — Team Selection Scorecards and Eligibility

## 20.1 Objective

Build the candidate universe and calculate transparent team-selection scores.

## 20.2 Target Tables

```text
team_selection_scorecards
olympic_team_candidates
```

## 20.3 Codex Tasks

Implement team eligibility:

- existing team ID;
- valid country;
- supported category;
- active team;
- exactly two valid players;
- active memberships;
- valid date range;
- no critical relationship failure;
- no fabricated pair.

Implement selection components:

- partnership performance;
- analytical team rating;
- match prediction strength;
- combined player strength;
- strength of schedule;
- continuity;
- consistency and pressure proxy;
- recent form;
- evidence confidence;
- data quality confidence;
- risk penalty.

## 20.4 Eligibility Output

Publish:

```text
eligibility_status
eligibility_reason_codes
evidence_sufficiency_status
candidate_attribution_allowed_flag
```

Do not combine “eligible” with “high score.”

## 20.5 Required Tests

Test:

- valid candidate;
- inactive team;
- dissolved team;
- wrong country;
- category mismatch;
- invalid composition;
- unresolved pair;
- low evidence but eligible;
- critical quality failure;
- score formula;
- confidence adjustment.

## 20.6 Acceptance Gate

Phase 11 is complete when:

- every persistent team is classified;
- eligible candidates are correctly grouped by country/category;
- score components sum correctly;
- invalid teams cannot rank as candidates;
- tests pass.

---

# 21. Phase 12 — Olympic Candidate Rankings and Recommendations

## 21.1 Objective

Rank eligible existing teams and assign configurable recommendation statuses.

## 21.2 Target Table

```text
olympic_team_recommendations
```

## 21.3 Codex Tasks

Implement:

- country/category ranks;
- deterministic tie-breaking;
- primary count;
- alternate count;
- watchlist count;
- score gaps;
- closest alternative;
- authoritative-release flag;
- optional approved cross-category roster constraints;
- infeasibility reporting.

## 21.4 Baseline Recommendation Statuses

```text
PRIMARY
ALTERNATE
WATCHLIST
RANKED_CANDIDATE
```

## 21.5 Constraints

Do not hard-code a roster size not specified in configuration.

Do not apply cross-category player-overlap rules unless approved.

Do not generate new teams.

## 21.6 Required Tests

Test:

- status boundaries;
- insufficient candidate count;
- deterministic ties;
- no duplicate status row;
- valid team IDs;
- score gap;
- 5K/50K non-authoritative flag;
- 250K authoritative flag;
- optional constraint conflict.

## 21.7 Acceptance Gate

Phase 12 is complete when:

- candidate rankings exist for each supported country/category represented in the data;
- primary and alternate outputs use valid team IDs;
- counts match configuration;
- shortfalls are explicit;
- recommendations are reproducible;
- tests pass.

---

# 22. Phase 13 — Sensitivity and Explainability

## 22.1 Objective

Demonstrate recommendation stability and generate evidence-based explanations.

## 22.2 Target Tables

```text
selection_sensitivity_results
recommendation_explanations
```

## 22.3 Codex Tasks

Implement scenarios:

```text
BALANCED
PERFORMANCE_HEAVY
RATING_HEAVY
RECENT_FORM_HEAVY
CONFIDENCE_CONSERVATIVE
DEVELOPMENT_ORIENTED
```

Calculate:

```text
scenario_rank
scenario_score
primary_selection_flag
rank_range
selection_frequency
recommendation_stability_score
```

Generate template-based explanations containing:

- headline rationale;
- top strengths;
- material weaknesses;
- evidence volume;
- confidence band;
- quality limitations;
- closest alternative;
- score gap;
- sensitivity stability.

## 22.4 Narrative Rules

Narratives shall be generated only from actual data.

Do not create unsupported scouting language.

Do not imply causality or psychological chemistry.

## 22.5 Required Tests

Test:

- scenario weight validation;
- rank range;
- selection frequency;
- stability score;
- explanation factor selection;
- missing evidence narrative;
- low-confidence narrative;
- closest-alternative logic.

## 22.6 Acceptance Gate

Phase 13 is complete when:

- scenario scores are reproducible;
- recommendation stability is visible;
- every primary and alternate has an explanation;
- explanations match actual component evidence;
- tests pass.

---

# 23. Phase 14 — Workflow Assembly and Databricks Deployment

## 23.1 Objective

Wire all implemented modules into one parameterized Databricks Silver-to-Gold Workflow.

## 23.2 Workflow Tasks

Recommended tasks:

```text
01_resolve_configuration
02_validate_silver_upstream
03_build_competition_foundation
04_build_analytical_ratings
05_build_player_features
06_build_team_features
07_build_match_outcome_products
08_build_scorecards_and_rankings
09_build_olympic_candidates
10_build_sensitivity_and_explanations
11_validate_and_publish
12_publish_run_summary
```

## 23.3 Workflow Parameter

Required:

```text
release_name
```

Optional:

```text
analysis_as_of_date
scoring_scenario
model_enabled
```

## 23.4 Bundle Tasks

Codex shall:

1. inspect the existing root `databricks.yml`;
2. add the resource file through the existing include pattern;
3. validate target-specific variables;
4. reuse existing workspace path conventions;
5. avoid creating a second competing bundle;
6. validate the bundle;
7. deploy to the approved development target;
8. document UI and CLI execution methods.

## 23.5 Required Commands

Codex may use, where the environment is configured:

```bash
databricks bundle validate -t dev
databricks bundle deploy -t dev
```

Do not claim validation or deployment success unless commands complete successfully.

## 23.6 Workflow Tests

Validate:

- parameter propagation;
- task dependency graph;
- release schema isolation;
- failure propagation;
- retry settings;
- run context propagation;
- shared run ID;
- final success status;
- repair-run implications.

## 23.7 Acceptance Gate

Phase 14 is complete when:

- bundle validation succeeds;
- workflow deployment succeeds or the exact blocking issue is documented;
- the 5K workflow can be launched;
- tasks use the same Gold run context;
- failure prevents false success;
- execution instructions are documented.

---

# 24. Phase 15 — Release Validation and Acceptance

## 24.1 Objective

Run progressively larger releases and prove the implementation works.

## 24.2 Release Order

```text
napa_5k
→ napa_50k
→ napa_250k
```

## 24.3 5K Acceptance

Required:

- full workflow success;
- all enabled Gold tables exist;
- no critical quality failures;
- rating arithmetic passes;
- leakage tests pass;
- candidate universe builds;
- recommendations publish where data supports them;
- deterministic rerun passes.

## 24.4 50K Acceptance

Required:

- full workflow success;
- performance observations recorded;
- feature distributions reviewed;
- team-resolution rate reviewed;
- model metrics reviewed;
- rankings reviewed for anomalies;
- recommendations are stable enough to proceed;
- no critical reconciliation failure.

## 24.5 250K Acceptance

Required:

- full workflow success;
- authoritative flag is true;
- required tables and views publish;
- top-25 player rankings publish;
- supported country/category candidate groups publish;
- primary and alternates use valid team IDs;
- sensitivity completes;
- confidence and quality outputs publish;
- reconciliation passes;
- final run summary is complete.

## 24.6 Deterministic Rerun

At minimum, rerun 5K using the same:

```text
Silver input
analysis date
configuration
seed
code version
```

Compare:

- row counts;
- business hashes;
- ratings;
- component scores;
- ranks;
- recommendation statuses;
- model coefficients within tolerance.

## 24.7 Performance Evidence

Record actual:

```text
runtime by task
row counts
shuffle or memory concerns
largest tables
rating engine scaling behavior
model training duration
publication duration
```

Do not invent performance claims.

## 24.8 Acceptance Gate

Phase 15 is complete only when actual evidence is recorded for each executed release and all critical failures are resolved or explicitly accepted.

---

# 25. Phase 16 — Documentation and Final Handoff

## 25.1 Objective

Complete the implementation package for operation, review, and future maintenance.

## 25.2 Required Documents

Create or finalize:

```text
docs/data_dictionary_gold.md
docs/gold_lineage.md
docs/analytical_methodology.md
docs/model_card_match_outcomes.md
docs/selection_methodology.md
docs/quality_rules_gold.md
docs/runbook_gold.md
docs/gold_implementation_completion_report.md
```

## 25.3 Required Documentation Content

### Data Dictionary

- table;
- grain;
- primary key;
- column;
- type;
- definition;
- source;
- null behavior;
- quality rule.

### Analytical Methodology

- rating method;
- initialization;
- expected probability;
- update formula;
- reliability;
- evidence windows;
- strength of schedule;
- recency;
- consistency;
- development features.

### Model Card

- model purpose;
- training population;
- features;
- time split;
- metrics;
- baseline comparison;
- limitations;
- leakage controls;
- explainability.

### Selection Methodology

- candidate universe;
- eligibility;
- component scores;
- weights;
- confidence adjustment;
- risk penalty;
- tie-breaking;
- recommendation counts;
- sensitivity;
- human review.

### Runbook

- prerequisites;
- deployment;
- release execution;
- monitoring;
- reviewer queries;
- failure investigation;
- repair-run guidance;
- rollback or last-success behavior.

## 25.4 Acceptance Gate

Phase 16 is complete when:

- documentation matches the implemented code;
- all commands and table names are accurate;
- actual test results are included;
- assumptions and deviations are documented;
- final handoff report is complete.

---

# 26. Cross-Phase Test Strategy

## 26.1 Test Layers

```text
Unit tests
Integration tests
Acceptance tests
Backtests
Data quality tests
Reconciliation tests
Determinism tests
Leakage tests
```

## 26.2 Unit Tests

Focus on pure logic:

- IDs and canonical keys;
- match outcome derivation;
- game metrics;
- rating formulas;
- K-factor;
- reliability;
- recency weights;
- trend slopes;
- normalization;
- score formulas;
- eligibility;
- rank tie-breaking;
- recommendation statuses;
- sensitivity.

## 26.3 Integration Tests

Use deterministic Spark fixtures to validate:

- joins;
- grains;
- as-of logic;
- team resolution;
- rating sequence;
- feature windows;
- candidate assembly;
- stage and publish.

## 26.4 Acceptance Tests

Run against actual 5K, 50K, and 250K Silver schemas as available.

## 26.5 Leakage Tests

Required in ratings and modeling:

```text
feature_timestamp < outcome_timestamp
pre_match_rating excludes target match
train preprocessing excludes validation/test
analysis date excludes later matches
```

## 26.6 Reconciliation Tests

Required:

- Silver matches to Gold matches;
- match sides;
- player participation;
- team resolution;
- rating events;
- candidate classification;
- recommendation counts.

## 26.7 Determinism Tests

Compare business hashes and ordered outputs across identical runs.

---

# 27. Execution Gates

| Gate | Must Be True Before Proceeding |
|---|---|
| Gate 0 | Physical Silver contract documented |
| Gate 1 | All release configurations resolve |
| Gate 2 | Operational logging and publication tested |
| Gate 3 | Competition facts reconcile |
| Gate 4 | Team resolution is explainable |
| Gate 5 | Rating engine is exact, deterministic, and leakage-free |
| Gate 6 | Player features are time-valid |
| Gate 7 | Team features exclude fabricated candidates |
| Gate 8 | Quality confidence is separate from performance |
| Gate 9 | Match probability baseline is validated |
| Gate 10 | Player scorecards reconcile |
| Gate 11 | Team eligibility and scores reconcile |
| Gate 12 | Recommendations use valid team IDs |
| Gate 13 | Sensitivity and explanations match evidence |
| Gate 14 | Databricks Workflow deploys |
| Gate 15 | 5K, 50K, and 250K acceptance evidence is recorded |
| Gate 16 | Documentation matches implementation |

A failed gate shall block downstream work unless the instructor explicitly accepts the risk.

---

# 28. Recommended Codex Session Sequence

Use the following sequence.

## Session 1

```text
Phase 0 only
```

Review the discovery report before proceeding.

## Session 2

```text
Phases 1 and 2
```

Configuration, context, operations, and publication framework.

## Session 3

```text
Phase 3 only
```

Competition foundation.

## Session 4

```text
Phase 4 only
```

Persistent-team resolution.

## Session 5

```text
Phase 5 only
```

Rating engine.

This should be a dedicated session because of complexity and leakage risk.

## Session 6

```text
Phase 6
```

Player features.

## Session 7

```text
Phases 7 and 8
```

Team features and confidence.

## Session 8

```text
Phase 9
```

Match outcome baseline and optional model.

## Session 9

```text
Phase 10
```

Player scorecards and rankings.

## Session 10

```text
Phases 11 and 12
```

Team scorecards, eligibility, candidate rankings, and recommendations.

## Session 11

```text
Phase 13
```

Sensitivity and explanations.

## Session 12

```text
Phase 14
```

Workflow and bundle deployment.

## Session 13

```text
Phase 15
```

Release acceptance.

## Session 14

```text
Phase 16
```

Documentation and final handoff.

---

# 29. Master Codex Prompt

Use this prompt at the beginning of every implementation session.

```markdown
You are acting as a Senior Principal Data Engineer, Sports Analytics
Data Scientist, and Databricks Solution Architect.

Your task is to implement the NAPA Silver-to-Gold instructor reference
pipeline in the existing repository.

Authoritative documents:

1. NAPA_Silver_to_Gold_Layer_Engineering_Spec_v1.0.md
2. NAPA_Silver_to_Gold_Codex_Implementation_Plan_v1.0.md
3. NAPA_Bronze_to_Silver_Spec_v1.1.md
4. Existing repository AGENTS.md files and coding standards

Current implementation phase:

<INSERT PHASE NUMBER AND NAME>

Important operating rules:

- Inspect the repository and applicable AGENTS.md files before editing.
- Inspect actual Silver schemas and existing utilities before assuming fields.
- The physical Silver schema is authoritative.
- Do not invent fields, code values, category mappings, or business rules.
- Read only from the selected release-specific Silver schema.
- Do not read Raw or Bronze from Gold code.
- Do not access or infer hidden tournament simulation parameters.
- Do not create synthetic or ad-hoc candidate teams.
- Use valid existing team IDs for recommendations.
- Use deterministic processing, sorting, ranking, seeds, and hashes.
- Prevent future-data leakage in ratings, features, and models.
- Keep Databricks notebooks or entry scripts thin.
- Put reusable business logic in tested Python modules.
- Add or update tests with each implementation change.
- Run the tests available in this environment.
- Do not claim a test, Databricks run, model result, or deployment succeeded
  unless it actually ran successfully.
- Do not continue beyond the current phase.
- Preserve working Raw-to-Bronze and Bronze-to-Silver behavior.

Before coding, report:

1. files and modules relevant to this phase;
2. existing patterns you will reuse;
3. actual source columns required;
4. assumptions or conflicts;
5. the bounded implementation plan for this phase.

Then implement the phase.

At the end, provide a completion report containing:

1. files created or changed;
2. behavior implemented;
3. configuration added or changed;
4. tests added;
5. exact tests and commands run;
6. actual results;
7. unresolved issues;
8. assumptions requiring instructor approval;
9. divergences from the specifications;
10. recommended next phase.

Stop after completing the current phase.
```

---

# 30. Phase Prompt Templates

## 30.1 Phase 0 Prompt

```markdown
Execute Phase 0 — Repository and Silver Contract Discovery.

Do not implement Gold business transformations.

Inspect the repository, Databricks bundle, environment configuration,
existing pipeline modules, tests, operations tables, and actual Silver
schemas.

Create:

- docs/gold_discovery_report.md
- docs/gold_source_contract.md

Document actual columns, types, keys, code values, derivations, missing
concepts, team-ID availability, country logic, category logic, and status
logic.

Run existing tests and schema inspection commands where possible.

Stop after the discovery report and source contract are complete.
```

## 30.2 Phase 1–2 Prompt

```markdown
Execute Phases 1 and 2 only:

- Gold configuration and runtime context
- Operations, logging, and publication framework

Do not implement competition, rating, feature, model, scorecard, or
recommendation logic.

Reuse existing common pipeline patterns where possible.

Add complete unit tests for configuration validation, analysis-date
resolution, run registration, failure logging, stage publication, and
record-hash determinism.

Stop after the operational foundation is tested.
```

## 30.3 Phase 3 Prompt

```markdown
Execute Phase 3 — Competition Foundation only.

Build:

- competition_match_sides
- competition_player_matches

Use actual Silver schemas. Derive match and game outcomes, player
participation, partner/opponent context, metrics, cutoff behavior,
exclusions, quality checks, and reconciliation.

Do not implement persistent-team inference beyond a nullable direct field.
Do not implement ratings or scorecards.

Use deterministic fixtures and test all invalid structural cases.

Stop when the competition foundation passes its gate.
```

## 30.4 Phase 4 Prompt

```markdown
Execute Phase 4 — Persistent-Team Resolution only.

Implement the approved hierarchy:

1. direct team ID;
2. active membership pair at match date;
3. unique historical pair;
4. unresolved;
5. ambiguous.

Do not create synthetic team IDs.

Build resolved_match_teams and publish resolution counts and confidence.

Add unit and integration tests for every resolution path.

Stop after the team-resolution gate passes.
```

## 30.5 Phase 5 Prompt

```markdown
Execute Phase 5 — Analytical Rating Engine only.

Implement the configured chronological doubles Elo-style rating method.

Build:

- player_rating_events
- player_rating_history
- player_current_ratings

Use only pre-match information. Prevent future leakage. Use deterministic
match ordering. Do not collect the full match history to the driver.

Implement exact formula tests, chronological tests, determinism tests,
rating reconciliation, reliability, and source-rating comparison.

Do not implement player scorecards or recommendations.

Stop after the rating gate passes.
```

## 30.6 Phase 6 Prompt

```markdown
Execute Phase 6 — Player Features and Development Analytics only.

Build:

- player_performance_features
- player_development_features

Implement configured evidence windows, recency, opponent adjustment,
strength of schedule, consistency, trends, partner context, and evidence
status.

Create or update the feature registry.

Do not implement composite scorecards.

Add time-valid unit and integration tests.

Stop after the player-feature gate passes.
```

## 30.7 Phase 7–8 Prompt

```markdown
Execute Phases 7 and 8 only:

- Team and partnership features
- Entity data quality confidence

Build:

- team_performance_features
- partnership_effectiveness
- entity_data_quality_confidence

Keep performance and confidence separate. Only persistent valid team IDs
may be candidate-attributable.

Implement shrinkage-adjusted performance, continuity, synergy proxy,
evidence reliability, quality components, and limitation flags.

Do not implement final team scores or recommendations.

Stop after both gates pass.
```

## 30.8 Phase 9 Prompt

```markdown
Execute Phase 9 — Match Outcome Prediction only.

Build the analytical-rating probability baseline and its time-based
evaluation.

Where enabled, add Spark MLlib logistic regression as a transparent
challenger.

Build:

- match_outcome_training_set
- match_outcome_predictions
- match_model_metrics

Use chronological train, validation, and test splits. Prevent leakage.
Compare actual calibration, Brier score, log loss, accuracy, and AUC.

Do not promote a model without evidence.

Stop after the match-model gate passes.
```

## 30.9 Phase 10 Prompt

```markdown
Execute Phase 10 — Feature Normalization and Player Scorecards only.

Build:

- player_evaluation_scorecards
- national_player_rankings

Also calculate development-potential rankings from the existing
development features.

Publish raw features, normalized components, weights, raw scores,
confidence-adjusted scores, deterministic ranks, strengths, and risks.

Do not implement team recommendations.

Stop after the player-scorecard gate passes.
```

## 30.10 Phase 11–12 Prompt

```markdown
Execute Phases 11 and 12 only:

- Team selection scorecards and eligibility
- Olympic candidate rankings and recommendations

Build:

- team_selection_scorecards
- olympic_team_candidates
- olympic_team_recommendations

Use only valid existing teams. Apply configured country, category,
membership, status, quality, and composition rules.

Assign PRIMARY, ALTERNATE, WATCHLIST, and RANKED_CANDIDATE according to
configuration.

Do not invent roster constraints. Use only constraints explicitly present
in approved configuration.

Stop after recommendations reconcile and all tests pass.
```

## 30.11 Phase 13 Prompt

```markdown
Execute Phase 13 — Sensitivity and Explainability only.

Build:

- selection_sensitivity_results
- recommendation_explanations

Run the approved scorecard scenarios. Calculate stability and selection
frequency.

Generate template-based explanations from actual component evidence.
Do not generate unsupported scouting or psychological claims.

Stop after every primary and alternate recommendation has a validated
explanation.
```

## 30.12 Phase 14 Prompt

```markdown
Execute Phase 14 — Workflow Assembly and Databricks Deployment only.

Inspect the existing root databricks.yml and bundle conventions.

Wire the completed modules into one release-parameterized Silver-to-Gold
Workflow. Do not duplicate the bundle.

Validate and deploy to the approved development target where credentials
and workspace access are available.

Report exact commands and actual results. If deployment cannot run,
document the exact blocker and still complete static validation.

Stop after the workflow gate.
```

## 30.13 Phase 15 Prompt

```markdown
Execute Phase 15 — Release Validation and Acceptance.

Run in order:

1. napa_5k
2. napa_50k
3. napa_250k

Do not proceed to a larger release while critical failures remain in the
smaller release.

Record actual run IDs, task results, row counts, quality results,
reconciliation, model metrics, recommendation counts, runtime, and
performance observations.

Perform an identical-input deterministic rerun at least for napa_5k.

Do not change methodology merely to make a release pass without documenting
the issue.

Stop after the acceptance report is complete.
```

## 30.14 Phase 16 Prompt

```markdown
Execute Phase 16 — Documentation and Final Handoff.

Complete the Gold data dictionary, lineage, analytical methodology, model
card, selection methodology, quality rules, runbook, and implementation
completion report.

Ensure all names, commands, schemas, tables, parameters, metrics, and test
results match the actual implementation.

Do not include fabricated execution evidence.

Stop after the final handoff package is complete.
```

---

# 31. Progress Tracking Checklist

## Phase 0 — Discovery

- [ ] Repository inspected
- [ ] `AGENTS.md` files read
- [ ] Databricks bundle inspected
- [ ] Environment YAML inspected
- [ ] Actual Silver schemas documented
- [ ] Country values documented
- [ ] Gender values documented
- [ ] Team categories documented
- [ ] Status values documented
- [ ] Persistent team ID availability documented
- [ ] Discovery report accepted

## Phase 1 — Configuration

- [ ] All Gold YAML files created
- [ ] Runtime context implemented
- [ ] Analysis date implemented
- [ ] Configuration hash implemented
- [ ] 5K configuration resolves
- [ ] 50K configuration resolves
- [ ] 250K configuration resolves
- [ ] Invalid configuration tests pass

## Phase 2 — Operations

- [ ] Pipeline run logging
- [ ] Table run logging
- [ ] Quality logging
- [ ] Reconciliation logging
- [ ] Model run logging
- [ ] Recommendation run logging
- [ ] Stage-to-Gold publication
- [ ] Failure behavior tested

## Phase 3 — Competition

- [ ] Match sides
- [ ] Player matches
- [ ] Game metrics
- [ ] Point metrics
- [ ] Outcome checks
- [ ] Participation checks
- [ ] Exclusion reasons
- [ ] Reconciliation
- [ ] 5K build passes

## Phase 4 — Team Resolution

- [ ] Direct resolution
- [ ] Active-pair resolution
- [ ] Historical-pair resolution
- [ ] Ambiguous status
- [ ] Unresolved status
- [ ] Confidence
- [ ] Resolution reconciliation
- [ ] No synthetic IDs

## Phase 5 — Ratings

- [ ] Initialization
- [ ] Match ordering
- [ ] Expected probability
- [ ] K-factor
- [ ] Rating event
- [ ] History
- [ ] Current ratings
- [ ] Reliability
- [ ] Arithmetic tests
- [ ] Leakage tests
- [ ] Determinism test
- [ ] 5K rating build

## Phase 6 — Player Features

- [ ] Evidence windows
- [ ] Performance
- [ ] Opponent adjustment
- [ ] Strength of schedule
- [ ] Recency
- [ ] Consistency
- [ ] Partner context
- [ ] Rating trend
- [ ] Assessment trend
- [ ] Development momentum
- [ ] Feature registry
- [ ] Tests pass

## Phase 7 — Team Features

- [ ] Persistent team metrics
- [ ] Adjusted win rate
- [ ] Partnership continuity
- [ ] Synergy proxy
- [ ] Recent form
- [ ] Consistency
- [ ] Evidence reliability
- [ ] Unresolved pair separation
- [ ] Tests pass

## Phase 8 — Confidence

- [ ] Player quality confidence
- [ ] Team quality confidence
- [ ] Critical flags
- [ ] Warning flags
- [ ] Limitation text
- [ ] Confidence bands
- [ ] Tests pass

## Phase 9 — Match Outcomes

- [ ] Rating baseline predictions
- [ ] Time-based split
- [ ] Optional logistic model
- [ ] Calibration
- [ ] Brier score
- [ ] Log loss
- [ ] AUC
- [ ] Model version
- [ ] Model card draft
- [ ] Leakage tests

## Phase 10 — Player Scores

- [ ] Normalization
- [ ] Component scores
- [ ] Raw player score
- [ ] Confidence adjustment
- [ ] National ranks
- [ ] Top-25 view
- [ ] Development ranks
- [ ] Tie-breaking
- [ ] Tests pass

## Phase 11 — Team Scores

- [ ] Eligibility classification
- [ ] Reason codes
- [ ] Team component scores
- [ ] Confidence adjustment
- [ ] Risk penalty
- [ ] Country/category grouping
- [ ] Tests pass

## Phase 12 — Recommendations

- [ ] Candidate ranks
- [ ] Primary
- [ ] Alternates
- [ ] Watchlist
- [ ] Score gaps
- [ ] Valid team IDs
- [ ] Authoritative-release flag
- [ ] Recommendation counts reconcile
- [ ] Tests pass

## Phase 13 — Sensitivity

- [ ] All approved scenarios
- [ ] Rank range
- [ ] Selection frequency
- [ ] Stability score
- [ ] Primary explanations
- [ ] Alternate explanations
- [ ] Closest alternatives
- [ ] Tests pass

## Phase 14 — Workflow

- [ ] Workflow resource
- [ ] Bundle include
- [ ] Release parameter
- [ ] Task dependencies
- [ ] Shared run context
- [ ] Bundle validation
- [ ] Development deployment
- [ ] UI run instructions
- [ ] CLI run instructions

## Phase 15 — Acceptance

- [ ] 5K complete
- [ ] 5K deterministic rerun
- [ ] 50K complete
- [ ] 250K complete
- [ ] Quality passes
- [ ] Reconciliation passes
- [ ] Model metrics recorded
- [ ] Recommendations recorded
- [ ] Runtime recorded
- [ ] Performance issues documented

## Phase 16 — Documentation

- [ ] Data dictionary
- [ ] Lineage
- [ ] Analytical methodology
- [ ] Model card
- [ ] Selection methodology
- [ ] Quality rules
- [ ] Runbook
- [ ] Completion report
- [ ] Assumptions
- [ ] Deviations
- [ ] Final execution instructions

---

# 32. Completion Report Template

Codex shall use this structure at the end of every phase.

```markdown
# Phase Completion Report

## Phase

<phase number and name>

## Status

SUCCEEDED | PARTIALLY_COMPLETED | BLOCKED | FAILED

## Scope Completed

- ...

## Files Created

- ...

## Files Modified

- ...

## Configuration Changes

- ...

## Actual Source Contract Used

- ...

## Implementation Details

- ...

## Tests Added

- ...

## Commands Run

```bash
...
```

## Actual Test Results

- ...

## Databricks Commands Run

```bash
...
```

## Actual Databricks Results

- ...

## Data Quality or Reconciliation Results

- ...

## Assumptions

- ...

## Instructor Decisions Required

- ...

## Deviations from Specification

- ...

## Known Limitations

- ...

## Recommended Next Phase

- ...

## Commit Recommendation

```text
<suggested commit message>
```
```

---

# 33. Known Risks and Mitigations

## 33.1 Match Tables May Lack Persistent Team IDs

**Risk:** Historical match performance cannot be directly attributed to `teams.id`.

**Mitigation:**

- use the approved resolution hierarchy;
- retain unresolved status;
- do not create synthetic IDs;
- calculate player analytics independently;
- measure attribution coverage.

## 33.2 Rating Engine Scalability

**Risk:** Chronological state updates may be implemented with a driver-bound loop.

**Mitigation:**

- design the stateful approach before coding;
- batch deterministically by date or release sequence;
- keep state in Spark-compatible structures;
- test 5K and 50K before 250K;
- publish runtime evidence.

## 33.3 Temporal Leakage

**Risk:** Final ratings or aggregate future features may enter historical match predictions.

**Mitigation:**

- explicit as-of joins;
- pre-match rating events;
- time-based tests;
- chronological model split;
- leakage audit queries.

## 33.4 Sparse Team Histories

**Risk:** Small-sample teams rank too highly.

**Mitigation:**

- adjusted win rate;
- confidence adjustment;
- evidence bands;
- small-sample risk;
- sensitivity analysis.

## 33.5 Incomplete Category or Gender Data

**Risk:** Olympic category eligibility cannot be validated.

**Mitigation:**

- inspect actual values in Phase 0;
- externalize mappings;
- use `REVIEW_REQUIRED` where unresolved;
- do not infer unsupported gender or category values.

## 33.6 Scorecard Weights Become Hidden Answers

**Risk:** Instructor reference weights could be treated as the only valid student solution.

**Mitigation:**

- keep weights configurable;
- label them as reference defaults;
- publish raw components;
- run sensitivity scenarios;
- document that alternate justified methods are possible.

## 33.7 Model Adds Complexity Without Value

**Risk:** ML model is less calibrated or less explainable than ratings.

**Mitigation:**

- require the rating baseline;
- use logistic regression first;
- promote only with time-based evidence;
- allow `model_enabled=false`;
- preserve baseline output.

## 33.8 Workflow Deployment Differs from Local Tests

**Risk:** imports, paths, permissions, or serverless behavior fail in Databricks.

**Mitigation:**

- keep entry points thin;
- validate package/import behavior early;
- use bundle configuration consistently;
- perform a 5K Workflow run before scaling;
- record exact failures.

## 33.9 Free Edition Resource Limits

**Risk:** 250K processing or modeling exceeds available compute.

**Mitigation:**

- persist reusable foundations carefully;
- avoid unnecessary wide joins;
- avoid excessive partitions;
- make optional model disableable;
- separate essential baseline from optional analytics;
- document performance tradeoffs.

---

# 34. Decisions Requiring Instructor Review

The following decisions shall not be silently resolved by Codex.

## 34.1 Source Contract

- accepted country-code mapping;
- accepted gender mapping;
- accepted category mapping;
- accepted active-status values;
- team-country derivation fallback;
- handling of ambiguous historical teams.

## 34.2 Rating Method

- initialization hierarchy;
- default rating;
- K-factor;
- experience bands;
- margin multiplier;
- overall versus category-specific ratings;
- cross-country versus separate rating pools.

## 34.3 Evidence and Confidence

- evidence windows;
- recency half-life;
- minimum sample thresholds;
- confidence formula;
- critical versus warning quality rules.

## 34.4 Match Model

- whether ML modeling is enabled;
- model promotion criteria;
- selected challenger;
- calibration acceptance threshold.

## 34.5 Scorecards

- player component weights;
- team component weights;
- missing-component behavior;
- confidence adjustment;
- risk penalties;
- development-potential weights.

## 34.6 Eligibility and Recommendations

- primary count;
- alternate count;
- watchlist count;
- category definitions;
- cross-category player overlap;
- roster feasibility constraints;
- manual review and override process.

## 34.7 Production Acceptance

- whether 250K is sufficiently stable;
- whether unresolved team coverage is acceptable;
- whether model improvement is material;
- whether sensitivity is acceptable;
- whether recommendations are ready for executive presentation.

---

# 35. Final Definition of Done

The Codex Silver-to-Gold implementation is complete when all of the following are true.

## Architecture

- [ ] One shared codebase supports 5K, 50K, and 250K
- [ ] One parameterized Databricks Workflow is deployed
- [ ] Gold reads only release-specific Silver
- [ ] Shared operations tables are used
- [ ] Full-refresh processing is deterministic
- [ ] 250K is marked authoritative

## Competition Foundation

- [ ] Match sides reconcile
- [ ] Game and point metrics validate
- [ ] Player participation validates
- [ ] Team resolution is implemented
- [ ] Ambiguous and unresolved history remains visible

## Ratings

- [ ] Rating initialization is documented
- [ ] Chronological processing is deterministic
- [ ] Rating events are auditable
- [ ] Current and historical ratings publish
- [ ] Reliability publishes
- [ ] Source and analytical ratings remain separate
- [ ] Arithmetic, determinism, and leakage tests pass

## Player Analytics

- [ ] Performance features publish
- [ ] Consistency features publish
- [ ] Development features publish
- [ ] Player scorecards publish
- [ ] National rankings publish
- [ ] Top-25 views publish
- [ ] Development rankings publish

## Team Analytics

- [ ] Persistent-team features publish
- [ ] Partnership effectiveness publishes
- [ ] Candidate eligibility is explicit
- [ ] Team scorecards publish
- [ ] Candidate rankings publish
- [ ] Only valid existing teams are recommended

## Match Outcomes

- [ ] Rating probability baseline publishes
- [ ] Time-based evaluation publishes
- [ ] Optional model is leakage-free
- [ ] Model metrics are actual
- [ ] Model explanations are documented

## Recommendations

- [ ] Primary recommendations publish
- [ ] Alternate recommendations publish
- [ ] Watchlist publishes
- [ ] Counts match configuration
- [ ] Score gaps publish
- [ ] Sensitivity publishes
- [ ] Explanations match actual evidence
- [ ] Human review fields are available

## Operations and Quality

- [ ] Pipeline and table runs log correctly
- [ ] Quality results log correctly
- [ ] Reconciliation passes
- [ ] Failed runs cannot appear successful
- [ ] Deterministic rerun passes
- [ ] 5K acceptance passes
- [ ] 50K acceptance passes
- [ ] 250K acceptance passes

## Documentation

- [ ] Gold data dictionary is complete
- [ ] Gold lineage is complete
- [ ] Rating methodology is complete
- [ ] Model card is complete
- [ ] Selection methodology is complete
- [ ] Quality rules are complete
- [ ] Runbook is complete
- [ ] Completion report contains actual evidence
- [ ] Assumptions and deviations are documented

---

# Appendix A — Recommended First Codex Instruction

The first implementation request should be Phase 0 only.

```markdown
Read the following documents and inspect the repository before making
changes:

- NAPA_Silver_to_Gold_Layer_Engineering_Spec_v1.0.md
- NAPA_Silver_to_Gold_Codex_Implementation_Plan_v1.0.md
- NAPA_Bronze_to_Silver_Spec_v1.1.md
- all applicable AGENTS.md files

Execute only Phase 0 — Repository and Silver Contract Discovery.

Do not build Gold tables yet.

Inspect the actual Silver schemas, environment configuration, Databricks
bundle, operations utilities, test framework, and repository conventions.

Create:

- docs/gold_discovery_report.md
- docs/gold_source_contract.md

Report actual fields and code values. Do not invent missing fields.
Identify every decision requiring instructor review.

Run existing tests and any safe schema-inspection commands available.

Stop after Phase 0 and provide the required phase completion report.
```

---

# Appendix B — Implementation Philosophy

```text
Discover first.
Build the data contract second.
Build facts before features.
Build ratings before scorecards.
Build confidence separately from performance.
Validate time before modeling.
Establish eligibility before ranking.
Rank before recommending.
Explain every recommendation.
Scale only after smaller releases pass.
Document actual results, not expected results.
```
