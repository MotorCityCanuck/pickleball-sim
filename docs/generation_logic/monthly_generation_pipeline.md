# Monthly Generation Pipeline

**Status:** Implemented orchestration layer  
**Primary code:** `backend/app/generation/monthly_pipeline.py`  
**CLI:** `backend/scripts/run_monthly_pipeline.py`

## Purpose

The monthly generation pipeline wires the individual generation modules into one
repeatable process for running one or more successive monthly batches.

It is designed to support:

- one-month development runs
- resume-style runs that skip already populated stages
- successive future-month generation
- up to 12 months per invocation
- auditable per-step row counts and statuses

The pipeline coordinates existing generators. It does not replace their internal
logic.

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

Later months usually skip those setup stages and reuse the active player, club,
and team state. The month-level stages then generate new match/game activity and
rating updates:

- `matches` creates matches, match teams, match players, and game scores for the
  batch.
- `ratings` consumes the batch's matches and games, appends
  `player_rating_history` rows, and writes `ratings_update_log` audit rows.

## Multi-Month Looping

The pipeline accepts a `months` value from 1 to 12.

For a multi-month run:

1. It selects monthly batches ordered by `batch_month`.
2. If `--start-batch-id` is supplied, it starts at that batch.
3. If fewer than the requested number of batches exist, it creates successive
   `future_increment` batches after the last selected month.
4. It processes each selected batch in order.

This means a generation run can be advanced in chunks:

```bash
python backend/scripts/run_monthly_pipeline.py \
  --generation-run-id 15 \
  --start-batch-id 15 \
  --months 12
```

The 12-month cap is intentional. It keeps operational runs bounded while still
supporting a full simulated year per command.

## Existing Data Behavior

By default, the CLI skips stages that already have rows. This supports resume
and incremental workflows.

Examples:

- If a generation run already has players, `players` is skipped.
- If club memberships already exist for the run, `club_memberships` is skipped.
- If active teams already exist for the batch month, `teams` is skipped.
- If a batch already has matches, `matches` is skipped.
- If a batch already has rating logs, `ratings` is skipped.
- If a batch is already `completed`, the whole batch is skipped.

Use `--fail-existing` when you want the command to fail instead of skipping
already-populated stages.

## Batch Lifecycle

The pipeline uses `GenerationControlPlane` for batch status transitions.

For each processed batch:

```text
pending -> running -> completed
pending -> running -> failed
```

If a stage raises an error, the pipeline marks the batch as `failed` and writes
the exception text to `monthly_batches.error_message`.

Completed batches are skipped by default in later runs.

## CLI Usage

Run one month:

```bash
python backend/scripts/run_monthly_pipeline.py \
  --generation-run-id 15 \
  --start-batch-id 15
```

Run up to 12 successive months:

```bash
python backend/scripts/run_monthly_pipeline.py \
  --generation-run-id 15 \
  --start-batch-id 15 \
  --months 12
```

Run a small initial smoke load:

```bash
python backend/scripts/run_monthly_pipeline.py \
  --generation-run-id 15 \
  --start-batch-id 15 \
  --player-count 5000
```

Fail on existing data instead of skipping:

```bash
python backend/scripts/run_monthly_pipeline.py \
  --generation-run-id 15 \
  --start-batch-id 15 \
  --fail-existing
```

## CLI Output

The command prints a compact per-batch summary:

```text
generation_run_id=15
months_requested=2
batch=15,2024-01-01
  players=skipped,existing_players=5000,existing_registrations=5000
  club_memberships=skipped,existing_rows=4486
  teams=skipped,active_teams=1750
  matches=skipped,existing_matches=3286
  ratings=skipped,existing_logs=13144
batch=16,2024-02-01
  players=skipped,existing_players=5000,existing_registrations=0
  club_memberships=skipped,existing_rows=4486
  teams=skipped,active_teams=1750
  matches=generated,game_count=4938,match_count=3281
  ratings=generated,log_count=13124,match_count=3281,rating_history_count=13124
```

## Current Scope and Extension Points

The current pipeline is ready to loop month-level match and rating generation
for up to 12 successive batches.

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
