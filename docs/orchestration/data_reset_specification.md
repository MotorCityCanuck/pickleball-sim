# Data Reset Specification

**Status:** Draft for review  
**Scope:** Seed refresh and full synthetic generation reset behavior  
**Primary code paths:** `backend/app/generation/destructive_reset.py`, `backend/app/generation/seed_refresh_service.py`, `backend/app/generation/run_service.py`

## Purpose

This document defines how the system should reset data during:

- full seed refresh
- raw seed reload plus normalization
- full destructive synthetic generation runs

The goal is to make reset behavior:

- operationally safe
- fast at larger scales
- explicit about what is preserved
- explicit about what is rebuilt
- aligned with control-panel status reporting

This specification does **not** define database schema migrations. It defines
runtime data reset policy.

## Problem Statement

The current reset strategy performs broad `DELETE` operations across generated
tables in one long transaction. This is simple, but it will not scale well as
the simulation grows toward:

- hundreds of thousands of players
- hundreds of thousands or millions of matches
- large `match_teams`, `match_team_players`, and `ratings_update_log` tables

Observed issues:

- destructive reset can consume CPU and disk for a long time
- status reporting was historically too coarse to show what was happening
- operator confidence drops when a reset appears frozen
- row-by-row MVCC deletes generate large WAL volume and index maintenance cost

## Design Principles

1. Runtime reset should be a **data-domain** operation, not a schema rebuild.
2. Control/history data should be preserved unless explicitly purged by a separate operator action.
3. Seed/reference rebuilds and synthetic/generated rebuilds should be treated as separate domains.
4. Reset behavior must be observable through durable status rows.
5. Fast reset strategies should be preferred over generic row-by-row deletes when safe.

## Non-Goals

- Rebuilding the entire database schema from ORM metadata during routine runtime operations
- Replacing migrations/schema management with ORM `drop_all()` / `create_all()`
- Preserving partial generated data after a full destructive generation run
- Supporting arbitrary partial resumes in the first reset redesign

## High-Level Recommendation

For runtime resets, do **not** drop and rebuild all operational tables from the
ORM layer.

Instead:

1. classify tables into preserved and rebuildable domains
2. keep schema intact
3. reset only the rebuildable domains
4. prefer `TRUNCATE` or similarly efficient domain-specific reset mechanisms
5. preserve operator history, configuration state, and selected audit history

## Data Domains

### Domain A: Control and Configuration

These tables should be preserved across normal seed refresh and generation reset
operations.

Examples:

- `configuration_profiles`
- `configuration_profile_versions`
- `job_status`
- `job_stage_progress`
- `generation_runs`
- `monthly_batches`
- `student_dataset_releases`
- `student_dataset_release_files`
- export/release metadata the operator wants to retain

Rationale:

- preserves reproducibility
- preserves operator history
- preserves failure analysis
- preserves control-panel context

### Domain B: Reference and Seed-Derived Production Data

These tables are rebuilt during full seed refresh workflows.

Examples:

- `regions`
- `clubs`
- `first_names`
- `last_names`

This domain should be reset when the operator runs:

- `Normalize Seed Data`
- `Refresh Full Seed Dataset`

This domain should **not** be reset during a generation-only destructive run.

### Domain C: Raw Seed Staging Data

These tables represent raw ingest inputs and ingest errors.

Examples:

- `raw_seed_load_runs`
- `raw_seed_load_errors`
- `raw_metro_areas`
- `raw_first_names`
- `raw_last_names`
- `raw_state_prov_biases`
- `raw_pickleball_club_names`
- `raw_pickleball_club_distributions`

Policy:

- raw staging rows are rebuildable
- raw load run history may be preserved as operator history, depending on retention policy
- staging content can be replaced per dataset during new raw ingest cycles

### Domain D: Generated Synthetic Operational Data

These tables are fully rebuildable and should be reset before a full synthetic
generation run. They should also be reset before seed normalization when
reference-table changes invalidate downstream synthetic data.

Examples:

- `players`
- `player_registrations`
- `club_memberships`
- `teams`
- `team_memberships`
- `tournaments`
- `matches`
- `match_games`
- `match_teams`
- `match_team_players`
- `player_rating_history`
- `player_assessment_history`
- `ratings_update_log`
- `batch_runs`
- `validation_results`
- `export_runs`

## Reset Modes

### Mode 1: Raw Ingest Only

Purpose:

- reload configured raw seed datasets into staging tables

Reset scope:

- targeted replacement of affected raw staging dataset rows
- no synthetic generated-data reset
- no production reference-table rebuild

Preserve:

- configuration
- job/run history
- production reference tables
- generated synthetic tables

### Mode 2: Seed Normalization Only

Purpose:

- rebuild production reference tables from raw staging rows

Reset scope:

- reset generated synthetic domain because downstream data depends on reference tables
- rebuild production reference domain

Preserve:

- configuration
- job/run history
- raw staging history as configured

### Mode 3: Full Seed Refresh

Purpose:

- reload raw staging inputs and rebuild production reference data

Reset scope:

- raw ingest into staging
- generated synthetic domain reset
- production reference domain rebuild

Preserve:

- configuration
- job/run history
- prior release/export history unless a separate purge policy says otherwise

### Mode 4: Full Synthetic Generation Run

Purpose:

- regenerate all synthetic data from the current valid configuration and current
  seed/reference state

Reset scope:

- generated synthetic operational domain only

Preserve:

- configuration
- job/run history
- reference domain
- raw staging history

## Runtime Strategy Options

### Option A: Current Broad DELETE Strategy

Mechanism:

- ordered `DELETE FROM table` statements
- one transaction

Pros:

- simple
- ORM-friendly
- predictable

Cons:

- poor scaling
- high WAL volume
- expensive index maintenance
- slow for `matches`, `match_teams`, `match_team_players`, `ratings_update_log`

Recommendation:

- keep only as an interim fallback

### Option B: Ordered TRUNCATE for Rebuildable Domains

Mechanism:

- `TRUNCATE ... RESTART IDENTITY` in dependency-safe order
- or `TRUNCATE ... CASCADE` if explicitly controlled

Pros:

- much faster than `DELETE`
- lower per-row overhead
- better fit for full rebuild workflows

Cons:

- requires very careful table classification
- must not touch preserved history tables
- identity reset behavior must be intentional

Recommendation:

- preferred next step for large generated domains

### Option C: Chunked DELETE

Mechanism:

- delete large tables in batches by primary-key range or `LIMIT`-style loops

Pros:

- more controllable lock/WAL profile than single huge delete
- can expose better intermediate progress

Cons:

- still fundamentally delete-based
- more code complexity
- slower than `TRUNCATE` for full rebuild scenarios

Recommendation:

- useful only if `TRUNCATE` is unsafe or blocked by retention requirements

### Option D: Schema Drop/Recreate from ORM

Mechanism:

- drop selected tables
- recreate via ORM metadata

Pros:

- brute-force clean state

Cons:

- couples runtime execution to schema definition
- riskier during live operator workflows
- complicates preservation of selected history tables
- blurs line between data reset and schema management

Recommendation:

- do not use as the standard runtime reset mechanism
- acceptable only for dev/bootstrap utilities, not control-panel execution

## Recommended Reset Policy

### Runtime Policy

Use domain-aware reset behavior:

- seed normalization/full seed refresh:
  - reset generated synthetic domain
  - rebuild reference domain
- generation run:
  - reset generated synthetic domain only

Preferred mechanism:

- convert generated synthetic-domain reset from broad `DELETE` to ordered `TRUNCATE`
- keep durable job/stage reporting around each reset sub-step

### Preservation Policy

Preserve by default:

- configuration versions
- run history
- job history
- batch history
- failure history
- release/export history

Potential optional retention policy later:

- archive or prune old `job_stage_progress`
- archive or prune old `raw_seed_load_runs`
- archive or prune old export artifacts

## Status and Observability Requirements

Any redesigned reset mechanism must continue to emit durable progress through
the orchestration layer.

Minimum runtime visibility:

- reset stage started
- current table/domain step
- completed table/domain steps
- total table/domain steps
- heartbeat freshness
- failure reason

If chunked deletion is used anywhere, add:

- current chunk number
- rows removed so far
- estimated total when available

If `TRUNCATE` is used, the status model should still show:

- current table being truncated
- completed table count

## Safety Requirements

1. Reset must only operate on explicitly approved rebuildable tables.
2. Preserved tables must be defined in code and in documentation, not inferred ad hoc.
3. The operator UI must identify the reset mode clearly.
4. Production-like environments should require stronger confirmation than local dev.
5. A failed reset must leave clear status records even if the data reset is partial.

## Open Questions

1. Should `generation_runs` and `monthly_batches` be preserved indefinitely, or should there be a separate “purge history” operator tool later?
2. Should `student_dataset_releases` be preserved across full seed refresh, or should some releases be invalidated when reference data changes materially?
3. Should raw ingest history remain forever, or should only the most recent successful cycle remain prominently attached to the control panel?
4. Should identity values be reset during generated-domain rebuilds, or preserved for audit continuity?
5. Should reset be implemented as one transaction per domain or one transaction per table for better recoverability and progress visibility?

## Proposed Next Implementation Step

1. Define the preserved-table allowlist and rebuildable-table allowlist in one shared module.
2. Refactor destructive reset into domain-aware strategies.
3. Implement a `TRUNCATE`-based reset path for the generated synthetic domain.
4. Keep the current status instrumentation pattern so the control panel stays informative.
5. Add tests that verify:
   - preserved tables survive resets
   - rebuildable tables are emptied
   - job/run history remains intact
   - reset progress is still visible

## Bottom-Line Decision

For routine runtime workflows, the system should **not** drop and rebuild all
operational tables from ORM metadata.

The preferred design is:

- preserve control/configuration/history tables
- rebuild seed/reference and synthetic domains explicitly
- replace large-table `DELETE`-based resets with a faster domain-aware reset
  strategy, preferably `TRUNCATE` where safe
