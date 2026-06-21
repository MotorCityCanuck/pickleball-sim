# Durable Background Jobs Specification

## Status

Proposed implementation specification for review.

## Purpose

This document defines a cautious migration path from in-process control-panel
background threads to durable background job execution.

The first target is the realism audit. Generation runs and student dataset
exports should remain on the existing implementation until the new worker
pattern has been proven on realism-audit workloads.

The immediate problem is operational stability. Multiple long-running jobs have
left `job_status` and `job_stage_progress` rows in `running` state after the
backend process or worker context disappeared. In those cases PostgreSQL had no
active query, no Python exception was persisted, and the control plane had to
infer stale state from old heartbeats.

## Current Failure Mode

Heavy jobs are currently submitted from the FastAPI control panel into an
in-process `ThreadPoolExecutor` through `BackgroundJobRunner`.

This has a weak failure boundary:

- if the web process exits, the job thread exits with it
- if the process is restarted, queued and running work held only in memory is
  lost
- if the worker vanishes outside normal exception handling, the database is
  left with stale `running` rows
- the UI can detect staleness only after heartbeats age out
- recovery is manual and cannot know whether a job is safely resumable

This is acceptable for short tasks. It is not reliable enough for realism
audits, generation runs, or exports at large data scale.

## Goals

The durable job system must:

- execute heavy jobs outside the web request process
- preserve the existing `job_status` and `job_stage_progress` user-facing model
- record durable job ownership and worker heartbeats
- record enough lifecycle evidence to diagnose worker loss
- allow realism audits to resume from the last completed query
- make stale jobs recoverable without guessing whether work is still active
- keep the first implementation small enough to review and test carefully

## Non-Goals

The first revision does not need to:

- replace every existing control-panel background task
- introduce a large external queue stack
- parallelize realism-audit queries
- redesign all job lifecycle tables
- make generation runs resumable across monthly-batch boundaries
- make student dataset exports resumable
- automatically retry failed SQL forever

## Recommended Architecture

Use a DB-backed durable worker process as the first implementation.

The web process remains responsible for:

- creating `job_status` rows
- creating `job_stage_progress` rows
- rendering job state
- requesting cancellation or clearing stale state

The durable worker process becomes responsible for:

- claiming queued jobs
- renewing leases while work is active
- running job handlers
- writing progress and lifecycle events
- releasing claims on success or failure

This avoids adding Redis, RabbitMQ, or Celery as a first step. The database is
already the source of truth for control-plane state, and the current system
already expresses job identity and progress there.

An external queue can still be introduced later if the DB-backed worker becomes
too limiting.

## Job Scope

### First Supported Durable Job

The first durable job type is:

```text
realism_audit
```

### Later Candidates

After the realism-audit path is stable, evaluate:

```text
student_dataset_export
generation_run
seed_refresh
```

Generation runs should move last because they have the largest state surface
and already include many stage-specific progress events.

## Proposed Schema

The schema should be additive. Existing tables remain valid.

### `background_workers`

Tracks worker processes that can claim durable jobs.

```sql
CREATE TABLE background_workers (
    worker_id VARCHAR(64) PRIMARY KEY,
    worker_type VARCHAR(50) NOT NULL,
    host_name VARCHAR(255),
    process_id INTEGER,
    started_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_heartbeat_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(30) NOT NULL DEFAULT 'running',
    metadata_json JSONB,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_background_workers_status
        CHECK (status IN ('running', 'stopped', 'failed'))
);

CREATE INDEX idx_background_workers_status
    ON background_workers (status);

CREATE INDEX idx_background_workers_heartbeat
    ON background_workers (last_heartbeat_at);
```

### `background_job_leases`

Tracks which worker currently owns a pending or running job.

```sql
CREATE TABLE background_job_leases (
    job_status_id BIGINT PRIMARY KEY REFERENCES job_status(id) ON DELETE CASCADE,
    worker_id VARCHAR(64) NOT NULL REFERENCES background_workers(worker_id),
    lease_token VARCHAR(64) NOT NULL,
    claimed_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    lease_expires_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    last_heartbeat_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    attempt_count INTEGER NOT NULL DEFAULT 1,
    metadata_json JSONB,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX idx_background_job_leases_token
    ON background_job_leases (lease_token);

CREATE INDEX idx_background_job_leases_worker
    ON background_job_leases (worker_id);

CREATE INDEX idx_background_job_leases_expiry
    ON background_job_leases (lease_expires_at);
```

### `background_job_events`

Append-only operational breadcrumbs.

```sql
CREATE TABLE background_job_events (
    id BIGSERIAL PRIMARY KEY,
    job_status_id BIGINT NOT NULL REFERENCES job_status(id) ON DELETE CASCADE,
    worker_id VARCHAR(64),
    event_type VARCHAR(50) NOT NULL,
    event_message TEXT,
    event_metadata_json JSONB,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_background_job_events_job
    ON background_job_events (job_status_id, id);

CREATE INDEX idx_background_job_events_type
    ON background_job_events (event_type);
```

Required event types for the first revision:

```text
queued
claimed
started
heartbeat
stage_started
step_started
step_succeeded
step_failed
snapshot_saved
completed
failed
lease_expired
cancel_requested
cancelled
```

### `realism_audit_query_runs`

Durable per-query checkpoints for realism audits.

```sql
CREATE TABLE realism_audit_query_runs (
    id BIGSERIAL PRIMARY KEY,
    job_status_id BIGINT NOT NULL REFERENCES job_status(id) ON DELETE CASCADE,
    generation_run_id BIGINT REFERENCES generation_runs(id),
    batch_id BIGINT REFERENCES monthly_batches(id),
    query_index INTEGER NOT NULL,
    query_name VARCHAR(255) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'pending',
    started_at TIMESTAMP WITHOUT TIME ZONE,
    completed_at TIMESTAMP WITHOUT TIME ZONE,
    elapsed_ms BIGINT,
    row_count BIGINT,
    result_json JSONB,
    error_message TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_realism_audit_query_runs_job_query
        UNIQUE (job_status_id, query_name),
    CONSTRAINT chk_realism_audit_query_runs_status
        CHECK (status IN ('pending', 'running', 'succeeded', 'failed', 'skipped'))
);

CREATE INDEX idx_realism_audit_query_runs_job_index
    ON realism_audit_query_runs (job_status_id, query_index);

CREATE INDEX idx_realism_audit_query_runs_status
    ON realism_audit_query_runs (status);

CREATE INDEX idx_realism_audit_query_runs_generation_run
    ON realism_audit_query_runs (generation_run_id);
```

The `result_json` column allows safe resume without rerunning already completed
queries. If result payloads become too large, this can be replaced by a
filesystem-backed result artifact path in a later revision.

## Worker Claiming Contract

The worker should claim jobs with a single transactional update pattern.

Claimable jobs for the first revision:

```text
job_status.job_type = 'realism_audit'
job_status.status IN ('pending', 'running')
no unexpired lease exists
```

`running` jobs are claimable only if their lease has expired or no lease exists.
This is what allows recovery after process loss.

Claim behavior:

1. Start transaction.
2. Select one claimable job using `FOR UPDATE SKIP LOCKED`.
3. Insert or update `background_job_leases`.
4. Set `job_status.status = 'running'` if it was pending.
5. Write `background_job_events.claimed`.
6. Commit.

Only the worker that holds the current `lease_token` may update execution state.

## Heartbeat Contract

Worker heartbeat has two layers:

- worker-level heartbeat in `background_workers`
- job-level heartbeat in `background_job_leases` and `job_stage_progress`

Default lease duration:

```text
5 minutes
```

Default heartbeat interval:

```text
30 seconds
```

For realism audit, the heartbeat loop must run independently while SQL is
executing. The current implementation only updates after each query finishes,
which means a single long SQL statement can look dead. The durable worker must
renew the lease and stage heartbeat while a long query is still active.

Recommended implementation:

- one worker thread runs the job handler
- a small heartbeat helper renews the lease in a separate session
- heartbeat stops only when the handler reaches a terminal state

## Realism Audit Durable Execution

The realism-audit worker should be implemented as the first durable handler.

### Registration Flow

The control-panel route should continue creating:

- `job_status`
- `job_stage_progress`

It should also create one `realism_audit_query_runs` row per available query at
registration time.

Initial state:

```text
job_status.status = 'pending'
job_status.current_phase = 'queued'
job_stage_progress.status = 'pending'
realism_audit_query_runs.status = 'pending'
```

The route should not submit work to `BackgroundJobRunner` for durable realism
audits. It should rely on the durable worker process.

### Execution Flow

For each query ordered by `query_index`:

1. Skip query rows already marked `succeeded`.
2. Mark the next query row `running`.
3. Write `background_job_events.step_started`.
4. Update `job_status.current_phase` to the query name.
5. Update `job_stage_progress.progress_message` to "Running query N of T".
6. Execute the query using `RealismAuditRunner`.
7. Store result rows, row count, elapsed milliseconds, and completion time.
8. Mark the query row `succeeded`.
9. Update `job_stage_progress.progress_current`, percent, message, and heartbeat.
10. Write `background_job_events.step_succeeded`.

After all queries succeed:

1. Build `RealismAuditExecution` from stored query results.
2. Save the audit snapshot.
3. Mark `job_stage_progress` succeeded.
4. Mark `job_status` succeeded.
5. Delete or mark the lease complete.
6. Write `background_job_events.completed`.

### Resume Flow

If a worker dies:

1. The lease expires.
2. The next worker claims the same job.
3. The handler reads `realism_audit_query_runs`.
4. Completed queries are reused.
5. The first `pending`, `running`, or `failed` query is rerun.

For a query found as `running` from a prior expired lease, the new worker should
mark it back to `pending` before rerun and write a recovery event.

### Failure Flow

If a query fails with an exception:

1. Mark that query row `failed`.
2. Mark `job_stage_progress` failed.
3. Mark `job_status` failed.
4. Store the exception message.
5. Release the lease.
6. Write `background_job_events.failed`.

The first revision should not automatically retry failed SQL exceptions. A
manual rerun or explicit retry button can be added after the basic worker path
is proven.

## Worker Process

Add a CLI entry point:

```text
backend/scripts/run_background_worker.py
```

Suggested arguments:

```text
--worker-type control-heavy
--queues realism_audit
--poll-interval-seconds 5
--lease-seconds 300
--heartbeat-seconds 30
--once
```

`--once` is important for tests and manual diagnosis. It should claim at most
one job and then exit.

The long-running worker should be started separately from `uvicorn`.

Local development options:

```text
python backend/scripts/run_background_worker.py --queues realism_audit
```

Later, if this is run under Docker Compose or a process supervisor, the worker
should be its own service.

## Control Panel Changes

The control panel should keep the same operator workflow:

- Run Realism Audit button creates a job.
- The orchestration tab shows progress.
- Clear stalled job remains available when a job is not active.

Changes required:

- show the current lease owner and lease expiry for running/stalled jobs
- distinguish "running with fresh worker lease" from "stored as running but
  unclaimed/stale"
- for stale durable jobs, prefer "Resume audit" over "Clear stalled job" once
  resume is implemented
- keep "Clear stalled job" as a manual escape hatch

The UI should not claim that no audit exists when a stale `running` row exists.
It should say that no active worker is processing the audit.

## Recovery Semantics

There are three important states:

| State | Meaning | Operator action |
| --- | --- | --- |
| Active | Job has a fresh unexpired lease and heartbeat | Wait or cancel |
| Recoverable | Job is non-terminal and lease is expired or missing | Resume or clear |
| Terminal | Job succeeded or failed | Review result or rerun |

The current UI mostly distinguishes active from non-active. The durable worker
revision should make recoverable state explicit.

## Cancellation

Cancellation can be deferred until after the first durable worker works, but the
schema should support it.

Recommended first behavior:

- add a cancel button that writes a `cancel_requested` event
- worker checks for cancellation between queries
- if cancellation is requested, mark job `failed` or `cancelled`

The current `job_status` check constraint must be reviewed before introducing a
new `cancelled` terminal status. If the existing allowed status set is narrow,
use `failed` with a cancellation message for the first revision.

## Implementation Plan

### Phase 0: Confirm Baseline and Clean State

Purpose:

- avoid building on ambiguous control-plane state

Tasks:

- clear or fail stale realism audit job `109` using the existing recovery path
- record the latest completed audit baseline, including job `108` runtime
- record the current state of job tables before schema changes
- confirm the web app and worker will use the same database URL and schema

Acceptance criteria:

- no stale realism audit job is blocking new audit registration
- current 50k audit baseline is documented

### Phase 1: Add Durable Worker Schema

Purpose:

- add the minimum durable execution model without changing behavior

Tasks:

- add ORM models for `BackgroundWorker`, `BackgroundJobLease`,
  `BackgroundJobEvent`, and `RealismAuditQueryRun`
- add DDL to `backend/schema.sql`
- apply DDL to the live database
- add indexes and check constraints
- add tests that create and query the new models

Acceptance criteria:

- schema applies cleanly on an empty database
- schema applies cleanly with `CREATE TABLE IF NOT EXISTS` for the live database
- existing tests continue to pass

### Phase 2: Implement Worker Claim and Lease Library

Purpose:

- create reusable infrastructure before migrating the audit handler

Tasks:

- add a worker identity helper that generates `worker_id`
- add worker registration and heartbeat functions
- add job claim logic with row locking
- add lease renewal and lease release functions
- add event writer helper
- add stale lease detection helpers
- add tests for competing workers using two sessions where feasible

Acceptance criteria:

- only one worker can claim a job
- expired leases can be reclaimed
- fresh leases cannot be stolen
- worker and job heartbeats update predictably
- lifecycle events are written durably

### Phase 3: Add the Worker CLI

Purpose:

- run heavy jobs outside the web process

Tasks:

- create `backend/scripts/run_background_worker.py`
- support `--queues realism_audit`
- support `--once`
- support configurable poll and heartbeat intervals
- log worker start, claim, completion, failure, and shutdown
- make the CLI exit nonzero only on worker infrastructure errors, not on a
  normal job failure

Acceptance criteria:

- running the worker with no jobs exits cleanly in `--once` mode
- running the worker with one queued test job claims it
- worker rows and heartbeat rows are visible in the database

### Phase 4: Convert Realism Audit Registration

Purpose:

- keep the existing UI but stop submitting audits to the in-process thread pool

Tasks:

- update `/control/realism-audit/run` to create durable audit query checkpoint
  rows
- do not call `background_runner.submit` for realism audits after durable mode
  is enabled
- introduce a feature flag if needed:

```text
CONTROL_PANEL_DURABLE_REALISM_AUDIT=true
```

- keep the old in-process path available behind the inverse flag during the
  transition

Acceptance criteria:

- clicking Run Realism Audit creates pending job state and query checkpoint rows
- no in-process thread is started when durable mode is enabled
- existing route tests are updated for both modes if the compatibility flag is
  retained

### Phase 5: Implement Durable Realism Audit Handler

Purpose:

- make realism audit execution resumable and diagnosable

Tasks:

- implement `RealismAuditJobHandler`
- load pending query rows by `query_index`
- execute one query at a time
- write per-query `started_at`, `completed_at`, `elapsed_ms`, `row_count`, and
  `result_json`
- update `job_status` and `job_stage_progress` after every query
- build the final snapshot from stored query results
- mark terminal state on success or failure
- write lifecycle events for every important transition

Acceptance criteria:

- a full audit produces the same snapshot content as the current runner
- a killed worker after query N can be restarted and resume at query N+1
- a SQL exception marks the job failed and stores the failed query name
- long queries keep the stage heartbeat fresh while running

### Phase 6: Update Control Panel Recovery UX

Purpose:

- make stale durable state explicit and less confusing

Tasks:

- expose lease state in the read model
- show "Audit recoverable" when a non-terminal audit has no fresh lease
- add a Resume Audit button if the worker is not always-on
- keep Clear Stalled Job for forced cleanup
- ensure top warning banners refresh with orchestration partials

Acceptance criteria:

- a stale durable audit is not described as completed
- a stale durable audit is not described only as "not running"
- the operator can see the last completed query and current/recoverable state

### Phase 7: Validate at 50k

Purpose:

- prove the first migration on the current failure case

Tasks:

- run the 50k realism audit through the durable worker
- record total runtime
- record per-query runtimes
- intentionally stop the worker mid-audit in a non-production test run
- restart the worker and verify resume behavior
- compare snapshot outputs against the existing audit runner

Acceptance criteria:

- no orphaned `running` state after worker stop and restart
- query checkpoint rows show the audit progression
- total audit runtime is at least no worse than the existing runner except for
  acceptable checkpoint overhead
- per-query timings identify the next SQL optimization target

## Testing Plan

### Unit Tests

Add tests for:

- worker registration
- job claim behavior
- lease renewal
- stale lease recovery
- event writing
- realism audit query checkpoint creation
- resume from partial checkpoint state

### Route Tests

Update control-panel route tests for:

- durable audit registration
- pending job display
- active worker display
- recoverable stale audit display
- completed audit display
- clear stalled job behavior

### Integration Tests

Add a small SQLite-compatible realism audit test if practical, but use
PostgreSQL-oriented tests for row locking and lease behavior if SQLite cannot
represent the concurrency semantics.

### Manual Verification

Manual local verification should include:

```text
1. Start web app.
2. Start durable worker.
3. Create realism audit from control panel.
4. Confirm worker claims the job.
5. Confirm query progress and per-query timings appear.
6. Stop worker mid-audit.
7. Confirm UI shows recoverable state after lease expiry.
8. Restart worker.
9. Confirm audit resumes and completes.
```

## Rollout Plan

### Step 1: Development Mode

- add schema and worker implementation
- keep in-process path as the default
- run tests and one manual durable audit with the feature flag enabled

### Step 2: Realism Audit Durable Mode

- enable durable mode for realism audit only
- keep generation and export unchanged
- run the current 50k audit
- inspect worker events and per-query timings

### Step 3: Stabilization

- fix any worker lifecycle issues
- refine UI text for active, recoverable, and terminal states
- document worker startup in setup docs

### Step 4: Evaluate Export Migration

- move student dataset export only after realism audit is stable
- decide whether export needs checkpointing or only stronger terminal-state
  handling

### Step 5: Evaluate Generation Migration

- move generation run last
- design monthly-batch checkpoint behavior explicitly before implementation

## Operational Guidance

Until the durable worker is implemented:

- a reboot can reduce environmental instability, but it does not fix the
  failure class
- stale running rows should continue to be cleared through existing recovery
  controls
- long realism audits should be treated as diagnostic runs, not reliable
  unattended operations

After the durable worker is implemented:

- the web process may be restarted without losing claimable work
- worker process loss should result in recoverable jobs after lease expiry
- realism audits should resume from the last completed query
- per-query timing data should become the primary input for audit SQL
  optimization

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Worker and web process disagree about job state | Keep `job_status` as the shared operator-facing source of truth and write all state changes transactionally. |
| Two workers claim the same job | Use row locking and lease tokens. Require the current token for progress updates. |
| Heartbeat writes add overhead | Heartbeats are small updates every 30 seconds, materially cheaper than long audit SQL. |
| `result_json` becomes large | Start with JSON for simplicity; move to artifact files if storage or row size becomes an issue. |
| SQLite tests cannot model locking | Unit-test pure state transitions in SQLite and add focused PostgreSQL manual/integration coverage for claiming. |
| Scope expands into all jobs too early | Gate the first release to realism audit only. |

## Open Questions

- Should durable mode be enabled by default for realism audit immediately, or
  introduced behind `CONTROL_PANEL_DURABLE_REALISM_AUDIT`?
- Should cancelled jobs get a new `cancelled` status, or use `failed` with a
  cancellation message to preserve existing status constraints?
- Should per-query audit results be stored in `realism_audit_query_runs.result_json`
  or written to a filesystem artifact path?
- Should the worker be launched manually during development or added as a
  Docker Compose service immediately?
- Should worker recovery automatically reclaim expired audits, or should the UI
  require an explicit Resume Audit action for the first revision?

## Recommended First Slice

The smallest useful implementation slice is:

1. Add durable worker schema.
2. Add worker claim, lease, heartbeat, and event helpers.
3. Add worker CLI with `--once`.
4. Convert realism audit registration behind a feature flag.
5. Implement durable realism audit handler with per-query checkpoints.
6. Validate resume by stopping the worker after a completed query.

This slice directly addresses the observed audit failure mode without forcing a
simultaneous migration of generation runs or student dataset exports.
