# Monthly Generation Pipeline

**Status:** Implemented orchestration layer  
**Primary code:** `backend/app/generation/monthly_pipeline.py`  
**CLI:** `backend/scripts/run_monthly_pipeline.py`

## Purpose

The monthly generation pipeline wires the individual generation modules into one
repeatable process for running one or more successive monthly batches.

It is designed to support:

- full generation runs from the beginning
- successive future-month generation
- the configured number of months for the active generation run
- auditable per-step row counts and statuses

The pipeline coordinates existing generators. It does not replace their internal
logic.

## Version 1 Web Control Panel Policy

The lower-level monthly pipeline should align with the Version 1 web control
panel policy. Operator-facing generation starts from the beginning and does not
support selected-batch starts, partial restarts, or existing-data bypass
behavior.

For the web control panel:

- Only the web control panel may start an operator-facing generation run.
- A generation run starts only from the single current valid configuration.
- A generation run is destructive to generated domain data.
- Seed/reference data and saved configuration versions are preserved.
- Seed/reference data is treated as fixed operational input for Version 1 and
  changes only through explicit raw ingest and seed normalization workflows.
- Only one generation run may be active at a time.
- No selected-batch start, mid-run start, or partial resume is allowed.
- Failed generation runs must be retried by starting a new full destructive run
  from the beginning.

CLI entry points may remain useful for development and testing, but they should
use the same lifecycle guard and destructive reset service used by the web
control panel when starting a generation run.

For Version 1 web workflows, generation completion is based on the implemented
generation stages: `players`, `club_memberships`, `teams`, `matches`, and
`ratings`. Validation and student dataset release/export are future
post-generation workflow steps. They may be shown as disabled/planned in the UI,
but they are not required for a generation run to become `succeeded`.

The web control panel should display a progress bar for each implemented stage.
Pipeline and generator code therefore needs a durable progress callback or
progress-writer hook for long-running stages. Stage progress should be persisted
periodically while the worker is running, not only when the stage returns.

Minimum progress fields for each visible stage:

- Stage status.
- Progress current value.
- Progress total value, when known.
- Progress unit.
- Last heartbeat timestamp.
- Last progress message.

When a stage knows its expected total, such as target players, target matches,
or files to export, the UI should render a determinate progress bar. When the
total is not known, the UI should render an indeterminate progress bar with the
current processed count and heartbeat age. A stale heartbeat is an operational
warning, not an automatic failure.

## Execution Order

For each monthly batch, the pipeline runs stages in this order:

1. `players`
2. `club_memberships`
3. `teams`
4. `matches`
5. `ratings`

The first three stages are effectively setup stages for the current run:

- `players` creates the initial player population, registrations, and initial
  rating history.
- `club_memberships` assigns generated players to clubs.
- `teams` creates active doubles teams.

Later months reuse the active player, club, and team state created earlier in
the same generation run. The month-level stages then generate new match/game
activity and rating updates:

- `matches` creates matches, match teams, match players, and game scores for the
  batch.
- `ratings` consumes the batch's matches and games, appends
  `player_rating_history` rows, and writes `ratings_update_log` audit rows.

## Full-Run Monthly Looping

The pipeline should process the configured month range from the current valid
configuration. The first generated month and generated month count come from the
configuration snapshot frozen into the generation run.

For a full generation run:

1. The generation service performs the destructive reset.
2. It creates all required `monthly_batches` for the configured month range.
3. It processes monthly batches ordered by `batch_month`.
4. It processes each stage from the beginning.
5. It marks each monthly batch `succeeded` or `failed`.
6. It marks the generation run `succeeded` only after all required monthly
   batches succeed.

The destructive reset must use the generated-domain reset plan defined in the
data reset specification and shared backend reset-plan module. PostgreSQL uses
an explicit multi-table `TRUNCATE TABLE ... RESTART IDENTITY` for the
rebuildable generated operational domain; non-PostgreSQL/test dialects may use
ordered `DELETE` fallback behavior. The reset must preserve seed/reference
tables, configuration versions, `generation_runs`, `monthly_batches`,
`job_status`, `job_stage_progress`, and export/release history.

The web orchestration workflow must not expose:

- selected-batch starts
- month-count overrides
- existing-data bypass controls
- fail-on-existing controls
- stage-level resume controls
- mid-run restarts

## Batch Lifecycle

The pipeline uses `GenerationControlPlane` for batch status transitions.

For each processed batch:

```text
pending -> running -> succeeded
pending -> running -> failed
```

If a stage raises an error, the pipeline marks the batch as `failed` and writes
the exception text to `monthly_batches.error_message`.

Failed batches make the generation run fail. Retrying after failure requires a
new full destructive generation run from the beginning.

## CLI Usage

Start a full generation run:

```bash
python backend/scripts/run_monthly_pipeline.py \
  --generation-run-id 15
```

The CLI should use the generation run's frozen configuration snapshot to derive
the first generated month, generated month count, player scale, and other
runtime settings. Development-only flags may exist temporarily during migration,
but they should not be part of the operator-facing contract.

## CLI Output

The command should print a compact per-batch summary:

```text
generation_run_id=15
months_configured=2
batch=1,2024-01-01,status=succeeded
  players=generated,players=5000,registrations=5000
  club_memberships=generated,rows=4486
  teams=generated,active_teams=1750
  matches=generated,game_count=4938,match_count=3286
  ratings=generated,log_count=13144,match_count=3286,rating_history_count=13144
batch=2,2024-02-01,status=succeeded
  matches=generated,game_count=4938,match_count=3281
  ratings=generated,log_count=13124,match_count=3281,rating_history_count=13124
```

## Current Scope and Extension Points

The current pipeline is intended to loop month-level match and rating generation
for the configured generation month range.

The following future enhancements should plug into this orchestration layer as
new stages or as replacements for setup-only behavior:

- incremental monthly player growth
- monthly club membership churn
- team persistence, dissolution, and new team formation per month
- assessment history generation
- validation result generation
- Parquet export

Until those are implemented, the pipeline reuses the initial population,
memberships, and active teams for successive months, then generates new matches,
games, and rating updates for each monthly batch.
