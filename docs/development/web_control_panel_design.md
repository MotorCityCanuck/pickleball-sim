# Web Control Panel Design

**Status:** Revised proposed design for review  
**Target implementation:** FastAPI + Jinja2 + HTMX on one server-rendered HTML page  
**Primary users:** Instructor/developer operators running local simulation jobs  
**Frontend position:** No React or SPA framework for the initial implementation

## Purpose

The web layer should be an operational control panel, not a marketing-style site. Its job is to make configuration changes, raw data ingest, seed-data preparation, and long-running simulation workflows visible and controllable from one browser page.

The application should be a single server-rendered page with top-level tabs. The first version should prioritize reliability, progress visibility, safe controls, and implementation simplicity over visual complexity.

This control panel is part of the local development and operator workflow. It should make the existing command-line workflows easier to inspect and execute, but it should not replace or duplicate the underlying pipeline logic.

## Initial Implementation Scope

The first implementation should stay intentionally narrow.

### In Scope For Version 1

- One FastAPI route serving a server-rendered `/control` page.
- Jinja2 templates and HTMX partial updates.
- Two primary tabs: Configuration Control and Workload Orchestration.
- Read-only operational status panels for existing generation runs, monthly batches, raw seed load runs, and jobs.
- HTMX polling for the active job status panel.
- Schema-driven generated configuration forms using backend configuration models as the source of truth.
- Configuration validation before saving a new version.
- Immutable configuration version creation.
- Raw ingest and seed normalization job launch actions.
- Generation plan creation action.
- Monthly pipeline launch action.
- Coarse progress updates at job, batch, and stage level.
- Guardrails that prevent obviously unsafe operations.
- Development and production environment visibility in the page header.

### Explicitly Out Of Scope For Version 1

- React, Vue, Svelte, or any SPA-style frontend architecture.
- WebSockets or real-time streaming infrastructure.
- Complex drag-and-drop workflow builders.
- Multi-user collaboration.
- Role-based access control.
- Full job cancellation.
- Advanced visual analytics dashboards.
- Config approval workflows.
- Full production hardening.
- Sophisticated worker queues such as Celery or RQ, unless FastAPI background execution becomes insufficient.

## Control Plane Responsibilities

The web layer should operate as a control plane. Its responsibilities are:

- Expose configuration state.
- Validate and save immutable configuration versions.
- Launch approved workload actions.
- Display job progress and recent operational history.
- Prevent unsafe or conflicting operations.
- Show environment and database context clearly.
- Provide operational visibility into simulation readiness.

The web layer should not own the core simulation business logic. Pipeline rules, generation logic, rating logic, seed preparation logic, and validation logic should remain in backend service modules or existing pipeline scripts. The control panel should call those services and display their status.

## Page Structure

Use a single server-rendered page:

```text
/control
```

The page should have three primary tabs:

1. Configuration Control
2. Workload Orchestration
3. Student Dataset Generation

Recommended secondary layout:

```text
Header
- Environment/database summary
- Active configuration profile/version
- Running job indicator
- Current operator mode: development or production

Tabs
- Configuration Control
- Workload Orchestration
- Student Dataset Generation

Persistent Status Bar
- Latest job status
- Current phase
- Percent complete
- Last refresh time
```

HTMX partials should update tab bodies and job status panels without a full page reload.

## Frontend Architecture Position

The initial implementation should not use React. React is unnecessary for this operational control panel and would add avoidable complexity through client-side state management, a frontend build pipeline, and component-level synchronization issues.

The preferred approach is:

```text
FastAPI routes
  -> Jinja2 templates
    -> HTMX partial refreshes
      -> Small amount of plain JavaScript only where necessary
```

HTMX should be used for:

- Tab content refreshes.
- Form validation submissions.
- Save-new-version actions.
- Job launch actions.
- Job status polling.
- Refreshing recent jobs, generation runs, and monthly batch tables.

Plain JavaScript should be limited to small UI helpers such as confirmation toggles, collapsible sections, and optional client-side display enhancements. Server-side state should remain authoritative.

## Environment Model

The web layer should support two named environments:

1. Development
2. Production

Both environments should use the same schema design. The active environment must be shown prominently in the page header.

Recommended environment guardrails:

- Show a clear environment label in the header.
- Use a stronger visual warning when connected to production.
- Require explicit confirmation for write-heavy production actions.
- Consider making production read-only in the first implementation until production workflows are proven safe.
- Display the configured database name or safe database alias.
- Never hide the active environment from the operator.

The control panel should make it difficult to accidentally run a large or destructive workload against the wrong database.

## Tab 1: Configuration Control

The Configuration Control tab should edit and version the full generation configuration payload stored in:

- `configuration_profiles`
- `configuration_profile_versions`

Configuration edits should create new immutable profile versions. A generation run must freeze its selected configuration into `generation_runs.parameter_snapshot` before any workload starts.

### Required Capabilities

- Select active configuration profile.
- View latest valid version.
- View older versions.
- Create a new version from an existing version.
- Edit configuration groups through generated forms.
- Validate edits before saving.
- Mark a version as valid or invalid.
- Start a generation run from a selected version only when all configuration items are valid.
- Provide a generation run start time and progressing duration indicator.
- Show field-level changes compared with the previous version.

### Editing Model

Use schema-driven generated forms rather than manually maintained form fields.

The authoritative configuration schema should come from backend configuration models. The same schema should drive:

- Field names.
- Field types.
- Defaults.
- Validation rules.
- Min/max constraints.
- Enumerations.
- Required fields.
- Help text.
- Grouping metadata.
- Advanced/basic field visibility.

The UI should still present fields in manually curated domain groups so the page remains understandable. Generated fields should appear inside these groups, not as one giant JSON editor.

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
- Injury modeling
- Tournament simulation
- Export settings
- Validation thresholds
- Runtime settings
- Experimental features

Each field should have:

- Label.
- Current value.
- Type-specific input.
- Validation hint on hover over the field label.
- Default value indicator.
- Changed-from-version marker.
- Basic or advanced designation.
- Optional description from the backend schema.

Use appropriate controls:

- Numeric inputs for counts and thresholds.
- Sliders only for bounded probability-style values when precision is not critical.
- Checkboxes for booleans.
- Select menus for enumerations.
- Editable key/value tables for weight maps.
- Text inputs for names and versions.
- Read-only display for computed or deprecated values.

### Configuration Version States

Configuration versions should use explicit states.

Recommended states:

```text
draft
validated
valid
invalid
deprecated
archived
```

Definitions:

- `draft`: A candidate configuration payload that has not yet passed validation.
- `validated`: A candidate version has passed validation but has not been promoted for use.
- `valid`: Approved for generation runs.
- `invalid`: Failed validation or manually marked unusable.
- `deprecated`: Previously valid but no longer recommended.
- `archived`: Retained for history but hidden from normal selectors.

Only `valid` configuration versions should be eligible for generation run creation.

### Validation

Configuration validation should run before a new version can become valid.

Validation should check:

- Probabilities are between `0` and `1`.
- Weight groups sum to `1.0`.
- Minimums are less than maximums.
- Target counts are positive.
- Rating bounds are coherent.
- Month counts are within supported limits.
- Required groups are present.
- Unknown keys are either rejected or clearly flagged.
- Runtime settings are compatible with the selected scale.
- Experimental flags do not enable unsupported combinations.

Validation results should be shown inline next to the affected field and also in a summary panel.

### Save Behavior

Do not mutate existing profile-version payloads.

Recommended save flow:

1. User edits draft values in the generated form.
2. User clicks `Validate`.
3. Server validates and returns inline errors/warnings.
4. If valid, user clicks `Save New Version`.
5. Server inserts a new `configuration_profile_versions` row.
6. UI updates active version selector and version history.
7. UI shows a version-to-version change summary.

### Configuration Diffing

Configuration versioning should include a basic diff view.

The initial version should show:

- Fields changed from the parent version.
- Previous value.
- New value.
- Whether the change affects scale, randomness, scheduling, ratings, or runtime behavior.

This is important for debugging, reproducibility, and explaining why simulation results changed across runs.

## Tab 2: Workload Orchestration

The Workload Orchestration tab should control two major stages:

1. Raw Data Ingest and Seed Data Generation
2. Workflow Control and Status

Student-facing parquet dataset generation is intentionally managed in a separate
Student Dataset Generation tab because it is a publication/export workflow, not
a core simulation execution workflow.

These stages should be visible as separate panels inside the same tab.

## Stage 1: Raw Data Ingest And Seed Data Generation

This stage prepares the reference data needed by generation jobs.

- This stage can run independently of the data generation pipeline.
- This stage must not run when the data generation pipeline is active.
- This stage should be blocked when another write-heavy seed preparation job is already running.

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

- Raw load status.
- Latest `raw_seed_load_runs` status.
- Rows read.
- Rows loaded.
- Rows rejected.
- Latest load time.
- Error count.
- Normalize status.
- Production row count.

Controls:

- Load selected raw datasets.
- Normalize selected datasets.
- Replace production rows, behind a confirmation checkbox.
- Run all required seed-prep steps in order.
- View latest ingest errors.

### Seed Data Readiness Panel

Before simulation workflows can run, show readiness checks:

- Regions loaded.
- First names loaded.
- Last names loaded.
- Clubs loaded.
- State/province bias data loaded where expected.
- Default configuration profile exists and has a valid version.
- Required raw datasets have successful load and normalization history.

Use this panel to prevent generation runs from starting against incomplete reference data.

## Stage 2: Workflow Control And Status

This stage creates generation plans and runs monthly generation.

Existing command equivalents:

- `backend/scripts/create_generation_plan.py`
- `backend/scripts/run_monthly_pipeline.py`

### Generation Plan Controls

Inputs:

- Generation name.
- Configuration profile.
- Configuration version.
- Seed value.
- First batch month.
- Historical month count.
- Initial player count override.

Actions:

- Create generation plan.
- Preview planned monthly batches.
- Start selected plan.

### Monthly Pipeline Controls

Inputs:

- Generation run.
- Start batch.
- Month count, capped at `12`.
- Player count override.
- Skip existing stages.
- Fail on existing stages.

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

The current implementation supports the first five stages. Validation and export should appear as planned/disabled stages until implemented.

## Tab 3: Student Dataset Generation

The Student Dataset Generation tab should manage creation of student-facing parquet
dataset releases from the clean, validated simulation database.

This tab should be treated as a controlled export and publication workflow, not
as part of the core simulation generation pipeline.

### Purpose

The purpose of this tab is to allow the instructor/operator to generate
student-facing analytical datasets while concealing internal simulation details.

The exported parquet datasets should support:

- one-year historical data releases
- monthly incremental match-result releases
- analytics and machine learning assignments
- student-developed rating systems
- Monte Carlo tournament simulation
- dashboarding and exploratory analysis
- optional public release through GitHub or Kaggle

The exported datasets must not expose:

- generator configuration payloads
- internal generation run logs
- export logs
- batch run metadata
- raw seed data
- internal hidden ratings
- hidden simulation parameters
- operational job metadata

### Recommended Export Flow

Student-facing parquet generation should occur after the database pipeline has
completed clean data generation and validation.

Recommended flow:

```text
Run simulation pipeline into clean database
        ↓
Validate ORM, database constraints, and FK integrity
        ↓
Select student-facing release scope
        ↓
Project allowed student-facing columns
        ↓
Apply optional data quality injection to export dataframes
        ↓
Validate post-injection parquet datasets
        ↓
Write release folder
        ↓
Write instructor-only manifest
```

The data quality injection step should operate only on export dataframes and
parquet outputs. It must not mutate the authoritative database.

### Release Types

The tab should support two release types:

1. Historical baseline release
2. Monthly incremental release

#### Historical Baseline Release

The historical baseline release should contain one full year of historical
student-facing data.

Suggested release folder:

```text
release_YYYY_MM_historical/
```

This release is used for:

- initial student exploration
- model training
- ranking development
- feature engineering
- baseline tournament simulations

#### Monthly Incremental Release

Monthly releases should contain the next incremental month of student-facing
match results and updated analytical history.

Suggested release folder:

```text
release_YYYY_MM/
```

This release is used for:

- rolling model updates
- drift analysis
- incremental ingestion
- updated predictions
- operational analytics simulation

### Student Dataset Controls

Inputs:

- release name
- release type
- source generation run
- source configuration profile/version display only
- release month
- historical month count
- include dimensions
- include fact tables
- include derived summary tables
- include visible rating history
- include rating deltas
- include data dictionary
- include release manifest
- output folder
- overwrite existing release, behind confirmation checkbox

Actions:

- Preview release contents.
- Validate release readiness.
- Generate clean instructor preview export.
- Generate student-facing parquet release.
- Generate instructor-only manifest.
- Download or open release folder.
- View latest export validation results.

### Student-Facing Dataset Tables

The first version should support the following export groups.

Dimensions:

```text
dim_players.parquet
dim_clubs.parquet
dim_regions.parquet
```

Facts:

```text
fact_matches.parquet
fact_games.parquet
fact_team_memberships.parquet
fact_rating_history.parquet
```

Derived summaries:

```text
monthly_player_summary.parquet
monthly_region_summary.parquet
```

Metadata:

```text
release_manifest.parquet
data_dictionary.parquet
```

Tournament/event data, if implemented:

```text
tournament_events.parquet
```

### Protected Data Rules

The student dataset generation workflow must enforce field-level projection.

The following data must never be included in student-facing parquet files:

- actual hidden rating
- hidden skill rating
- internal confidence model values
- generator random seed values
- generator configuration payloads
- regional weighting configuration
- hidden matchmaking logic
- hidden fatigue calculations
- hidden injury susceptibility
- hidden player growth potential
- internal job status
- raw seed load metadata
- generation batch metadata
- export job logs
- validation job logs

The exported rating history may expose:

- visible rating
- visible rating delta
- visible confidence
- matches played
- wins
- losses

The exported rating history must not expose the actual hidden rating used by the
simulation engine.

### Data Quality Injection Controls

The Student Dataset Generation tab should include a dedicated Data Quality
Injection panel.

Data quality injection should be optional and configurable per release.

The control panel should expose a practical operator-facing subset of the full
data quality injection configuration.

#### Primary Configuration Items

Required controls:

- enable data quality injection
- injection level
- random seed
- apply to historical releases
- apply to monthly releases
- write instructor-only injection manifest
- write student-visible data quality summary
- preserve foreign key integrity
- preserve protected identifiers
- maximum affected rows percentage
- maximum affected fields per row

Supported injection levels:

```text
none
low
medium
high
very_high
```

Recommended default:

```text
medium
```

for historical releases, and:

```text
low
```

for monthly releases.

#### Injection Level Descriptions

The UI should describe each level in plain language.

```text
none
- No data quality issues are injected.

low
- Light operational imperfections.
- Suitable for introductory profiling and cleaning.

medium
- Moderate data quality issues.
- Suitable for standard graduate analytics assignments.

high
- Significant but bounded quality issues.
- Suitable for advanced analytics engineering assignments.

very_high
- Heavy but controlled imperfections.
- Suitable for capstone or challenge datasets.
```

#### Frequency Configuration

The initial UI should allow either:

1. simple level-based defaults, or
2. advanced override percentages.

For the first implementation, use level-based defaults and hide advanced
frequency overrides.

Advanced controls may include:

- field-level issue rate
- row-level issue rate
- categorical variant rate
- duplicate-like row rate
- maximum total affected rows
- per-table issue profile override

Suggested default frequency bands:

```text
none:
  field_issue_rate: 0.00%
  row_issue_rate: 0.00%
  categorical_variant_rate: 0.00%
  duplicate_like_row_rate: 0.00%

low:
  field_issue_rate: 0.10% - 0.50%
  row_issue_rate: 0.05% - 0.25%
  categorical_variant_rate: 0.10% - 0.30%
  duplicate_like_row_rate: 0.01% - 0.05%

medium:
  field_issue_rate: 0.50% - 2.00%
  row_issue_rate: 0.25% - 1.00%
  categorical_variant_rate: 0.30% - 1.00%
  duplicate_like_row_rate: 0.05% - 0.20%

high:
  field_issue_rate: 2.00% - 5.00%
  row_issue_rate: 1.00% - 3.00%
  categorical_variant_rate: 1.00% - 3.00%
  duplicate_like_row_rate: 0.20% - 0.75%

very_high:
  field_issue_rate: 5.00% - 10.00%
  row_issue_rate: 3.00% - 6.00%
  categorical_variant_rate: 3.00% - 6.00%
  duplicate_like_row_rate: 0.75% - 1.50%
```

These values should be configuration-driven, not hard-coded.

#### Eligible Issue Type Controls

The UI should allow the operator to enable or disable major issue categories.

Initial issue categories:

- missing optional values
- categorical variants
- formatting variants
- numeric outliers
- rounding variants
- timestamp jitter
- duplicate-like rows
- delayed visible rating updates
- soft join ambiguity

For the first version, expose these as checkboxes under an "Advanced Data
Quality Options" disclosure panel.

Default enabled issue categories:

- missing optional values
- categorical variants
- formatting variants
- rounding variants
- soft join ambiguity

Default disabled issue categories:

- numeric outliers
- timestamp jitter
- duplicate-like rows
- delayed visible rating updates

#### Per-Table Injection Controls

The initial implementation should support table-level enablement.

Recommended controls:

```text
dim_players
dim_clubs
dim_regions
fact_matches
fact_games
fact_team_memberships
fact_rating_history
monthly_player_summary
monthly_region_summary
```

For each table, show:

- injection enabled
- selected issue profile
- estimated affected rows
- protected key status
- validation status

The first version may use defaults instead of exposing full per-column controls.

#### Instructor-Only Manifest Controls

The operator should be able to generate an instructor-only injection manifest.

Recommended file:

```text
instructor_only/data_quality_injection_manifest.parquet
```

The manifest should include:

- release id
- table name
- record primary key
- column name
- issue type
- original value
- injected value
- injection level
- random seed
- rule id
- injected timestamp

This file must not be included in student release folders unless explicitly
overridden by an instructor-only export mode.

### Student Dataset Validation

Before a release is finalized, the control panel should show validation results.

Required checks:

- parquet files can be read
- required files are present
- expected row counts are within tolerance
- protected identifiers were not mutated
- primary key uniqueness is preserved
- foreign key joins remain valid
- hidden rating fields are absent
- generator configuration fields are absent
- operational metadata fields are absent
- data dictionary matches exported schemas
- data quality issue rates are within configured bounds

### Student Dataset Status Views

The tab should include:

- latest student release card
- release history table
- pending export job card
- post-export validation panel
- data quality injection summary
- instructor-only manifest status

Student release history table columns:

- release id
- release name
- release type
- release month
- source generation run
- data quality level
- match count
- player count
- generated at
- validation status
- output path

### Recommended Endpoints

```text
GET  /control/student-datasets
POST /control/student-datasets/preview
POST /control/student-datasets/validate
POST /control/student-datasets/generate
GET  /control/student-datasets/{release_id}
GET  /control/student-datasets/{release_id}/validation
GET  /control/student-datasets/{release_id}/manifest
```

### Recommended Job Types

Add the following job types to the `job_status` model:

```text
student_dataset_preview
student_dataset_validation
student_dataset_export
data_quality_injection
```

### Guardrails

The Student Dataset Generation tab should include the following guardrails:

- disable export until source generation run is complete
- disable export if seed/reference readiness checks fail
- require confirmation before overwriting an existing release folder
- require confirmation before using high or very_high injection levels
- clearly label instructor-only files
- never include instructor-only manifests in student downloads by default
- prevent mutation of database records
- prevent mutation of protected identifiers
- validate field projection before export
- show warning when data quality injection is disabled


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

### Job Status States

Use explicit job lifecycle states.

Recommended states:

```text
pending
queued
running
completed
failed
cancel_requested
cancelled
```

Definitions:

- `pending`: Job record has been created but execution has not started.
- `queued`: Job is waiting for available execution capacity.
- `running`: Job is actively executing.
- `completed`: Job finished successfully.
- `failed`: Job ended with an unrecovered error.
- `cancel_requested`: Operator requested cancellation, but execution has not stopped yet.
- `cancelled`: Job stopped due to cancellation.

For version 1, cancellation states can exist in the model even if no cancellation action is exposed yet.

### Job Ownership Hierarchy

The UI should not treat every job as an isolated event. Jobs should be displayed in relation to the higher-level simulation objects they affect.

Recommended hierarchy:

```text
generation_run
  -> monthly_batches
      -> pipeline_stages
          -> job_status entries
```

This relationship should help the operator understand whether a job belongs to seed preparation, plan creation, a generation run, a monthly batch, or a specific pipeline stage.

### Structured Job Metadata

`job_status` should gain structured JSON metadata for stage counts and result summaries.

Recommended column:

```text
metadata_json
```

Potential contents:

- Current batch.
- Total batch count.
- Current stage.
- Stage index.
- Total stages.
- Rows read.
- Rows written.
- Rows rejected.
- Stage result summaries.
- Output file references.
- Validation warning counts.

This metadata should support richer status displays without requiring a new table for every progress detail.

### Structured Job Logs

Add or plan for a structured job log table.

Recommended fields:

- `id`
- `job_id`
- `timestamp`
- `severity`
- `phase`
- `message`
- `metadata_json`

Version 1 can show only the most recent log messages. Future versions can add filtering, expansion, and export.

## Generation Run States

Generation runs should use explicit lifecycle states.

Recommended states:

```text
planned
ready
running
partial_failure
completed
failed
cancelled
```

Definitions:

- `planned`: Run has been defined but not yet checked for readiness.
- `ready`: Prerequisites are satisfied and the run can start.
- `running`: One or more monthly batches are executing.
- `partial_failure`: Some stages or batches failed while others completed.
- `completed`: All planned batches and supported stages completed.
- `failed`: Run cannot continue without intervention.
- `cancelled`: Run was stopped by operator request.

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

- Stage started.
- Stage completed.
- Row counts after each stage.
- Current batch index out of total batches.

Later versions should add intra-stage counters for:

- Players generated.
- Club memberships created.
- Teams formed.
- Matches generated.
- Rating updates written.
- Files exported.

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

The response for `GET /control/jobs/{job_id}` should be a partial HTML fragment for HTMX and optionally JSON for future API use.

## Status Views

The Workload Orchestration tab should include:

- Current job card.
- Recent jobs table.
- Generation runs table.
- Monthly batches table.
- Raw seed load runs table.
- Validation/export placeholders.

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
- Show the selected database URL, database alias, or environment label in the header.
- Prevent launching two write-heavy jobs concurrently unless the job types are proven safe to run in parallel.
- Freeze configuration payloads into generation runs.
- Preserve immutable configuration versions.
- Show whether a stage will run, skip, or fail before starting.
- Require additional confirmation for production writes.
- Display a summary of expected affected rows when available.

## Concurrency Policy

The initial implementation should be conservative.

Recommended rules:

- Only one monthly pipeline job may run at a time.
- Seed ingest and seed normalization may not run while a monthly pipeline job is active.
- Generation plan creation may run only when no write-heavy generation job is active.
- Read-only status refreshes may run concurrently.
- Validation jobs may run concurrently only if they do not mutate shared state.
- Production write actions should be serialized.

If concurrency rules are violated, the UI should disable the action and explain which running job is blocking it.

## Idempotency And Rerun Strategy

The design should explicitly account for partial failures and reruns.

Each pipeline stage should define whether it is:

- Safe to rerun without deleting prior output.
- Safe to rerun only after deleting or replacing prior output.
- Not safe to rerun without manual intervention.

The UI should show whether a stage will:

- Run.
- Skip because output already exists.
- Fail because output already exists.
- Replace existing output after confirmation.

This matters for monthly pipeline reruns, seed normalization, ratings regeneration, and export stages.

## Authentication And Authorization

The initial implementation assumes a trusted local operator environment.

Version 1 does not need full authentication if the application is run locally and not exposed publicly. However, the design should not prevent future authentication or role-based access control.

Future versions should consider:

- Authenticated operator login.
- Admin/operator/read-only roles.
- Production write restrictions.
- Audit history of who started each job.
- Local-only binding by default.

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
    student_datasets.py
  templates/
    control.html
    partials/
      config_tab.html
      workload_tab.html
      job_status.html
      generation_runs.html
      monthly_batches.html
      student_datasets_tab.html
      student_dataset_validation.html
      raw_seed_runs.html
      validation_summary.html
  static/
    control.css
```

### Job Execution

For local development, FastAPI `BackgroundTasks` is acceptable for the first version.

If jobs need cancellation, restart durability, or multiple workers, move to a real queue later. The design should avoid assuming that request handlers own the job lifecycle.

### Frontend

Use restrained operational styling:

- Dense but readable tables.
- Clear status chips.
- Compact form groups.
- Sticky job status area.
- Tabs for the two major workflows.
- No landing page.
- No decorative cards inside cards.
- No SPA framework for the first implementation.

The first screen should be the control panel itself.

## Suggested Build Order

1. Add FastAPI app shell and `/control` route.
2. Render one-page layout with two tabs.
3. Add environment header and persistent status strip.
4. Add read-only status panels for configuration, generation runs, monthly batches, raw load runs, and jobs.
5. Add job-status polling partial.
6. Add configuration viewer.
7. Add schema-driven generated configuration form renderer.
8. Add configuration validation and save-new-version flow.
9. Add configuration diff summary.
10. Add raw ingest and normalize job launch actions.
11. Add generation-plan job launch action.
12. Add monthly-pipeline job launch action.
13. Add progress updates inside pipeline stages.
14. Add structured job metadata.
15. Add structured job logs.
16. Add cancellation and log detail views.

## Open Design Questions

- Should configuration editing use generated forms from a schema, or manually maintained grouped forms?
  - Answer: Configuration editing should use schema-driven generated forms. The backend configuration models should remain the source of truth for field definitions, validation metadata, defaults, ranges, and descriptions. The web layer should render those fields inside manually curated groups organized around major simulation domains.
- Should `job_status` gain structured JSON metadata for stage counts and result summaries?
  - Answer: Yes. This is important to clearly articulate status and avoid overloading simple text fields.
- Should long-running jobs be cancellable in the first version?
  - Answer: No. Add the status model support now if practical, but place user-facing cancellation controls in the future enhancement backlog.
- Should the web layer support multiple named environments, or only the local development database?
  - Answer: The web layer should support development and production environments. These should be two databases with the exact same schema design. The active environment must be displayed clearly, and production write actions should require stronger confirmation.
- Should validation/export be visible as disabled stages immediately, or hidden until implemented?
  - Answer: Show them as disabled/planned stages now. Add their full development and implementation to the future enhancement backlog.
- Should React be introduced later if the UI grows?
  - Answer: Not by default. The preferred long-term posture is still server-rendered HTML with HTMX unless the control panel develops requirements that clearly justify a SPA framework.

## Future Enhancement Backlog

### Student Dataset Generation Enhancements

- Advanced per-column data quality rule editing.
- Student dataset release comparison.
- Kaggle-ready packaging mode.
- GitHub public release packaging mode.
- Instructor-only truth export bundle.
- Hidden benchmark/holdout dataset generation.
- Student-facing data quality summary report.
- Automated parquet schema compatibility checks across releases.
- Release signing and checksum generation.
- Dataset version lineage visualization.
- Release notes generator.
- Dataset preview notebooks.
- Multiple difficulty profiles for the same clean source data.
- Download bundle creation for student release folders.



### Operational Enhancements

- Job cancellation support.
- Structured job log viewer with filtering.
- Log export for failed jobs.
- Retry failed stage capability.
- Automatic failed-job recovery recommendations.
- Estimated runtime calculations.
- Pipeline dependency graph visualization.
- Manual stage rerun controls.
- Background worker queue migration to Celery, RQ, Dramatiq, or equivalent.
- Job prioritization.
- Job history retention policy.

### Configuration Enhancements

- Config import/export.
- Config cloning.
- Config comparison across any two versions.
- Config templates and presets.
- Config schema migration tooling.
- Field-level advanced help panels.
- Experimental feature flags.
- Config approval workflow.
- Search/filter within configuration fields.
- Collapsible advanced configuration sections.

### Simulation Enhancements

- Dry-run simulation validation mode.
- Statistical sanity validation.
- Historical run comparison dashboards.
- Seed reproducibility validation.
- Monte Carlo orchestration controls.
- Multi-generation comparison runs.
- Validation stage implementation.
- Export stage implementation.
- Tournament simulation controls.

### UX Enhancements

- Dark mode.
- Keyboard shortcuts.
- Collapsible tables and panels.
- Batch operation controls.
- Live progress charts.
- More detailed run summaries.
- Operator notes on configuration versions and generation runs.

### Security And Environment Enhancements

- Authentication.
- Role-based permissions.
- Read-only production mode.
- Production environment locking.
- Audit history.
- Operator activity logging.
- Environment-specific feature flags.

### Observability Enhancements

- Structured metrics.
- Runtime performance dashboards.
- Pipeline timing breakdowns.
- Failure analytics.
- Stage throughput metrics.
- Database health monitoring.
- Dataset freshness indicators.

## Recommendation

Build the first version as a single-page HTMX control panel with server-rendered partials and background jobs. Keep it intentionally operational: configuration editing on one tab, workload orchestration on the other, with a persistent job status strip that always tells the operator what is running and what happened last.

The most important architectural boundary is that the web layer should remain a control plane. It should expose, validate, launch, and observe backend workflows. It should not become the owner of simulation, generation, rating, or pipeline business logic.
