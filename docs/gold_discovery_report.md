# Gold Discovery Report

## Scope

This report completes Phase 0 from
`docs/development/napa_silver_to_gold_codex_implementation_plan_v1.md`.

The objective was to verify the current repository, identify the actual Silver
contract available to a future Gold pipeline, and document gaps between the
Databricks-oriented specification and the codebase that exists today.

## Repository Verification Summary

- Repository root inspected: `/home/brett/projects/pickleball-sim`
- Shared agent guidance located: `agents.md`
- Root `AGENTS.md` file expected by the implementation plan is not present.
- Current worktree was clean at the start of Phase 0.
- Python backend is the active implementation surface.
- The student-facing Silver export contract is implemented in:
  - `backend/app/exports/student_dataset/projection.py`
  - `backend/app/exports/student_dataset/queries.py`
  - `backend/app/exports/student_dataset/writer.py`
  - `backend/app/exports/student_dataset/release_windows.py`

## Current Pipeline Architecture

The repository currently supports a local Python/SQLAlchemy pipeline, not a
Databricks-native pipeline.

Observed flow:

1. ORM models define the operational schema in `backend/app/models`.
2. Monthly simulation batches are generated through the backend generation
   services.
3. Student-facing Silver-style Parquet exports are produced by the
   `student_dataset` export package.
4. Release manifests are written to each export folder.
5. Release metadata can also be tracked in `student_dataset_releases`.

There is no checked-in Gold transformation package, Databricks bundle, or
serverless workflow definition yet.

## Package and Module Conventions

- Import root for backend code is `app`.
- ORM-first conventions are explicitly documented in `agents.md`.
- The export layer uses explicit projection contracts rather than dynamic schema
  inference.
- Tests are written with `pytest`.
- The backend reuses a local `.venv` interpreter and a standard package layout.

## Tests and Validation Executed

Executed:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  backend/tests/test_student_dataset_projection.py \
  backend/tests/test_student_dataset_queries.py \
  backend/tests/test_student_dataset_release_windows.py \
  backend/tests/test_student_dataset_service.py \
  backend/tests/test_student_dataset_writer.py \
  backend/tests/test_core_config.py \
  backend/tests/test_configuration_profiles.py -q
```

Result:

- `78 passed in 8.30s`

Additional validation performed:

- Physical Parquet schema inspection with `pyarrow`
- Manifest inspection for checked-in release artifacts
- Review of ORM models and export query logic

## Databricks and Environment Findings

The implementation plan assumes repository assets that do not currently exist.

Missing from the repository:

- root `databricks.yml`
- Databricks bundle resource YAML files
- `config/environments/napa_5k.yml`
- `config/environments/napa_50k.yml`
- `config/environments/napa_250k.yml`
- `config/silver_to_gold/*.yml`

Current runtime configuration is environment-variable based in
`backend/app/core/config.py`, with default payload support in
`backend/app/core/default_configuration.py`.

Conclusion:

- Phase 0 can be completed.
- Phase 1 cannot follow the spec literally until Databricks bundle and Gold
  configuration scaffolding are created.

## Silver Contract Discovery

### Canonical Physical Artifact Used

For the actual Phase 0 contract, the most relevant checked-in 5K artifact is:

`data/student_dataset_exports/5k_12_months_eliminated_uuid_data_types/20260714/114303Z/clean/5k_12_months_eliminated_uuid_data_types_initial_history`

Why this artifact was used:

- It is a real 5K export, which satisfies the plan's requirement to inspect at
  least `napa_5k`-equivalent Silver data.
- It uses schema version `1.3`.
- It matches the current `player_master`-based projection code and current
  export tests.

### Additional Artifacts Reviewed

- `scripts/data/student_dataset_exports/napa_olympic_analytics_v1_test/...`
- `scripts/data/student_dataset_exports/napa_olympic_analytics_v1_run/...`
- `data/student_dataset_exports/NAPA_dev_dataset_with_5k_players_12_months/...`

### Physical Table Inventory in the 5K Clean Artifact

- `clubs`
- `club_memberships`
- `match_games`
- `match_team_players`
- `match_teams`
- `matches`
- `monthly_batches`
- `player_assessment_history`
- `player_master`
- `player_registrations`
- `regions`
- `team_memberships`
- `teams`

## Required Discovery Questions

### Player status values

- `ACTIVE`
- `INACTIVE`
- `INJURED`
- `RETIRED`

### Team status values

- `active`
- `dormant`
- `retired`

### Country code values

- `CA`
- `US`

### Region type values

- `CA`
- `CMA`
- `MSA`

### Gender values

- `F`
- `M`

### Team category values

Derived from `teams.team_type`:

- `mens_doubles`
- `mixed_doubles`
- `open_doubles`
- `womens_doubles`

### Match type values

- `challenge`
- `clinic`
- `ladder`
- `league`
- `recreational`
- `tournament`

### Do historical match sides contain persistent `team_id`?

Yes, when the source match side was created from a persistent team.

Details:

- `match_teams.parquet` contains `id`, `match_id`, `team_number`, `team_id`,
  `team_score`, and `average_team_rating`.
- Exported `team_id` is sourced from upstream `match_teams.source_team_id`.
- Ad hoc sides can still have `team_id = null`.

Implication:

- Gold can use direct side-to-team joins where `team_id` is present.
- Gold still needs a null-safe fallback path for ad hoc sides.

### Is player country direct or region-derived?

Region-derived in the exported Silver contract.

Details:

- `player_master` contains `home_region_id`.
- `player_master` does not contain `country_code`.
- Country can be obtained through `player_master.home_region_id -> regions.id ->
  regions.country_code`.

### Do membership dates support as-of joins?

Yes.

Evidence:

- `club_memberships` exposes `start_date` and `end_date`.
- `team_memberships` exposes `joined_date` and `left_date`.
- Export query logic suppresses future end/left dates to preserve snapshot
  semantics.

### How is the latest successful Silver run resolved?

Two practical resolution paths exist in the current repository:

1. Database-backed release tracking
   - `student_dataset_releases.status` must be `succeeded`
   - `completed_at` is populated when publication finishes
   - This is the best current operational signal for "latest successful export"

2. Filesystem-backed artifact discovery
   - each release folder contains `manifest.json`
   - manifests carry `release_name`, `release_type`, `snapshot_month`, row
     counts, and schema version

Recommended Gold rule for the current repo:

- Prefer the latest `student_dataset_releases` record with `status='succeeded'`
  for a selected release family.
- Fall back to the newest valid filesystem release folder with a parseable
  `manifest.json` when database release metadata is unavailable.

This is not yet implemented as a reusable Gold utility because Phase 0 stops
before Gold code.

## Drift and Gaps Identified

### 1. Release naming drift

The spec expects supported releases named:

- `napa_5k`
- `napa_50k`
- `napa_250k`

The repository currently stores checked-in exports under names such as:

- `5k_12_months_eliminated_uuid_data_types`
- `NAPA_dev_dataset_with_5k_players_12_months`
- `napa_olympic_analytics_v1_test`
- `napa_olympic_analytics_v1_run`

### 2. Contract drift across checked-in artifacts

Observed mismatch between artifacts:

- older `run` artifact:
  - schema version `1.0`
  - `players.parquet`
  - `player_rating_history.parquet`
- newer 5K and test artifacts:
  - schema version `1.3`
  - `player_master.parquet`
  - no separate `player_rating_history.parquet`
  - latest rating state embedded in `player_master`

This is a material Phase 0 finding. Gold code must target one contract.

Recommendation:

- Treat schema `1.3` with `player_master` as the authoritative contract for new
  work unless the instructor explicitly directs otherwise.

### 3. Databricks scaffolding is absent

The spec assumes an existing Databricks deployment surface. The repository
currently has none of it.

### 4. Silver inventory differs from the original plan wording

The plan names `players` as a required Silver table. The current 5K physical
contract uses `player_master`.

### 5. Team-country and player-country are asymmetric

- `teams` includes direct `country_code` in current schema `1.3`
- `player_master` does not

Gold country logic must therefore use:

- direct country for teams where needed
- region-derived country for players

### 6. Some physically present fields are structurally null in checked-in data

Examples from the 5K artifact:

- `regions.latitude`
- `regions.longitude`
- `player_master.global_percentile`

Gold logic should not assume these fields are populated.

## Reusable Existing Assets for Gold

The future Gold implementation should reuse these existing repository patterns:

- explicit contract definitions in `projection.py`
- release-window logic in `release_windows.py`
- manifest-driven release metadata in `writer.py`
- ORM naming and relationship conventions in `backend/app/models`
- test style and fixture conventions in `backend/tests`

## Phase 0 Acceptance Assessment

Completed:

- repository tree inspected
- agent guidance located
- current pipeline architecture summarized
- package/module conventions identified
- test framework identified and exercised
- Bronze-to-Silver runtime context inspected through export modules
- operations/release tracking tables reviewed
- actual 5K-equivalent Silver schemas inspected
- required code values enumerated
- player-country derivation determined
- match-side persistent team identity gap determined
- membership as-of capability verified
- latest successful Silver release resolution method documented
- specification-vs-physical gaps documented

Not present in repository:

- Databricks bundle definitions
- environment YAML files expected by the spec

These are repository gaps, not Phase 0 blockers.

## Findings Requiring Instructor Confirmation

The following should be explicitly approved before Gold foundation work begins:

1. Schema `1.4` with `player_master` is the authoritative Silver contract.
2. Team category should be sourced from `teams.team_type`.
3. Player country should be derived from `regions.country_code`.
4. Gold may use exported `match_teams.team_id` directly, with fallback handling
   for null ad hoc sides.
5. The Gold pipeline should support a manifest/release-tracker based release
   selection approach instead of the spec's assumed Databricks environment files.
