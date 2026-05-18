# Web Control Panel Design

**Status:** Proposed design for review  
**Target implementation:** FastAPI + Jinja2 + HTMX on one HTML page  
**Primary users:** Instructor/developer operators running local simulation jobs

## Purpose

The web layer should be an operational control panel, not a marketing-style
site. Its job is to make configuration, seed-data preparation, and long-running
simulation workflows visible and controllable from one browser page.

The application should be a single HTML page with top-level tabs. The first
version should prioritize reliability, progress visibility, and safe controls
over visual complexity.

## Page Structure

Use a single server-rendered page:

```text
/control
```

The page should have two primary tabs:

1. Configuration Control
2. Workload Orchestration

Recommended secondary layout:

```text
Header
- Environment/database summary
- Active configuration profile/version
- Running job indicator

Tabs
- Configuration Control
- Workload Orchestration

Persistent Status Bar
- Latest job status
- Current phase
- Percent complete
- Last refresh time
```

HTMX partials should update tab bodies and job status panels without a full
page reload.

## Tab 1: Configuration Control

The Configuration Control tab should edit and version the full generation
configuration payload stored in:

- `configuration_profiles`
- `configuration_profile_versions`

Configuration edits should create new immutable profile versions. A generation
run must freeze its selected configuration into
`generation_runs.parameter_snapshot` before any workload starts.

### Required Capabilities

- Select active configuration profile.
- View latest valid version.
- View older versions.
- Create a new version from an existing version.
- Edit all configuration groups.
- Validate edits before saving.
- Mark a version as valid or invalid.
- Start a generation run from a selected version.

### Editing Model

Use grouped form sections rather than one giant JSON textarea.

Suggested sections:

- Simulation identity and target scale
- Player generation
- Regional distribution
- Club generation and memberships
- Team formation
- Match scheduling
- Matchmaking
- Games and scores
- Ratings
- Confidence
- Export settings
- Validation thresholds
- Runtime settings

Each field should have:

- label
- current value
- type-specific input
- validation hint
- default value indicator
- changed-from-version marker

Use appropriate controls:

- numeric inputs for counts and thresholds
- sliders only for bounded probability-style values when precision is not
  critical
- checkboxes for booleans
- select menus for enumerations
- editable key/value tables for weight maps
- text inputs for names and versions

### Validation

Configuration validation should run before a new version can become valid.

Validation should check:

- probabilities are between `0` and `1`
- weight groups sum to `1.0`
- minimums are less than maximums
- target counts are positive
- rating bounds are coherent
- month counts are within supported limits
- required groups are present
- unknown keys are either rejected or clearly flagged

Validation results should be shown inline next to the affected field and also in
a summary panel.

### Save Behavior

Do not mutate existing profile-version payloads.

Recommended save flow:

1. User edits draft values in the form.
2. User clicks `Validate`.
3. Server validates and returns inline errors/warnings.
4. If valid, user clicks `Save New Version`.
5. Server inserts a new `configuration_profile_versions` row.
6. UI updates active version selector and version history.

## Tab 2: Workload Orchestration

The Workload Orchestration tab should control two major stages:

1. Raw Data Ingest and Seed Data Generation
2. Workflow Control and Status

These stages should be visible as separate panels inside the same tab.

## Stage 1: Raw Data Ingest And Seed Data Generation

This stage prepares the reference data needed by generation jobs.

Existing command equivalents:

- `backend/scripts/load_raw_seed_data.py`
- `backend/scripts/normalize_seed_data.py`
- `backend/scripts/seed_configuration_profile.py`

### Raw Ingest Controls

Show a dataset checklist for supported raw datasets:

- `metro_areas_us`
- `metro_areas_ca`
- `first_names_us`
- `first_names_ca`
- `last_names_us`
- `last_names_ca`
- `pickleball_club_distributions`
- `pickleball_club_names`
- `state_prov_biases_us`
- `state_prov_biases_ca`

For each dataset, show:

- raw load status
- latest `raw_seed_load_runs` status
- rows read
- rows loaded
- rows rejected
- latest load time
- error count
- normalize status
- production row count

Controls:

- Load selected raw datasets.
- Normalize selected datasets.
- Replace production rows, behind a confirmation checkbox.
- Run all required seed-prep steps in order.
- View latest ingest errors.

### Seed Data Readiness Panel

Before simulation workflows can run, show readiness checks:

- regions loaded
- first names loaded
- last names loaded
- clubs loaded
- state/province bias data loaded where expected
- default configuration profile exists and has a valid version

Use this panel to prevent generation runs from starting against incomplete
reference data.

## Stage 2: Workflow Control And Status

This stage creates generation plans and runs monthly generation.

Existing command equivalents:

- `backend/scripts/create_generation_plan.py`
- `backend/scripts/run_monthly_pipeline.py`

### Generation Plan Controls

Inputs:

- generation name
- configuration profile
- configuration version
- seed value
- first batch month
- historical month count
- initial player count override

Actions:

- Create generation plan.
- Preview planned monthly batches.
- Start selected plan.

### Monthly Pipeline Controls

Inputs:

- generation run
- start batch
- month count, capped at `12`
- player count override
- skip existing stages
- fail on existing stages

Actions:

- Run one month.
- Run up to twelve successive months.
- Resume from selected batch.
- Stop/cancel requested job, when job cancellation is implemented.

Pipeline stages shown per batch:

```text
players
club_memberships
teams
matches
ratings
validation
export
```

The current implementation supports the first five stages. Validation and
export should appear as planned/disabled stages until implemented.

## Long-Running Job Model

Long-running actions should not run directly inside request/response handlers.

Recommended server flow:

1. User submits a workload action.
2. Server creates a `job_status` row with `pending`.
3. Server starts background execution.
4. Background worker updates `job_status`.
5. UI polls a status endpoint with HTMX.
6. UI renders progress, current phase, and logs.

The existing `job_status` table already supports:

- `job_type`
- `job_id`
- `status`
- `current_phase`
- `percent_complete`
- `current_message`
- `started_at`
- `completed_at`
- `error_message`

Recommended job types:

- `raw_seed_ingest`
- `seed_normalization`
- `generation_plan`
- `monthly_pipeline`
- `validation`
- `export`

## Progress Reporting

The UI needs real progress for long-running jobs, not just a spinner.

Show both batch-level and stage-level progress:

```text
Job: monthly_pipeline
Status: running
Current batch: 2024-04-01
Current phase: matches
Percent: 62.5%
Message: Generated 18,400 of 34,900 target matches
```

For the first version, progress can be coarse:

- stage started
- stage completed
- row counts after each stage
- current batch index out of total batches

Later versions should add intra-stage counters for:

- players generated
- club memberships created
- teams formed
- matches generated
- rating updates written
- files exported

## Polling Design

Use HTMX polling for job status:

```html
<section
  id="job-status"
  hx-get="/control/jobs/current"
  hx-trigger="load, every 2s"
  hx-swap="outerHTML">
</section>
```

Recommended endpoints:

```text
GET  /control
GET  /control/config
POST /control/config/validate
POST /control/config/versions
GET  /control/workloads
POST /control/jobs/raw-ingest
POST /control/jobs/normalize-seed
POST /control/jobs/create-plan
POST /control/jobs/run-pipeline
GET  /control/jobs/{job_id}
GET  /control/jobs/current
```

The response for `GET /control/jobs/{job_id}` should be a partial HTML fragment
for HTMX and optionally JSON for future API use.

## Status Views

The Workload Orchestration tab should include:

- current job card
- recent jobs table
- generation runs table
- monthly batches table
- raw seed load runs table
- validation/export placeholders

Generation run table columns:

- id
- generation name
- seed
- status
- configuration profile/version
- started
- completed
- batches

Monthly batch table columns:

- id
- month
- sequence
- status
- players added
- match count
- rating update count
- error

Recent jobs table columns:

- job id
- job type
- status
- phase
- percent complete
- started
- completed
- error

## Safety And Guardrails

The UI should prevent expensive or destructive mistakes.

Recommended guardrails:

- Require confirmation for replacing production seed data.
- Require confirmation for runs above a configurable player-count threshold.
- Cap monthly pipeline runs at 12 months per invocation.
- Disable start buttons when prerequisite checks fail.
- Show the selected database URL or environment label in the header.
- Prevent launching two write-heavy jobs concurrently unless the job types are
  proven safe to run in parallel.
- Freeze configuration payloads into generation runs.
- Preserve immutable configuration versions.
- Show whether a stage will run, skip, or fail before starting.

## Implementation Notes

### Backend

Recommended package structure:

```text
backend/app/web/
  main.py
  routes/
    control.py
    config.py
    jobs.py
  templates/
    control.html
    partials/
      config_tab.html
      workload_tab.html
      job_status.html
      generation_runs.html
      monthly_batches.html
  static/
    control.css
```

### Job Execution

For local development, FastAPI `BackgroundTasks` is acceptable for the first
version.

If jobs need cancellation, restart durability, or multiple workers, move to a
real queue later. The design should avoid assuming that request handlers own
the job lifecycle.

### Frontend

Use restrained operational styling:

- dense but readable tables
- clear status chips
- compact form groups
- sticky job status area
- tabs for the two major workflows
- no landing page
- no decorative cards inside cards

The first screen should be the control panel itself.

## Suggested Build Order

1. Add FastAPI app shell and `/control` route.
2. Render one-page layout with two tabs.
3. Add read-only status panels for configuration, generation runs, monthly
   batches, raw load runs, and jobs.
4. Add job-status polling partial.
5. Add configuration viewer.
6. Add configuration validation and save-new-version flow.
7. Add raw ingest and normalize job launch actions.
8. Add generation-plan job launch action.
9. Add monthly-pipeline job launch action.
10. Add progress updates inside pipeline stages.
11. Add cancellation and log detail views.

## Open Design Questions

- Should configuration editing use generated forms from a schema, or manually
  maintained grouped forms?
- Should `job_status` gain structured JSON metadata for stage counts and result
  summaries?
- Should long-running jobs be cancellable in the first version?
- Should the web layer support multiple named environments, or only the local
  development database?
- Should validation/export be visible as disabled stages immediately, or hidden
  until implemented?

## Recommendation

Build the first version as a single-page HTMX control panel with server-rendered
partials and background jobs. Keep it intentionally operational: configuration
editing on one tab, workload orchestration on the other, with a persistent job
status strip that always tells the operator what is running and what happened
last.
