# Data Reset Specification

**Status:** Implemented for generated-domain reset; retained as the authoritative reset policy  
**Scope:** Seed refresh and full synthetic generation reset behavior  
**Primary code paths:** `backend/app/generation/destructive_reset.py`, `backend/app/generation/seed_refresh_service.py`, `backend/app/generation/run_service.py`  
**Domain policy source:** `backend/app/generation/reset_plan.py`

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

The previous reset strategy performed broad `DELETE` operations across generated
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

### Domain A: Control, Configuration, and History

These tables should be preserved across normal seed refresh and generation reset
operations.

Examples:

- `configuration_profiles`
- `configuration_profile_versions`
- `job_status`
- `job_stage_progress`
- `generation_runs`
- `monthly_batches`
- `batch_runs`
- `validation_results`
- `export_runs`
- `student_dataset_releases`
- `student_dataset_release_files`
- `uploaded_files`
- export/release metadata the operator wants to retain

Rationale:

- preserves reproducibility
- preserves operator history
- preserves failure analysis
- preserves control-panel context
- preserves release/export lineage

### Domain B: Reference and Seed-Derived Production Data

These tables are rebuilt during full seed refresh workflows.

Rebuildable production reference examples:

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

- `raw_metro_areas`
- `raw_first_names`
- `raw_last_names`
- `raw_state_prov_biases`
- `raw_pickleball_club_names`
- `raw_pickleball_club_distributions`

Policy:

- raw staging rows are rebuildable
- `raw_seed_load_runs` and `raw_seed_load_errors` are preserved as raw-load history
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

These tables are reset by the generated operational reset plan in
`backend/app/generation/reset_plan.py`. Control/history tables that refer to
generated runs or batches, such as `monthly_batches`, `batch_runs`,
`validation_results`, `export_runs`, and student dataset release metadata, are
preserved by default.

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

### Option A: Legacy Broad DELETE Strategy

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

### Option B: Explicit Multi-Table TRUNCATE for Rebuildable Domains

Mechanism:

- on PostgreSQL, issue one explicit `TRUNCATE TABLE ... RESTART IDENTITY`
  statement over the generated operational allowlist
- include all foreign-key-related generated tables in the same truncate group
- avoid `CASCADE` so preserved tables cannot be pulled into the reset
- on non-PostgreSQL dialects, keep the ordered `DELETE` fallback used by tests

Pros:

- much faster than `DELETE`
- lower per-row overhead
- better fit for full rebuild workflows
- avoids MVCC dead-tuple buildup on large generated tables
- resets generated-domain identities intentionally

Cons:

- requires very careful table classification
- must not touch preserved history tables
- identity reset behavior must be intentional
- takes table-level locks while the truncate executes

Recommendation:

- implemented for the generated synthetic operational domain on PostgreSQL

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

- reset the generated synthetic domain from a shared explicit allowlist
- use explicit multi-table `TRUNCATE ... RESTART IDENTITY` on PostgreSQL
- keep ordered `DELETE` as a fallback for non-PostgreSQL/test dialects
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

- current generated-domain reset stage
- completed table count
- `reset_strategy` metadata set to `truncate`
- operator-facing wording that says reset/truncate rather than delete

## Safety Requirements

1. Reset must only operate on explicitly approved rebuildable tables.
2. Preserved tables must be defined in code and in documentation, not inferred ad hoc.
3. The operator UI must identify the reset mode and reset strategy clearly.
4. Production-like environments should require stronger confirmation than local dev.
5. A failed reset must leave clear status records even if the data reset is partial.
6. PostgreSQL generated-domain reset must not use broad `CASCADE`.
7. Any table with a foreign key into the generated reset group must either be
   explicitly part of that group or be handled before release.

## Open Questions

1. Should `generation_runs` and `monthly_batches` be preserved indefinitely, or should there be a separate “purge history” operator tool later?
2. Should `student_dataset_releases` be preserved across full seed refresh, or should some releases be invalidated when reference data changes materially?
3. Should raw ingest history remain forever, or should only the most recent successful cycle remain prominently attached to the control panel?
4. Should there be a dedicated operator action for pruning old control/history
   rows after they are no longer useful?

## Implemented Reset Behavior

1. `backend/app/generation/reset_plan.py` defines preserved and rebuildable
   table domains.
2. `backend/app/generation/destructive_reset.py` resets only the generated
   operational domain during generation-only resets and generated-data reset
   stages in seed normalization/full refresh workflows.
3. PostgreSQL uses a single explicit multi-table
   `TRUNCATE TABLE ... RESTART IDENTITY` statement for the generated operational
   domain.
4. SQLite and other non-PostgreSQL dialects use ordered `DELETE` fallback
   behavior for compatibility with tests and local lightweight execution.
5. Reset progress events include `reset_strategy`, and durable job/stage
   metadata records whether reset progress came from truncate or delete mode.
6. Full backend tests passed after implementation. Opt-in live PostgreSQL smoke
   tests also passed when allowed to connect to the local database.
7. A live-schema foreign-key check found no preserved/external tables with
   foreign keys into the generated reset group.

## Bottom-Line Decision

For routine runtime workflows, the system should **not** drop and rebuild all
operational tables from ORM metadata.

The preferred design is:

- preserve control/configuration/history tables
- rebuild seed/reference and synthetic domains explicitly
- reset the generated operational domain from an explicit allowlist
- replace large-table PostgreSQL `DELETE`-based resets with explicit
  multi-table `TRUNCATE ... RESTART IDENTITY`
- retain ordered `DELETE` only as a compatibility fallback for non-PostgreSQL
  dialects
