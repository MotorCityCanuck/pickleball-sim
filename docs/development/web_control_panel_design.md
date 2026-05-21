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
- Three primary tabs: Seed Data Config, Player and Match Config, and Workload Orchestration.
- Read-only operational status panels for existing generation runs, monthly batches, raw seed load runs, and jobs.
- HTMX polling for the active job status panel.
- Schema-driven generated configuration forms using backend configuration models as the source of truth.
- Configuration validation before saving a new version.
- Immutable configuration version creation.
- Raw ingest and seed normalization job launch actions.
- Full generation preview action derived from the current valid configuration.
- Full destructive generation run launch action.
- Student-facing parquet release generation as the final workload stage.
- Stage-level progress bars with persisted progress snapshots and heartbeat freshness.
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

1. Seed Data Config
2. Player and Match Config
3. Workload Orchestration

Recommended secondary layout:

```text
Header
- Environment/database summary
- Active configuration profile/version
- Running job indicator
- Current operator mode: development or production

Tabs
- Seed Data Config
- Player and Match Config
- Workload Orchestration

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

## Tab 1: Seed Data Config

The Seed Data Config tab should edit the seed-preparation subset of the full
generation configuration payload stored in:

- `configuration_profiles`
- `configuration_profile_versions`

This tab is one view into the canonical configuration working copy. It does not
own a separate save pipeline or a separate saved payload. Validation and save
must still operate on the recombined full configuration payload.

Configuration edits should create new immutable profile versions. There should
be exactly one current valid configuration set. A generation run must freeze
that selected configuration into `generation_runs.parameter_snapshot` before
any workload starts.

### Configuration Storage Model

Configuration versions should be stored as immutable validated JSON/JSONB
payloads with structured relational lifecycle metadata. The system should not
fully normalize every configuration parameter into separate database tables for
the first implementation.

Recommended storage shape:

```text
configuration_profile_versions
- id
- profile_id
- version_number
- title
- notes
- lifecycle_status
- created_at
- created_by
- last_used_at
- deprecated_at
- config_schema_version
- config_hash
- config_payload
```

The `config_payload` field contains the full generation configuration. Individual
configuration parameters are keys inside that payload, not columns on
`configuration_profile_versions`.

JSON/JSONB storage is acceptable only when paired with typed validation. The
backend configuration models should parse and validate the payload before it can
be saved. Arbitrary unvalidated JSON should never become a saved valid
configuration version.

This approach keeps the database manageable while preserving:

- schema validation
- immutable version snapshots
- configuration diffing
- lifecycle management
- generation reproducibility
- future schema migration flexibility

Relational columns should be reserved for lifecycle, identity, audit,
reproducibility, and orchestration fields. Nested simulation parameters,
probability distributions, thresholds, data quality settings, and export options
should remain inside the validated payload.

### Required Capabilities

- Load the current valid configuration by default.
- View the current valid version.
- Create a new immutable version from the edited working copy.
- Edit configuration groups through generated forms.
- Validate edits before saving.
- Require a brief user-provided title before saving a new version.
- Assign version numbers automatically when a validated configuration is saved.
- Track when each saved version was created, last used, and deprecated.
- Automatically deprecate the prior valid version when a new version is saved.
- Start a generation run only from the single current valid configuration version.
- Require changes to seed, first generated month, generated month count, player scale, or other generation settings to be made through a new valid configuration version.
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

The UI should still present fields in manually curated domain groups so the page remains understandable. Generated fields should appear inside these groups, not as one giant undifferentiated editor.

Suggested configuration-tab split:

1. Seed Data Config
2. Player and Match Config

The Seed Data Config tab should contain raw ingest and seed-preparation
settings such as:

- `raw_seed_data`
- `name_assignment`
- `regional`
- `club_generation`

The Player and Match Config tab should contain synthetic workload settings such
as:

- `runtime`
- `simulation`
- `player_generation`
- team formation settings
- match scheduling settings
- rating settings
- data quality and export settings

The control panel may still store and validate one full configuration payload,
but the editing experience should present the seed-preparation subset and the
player/match-generation subset on separate top-level config tabs that are
recombined before validation and save.

Within each config tab, the page should use manually curated section cards.
Because the total parameter count is large, the page should not rely on one
fully expanded scroll. The preferred interaction pattern is:

- collapsible section panels
- one or a few open sections at a time by default
- section summaries when collapsed
- `Basic` versus `Advanced` visibility toggles driven by metadata
- search/filter across labels, field paths, and help text
- advanced JSON fallback at the section level for rare or not-yet-promoted settings

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
- Checkboxes or toggle switches for booleans.
- Radio groups only for small mutually exclusive enumerations where seeing all options at once improves comprehension.
- Select menus for enumerations with more options or less frequent use.
- Editable key/value tables for weight maps.
- Editable min/max tables for bounded range maps.
- Text inputs for names and versions.
- Read-only display for computed or deprecated values.

### Configuration Version Lifecycle

The first implementation should avoid a complex configuration state machine.
The edit panel should operate on an unsaved working copy until the operator
validates and saves it.

Default behavior:

```text
Load current valid configuration
        ↓
Operator edits fields
        ↓
Validate Configuration
        ↓
If validation passes, show Save New Version
        ↓
Operator provides a short title
        ↓
System saves an immutable version number
        ↓
New version becomes valid and prior valid version becomes deprecated
```

Important distinctions:

- Unsaved edits are not configuration versions.
- Saved versions are immutable.
- A saved version must have passed validation before it is created.
- Exactly one saved version should have lifecycle status `valid`.
- Prior saved versions should have lifecycle status `deprecated`.
- Deprecated versions are retained in the database for audit/history but hidden
  from the normal UI and not eligible for generation.
- Runtime generation settings such as seed, first generated month, generated
  month count, and player scale come from the current valid configuration. The
  workload orchestration panel should display these values but should not expose
  one-off overrides.

Recommended lifecycle metadata for saved versions:

- `version_number`: assigned by the system, increasing within each profile.
- `title`: required short user-provided title.
- `description` or `notes`: optional longer explanation.
- `created_at`: when the immutable version was saved.
- `created_by`: optional for the first implementation.
- `last_used_at`: most recent time the version was used to create or start a generation run.
- `deprecated_at`: when the version was replaced by a newer valid version.
- `lifecycle_status`: `valid` or `deprecated`.

For the first implementation, only validated configurations should be saved as
versions. Validation failure should not create a database version. Saving a new
version should be transactional: insert the new valid version and deprecate the
prior valid version in the same operation.

The ORM and database schema will be updated during the build process to support
this simplified lifecycle. Expected updates include adding a version title,
optional notes, `last_used_at`, `deprecated_at`, renaming or replacing
`validation_status` with a lifecycle field, and enforcing exactly one valid
configuration version.

### Validation

Configuration validation should run before a new version can be saved.

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

If the operator changes any field after validation succeeds, the UI should
invalidate the validation result and return to the `Validate Configuration`
action. The `Save New Version` action should only be available for the exact
payload that passed validation.

### Save Behavior

Do not mutate existing profile-version payloads.

Recommended save flow:

1. UI loads the current valid configuration into an editable working copy.
2. User edits values in the generated form.
3. Server validates and returns inline errors/warnings.
4. If valid, UI enables `Save New Version`.
5. User provides a required short title and optional notes.
6. Server inserts a new immutable `configuration_profile_versions` row and assigns the next version number.
7. Server marks the previous valid version as deprecated in the same transaction.
8. UI updates the current version display.
9. UI shows a version-to-version change summary.

### Metadata-Driven Editor Rollout

The preferred end state is a metadata-driven configuration editor generated from
backend-owned field definitions. The backend should remain the source of truth
for:

- field paths
- labels
- help text
- defaults
- min/max/step constraints
- enum options
- control types
- basic versus advanced visibility
- section grouping

The frontend should not hardcode these rules independently.

Recommended incremental rollout:

1. Keep the current JSON editor as the active editing surface.
2. Add backend metadata definitions and payload-reading helpers for the future generated editor.
3. Expand backend validation coverage so the validation model matches the metadata model.
4. Render metadata-driven read-only or prototype form sections beside or behind the JSON editor during review.
5. Replace the JSON editor only after the generated form coverage is complete enough for day-to-day operator use.

During the transition period, the JSON editor should remain available as an
advanced fallback and debugging tool.

The initial metadata scaffold should include:

- typed section definitions for seed and synthetic scopes
- typed field definitions for the major simulation domains
- support for scalar inputs, booleans, enums, sliders, weight tables, range tables, and JSON fallback controls
- helpers that resolve current field values from the canonical payload
- tests confirming metadata paths resolve against the default configuration payload

The metadata scaffold is not itself a second configuration store. It is only a
view model over the canonical validated payload.

### Configuration Diffing

Configuration versioning should include a basic diff view.

The initial version should show:

- Fields changed from the parent version.
- Previous value.
- New value.
- Whether the change affects scale, randomness, scheduling, ratings, or runtime behavior.

This is important for debugging, reproducibility, and explaining why simulation results changed across runs.

## Tab 2: Player and Match Config

The Player and Match Config tab should edit the synthetic workload subset of
the same full generation configuration payload.

This tab is a second view into the same working copy used by Seed Data Config.
Both config tabs should support `Validate Configuration` and `Save New Version`
without introducing separate draft states. Switching between tabs should not
discard edits.

Suggested major groups inside this tab:

- Simulation Identity and Execution
- Player Population and Demographics
- Team Formation
- Match Scheduling
- Matchmaking
- Games and Scores
- Ratings and Confidence
- Availability, Injury, and Seasonality
- Validation and Export
- Experimental / Future Extensions

For usability, this tab should not render all configuration groups fully
expanded at once. It should prefer:

- collapsible section panels
- section summary rows when collapsed
- a `Show advanced settings` toggle using backend `basic_or_advanced` metadata
- search/filter by field label, path, or help text
- structured fallback editors such as weight tables, range tables, and
  section-level JSON editors for rarely changed or still-unmapped settings

## Tab 3: Workload Orchestration

The Workload Orchestration tab should present two independent operational
stages:

1. Generate New Seed Data
2. Generate Player and Match Data

Student-facing parquet dataset generation remains the final step inside Stage 2.
It is not a separate top-level orchestration stage or a separate top-level tab.

These two stages should be visible as separate panels inside the same tab.

### Simplified Operational Contract

The Version 1 control panel should deliberately avoid becoming a general
orchestration system.

- There is exactly one current valid configuration version.
- Saving a new configuration version automatically deprecates the prior valid version.
- Seed/reference data is treated as fixed operational input for Version 1 once prepared.
- Seed/reference data changes only through an explicit raw ingest and seed
  normalization workflow.
- Seed preparation and synthetic generation are separate operator actions.
- Seed preparation may run independently when no synthetic generation job is pending or active.
- Only the web control panel may start a generation run.
- A generation run may start only from the current valid configuration version.
- A generation run may start only when seed/reference readiness checks pass.
- Only one generation run may be `pending` or `running` at a time.
- Every generation run starts from the beginning.
- Every generation run is destructive to generated domain data.
- Generation runs must not delete seed/reference data or saved configuration versions.
- Failed generation runs are not resumable from a midpoint.
- Retrying after failure requires a new full destructive generation run.
- Student dataset releases may use only the current generation run after it has `succeeded`.

## Stage 1: Generate New Seed Data

This stage prepares or refreshes the reference data needed by synthetic
generation jobs.

- This stage can run independently of synthetic generation.
- This stage must not run when player/match generation is pending or active.
- This stage should be blocked when another write-heavy seed preparation job is already pending or running.
- Version 1 should treat normalized seed/reference data as fixed operational
  input once prepared. The system does not need seed dataset version lineage for
  the first implementation.
- Changing seed/reference data requires running the explicit raw ingest and seed
  normalization workflow again.

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
- Exactly one current valid configuration version exists.
- Required raw datasets have successful load and normalization history.

Use this panel to prevent generation runs from starting against incomplete reference data.

### Seed Data Versioning Position

Seed dataset version lineage is a future enhancement. The seed datasets are
large and difficult to persist as historical versions, so Version 1 should not
attempt to snapshot or version seed/reference data for every generation run.

For Version 1:

- Treat normalized seed/reference data as fixed operational input.
- Allow seed/reference changes only through explicit raw ingest and seed
  normalization actions.
- Preserve seed/reference data when a destructive generation run starts.
- Do not expose seed version selection in the UI.
- Do not attempt to replay historical generation runs against old seed data.

If seed/reference data changes, subsequent generation runs use the currently
loaded seed/reference data. Reproducibility for Version 1 is primarily based on
the saved configuration snapshot and the current prepared seed/reference state.

## Stage 2: Generate Player And Match Data

This stage starts full generation runs and displays generation progress.
Generation starts are deliberately narrow in Version 1: only the web control
panel may kick off a generation run, every run starts from the beginning, and
every run is destructive to generated data.

There should be no operator-facing generation plan concept in Version 1. The
current valid configuration is the plan. The preview shown before launch should
be derived from that configuration and should not create a separate persistent
plan object.

The generation service should own the full run lifecycle:

```text
validate current configuration
        ↓
create pending job_status row
        ↓
create generation run record
        ↓
freeze parameter_snapshot
        ↓
commit pending launch state
        ↓
start background worker execution
        ↓
destructively reset generated data
        ↓
create monthly batch records
        ↓
execute generation stages from the beginning
        ↓
mark generation run succeeded or failed
```

Web routes should register the pending launch, commit it, enqueue background
execution, and then return immediately. They should poll job status and must
not contain their own independent lifecycle logic.

### Full Generation Run Controls

Inputs:

- Generation name.
- Current valid configuration version, display only.
- Seed value from the current valid configuration, display only.
- First generated month from the current valid configuration, display only.
- Generated month count from the current valid configuration, display only.
- Player scale or target player count from the current valid configuration, display only.
- Destructive run confirmation.

Actions:

- Preview full generation run.
- Start full generation run.

Generation start rules:

- A run may start only when the current configuration version is valid.
- A run may start only when Stage 1 seed/reference readiness checks pass.
- A run may start only when no generation run or generation job is currently `pending` or `running`.
- A run must use seed, first generated month, generated month count, player scale,
  and all other runtime generation settings from the current valid configuration.
- The workflow orchestration UI must not allow one-off overrides for generation
  settings. If a different value is needed, the operator must save a new valid
  configuration version first.
- A run must delete and rebuild generated domain data.
- A run must not delete seed/reference data or saved configuration versions.
- A run must freeze the current valid configuration into `generation_runs.parameter_snapshot`.
- A failed generation run cannot resume from a midpoint. A retry must create a new full destructive run from the beginning.

Generated data reset should delete generated-domain and run-specific data in a
defined dependency order. It should not reset raw seed data, normalized
seed/reference tables, saved configuration versions, or system configuration.

Required destructive delete order:

```text
1. job_stage_progress
2. student_dataset_release_files
3. student_dataset_releases
4. validation_results
5. export_runs
6. batch_runs
7. ratings_update_log
8. player_rating_history
9. player_assessment_history
10. match_team_players
11. match_games
12. match_teams
13. matches
14. team_memberships
15. teams
16. club_memberships
17. player_registrations
18. players
19. tournaments
20. monthly_batches
```

Preserved tables:

```text
configuration_profiles
configuration_profile_versions
generation_runs
job_status
uploaded_files
regions
first_names
last_names
clubs
```

`generation_runs` and `job_status` should be preserved as operational
audit/control records. The current generation run is the latest run created by
the generation service, not any older succeeded run whose generated data has
already been reset.

### Generation Progress Display

Implemented generation stages shown per batch:

```text
players
club_memberships
teams
matches
ratings
```

For Version 1, a generation run may become `succeeded` when the implemented
generation stages complete successfully. Future validation and student release
steps must not be treated as required generation completion criteria.

Future post-generation workflow steps may be shown as disabled or planned items:

```text
validation
student_dataset_release
```

These planned items should be visually distinct from incomplete or failed
implemented stages. The UI should label them as `not implemented` or `planned`,
not `incomplete`.

Each implemented stage should have its own progress bar. The progress bar should
be driven by persisted progress metadata, not by client-side timers or inferred
elapsed time.

Recommended per-stage display:

```text
Stage: matches
Status: running
Progress: 425,000 / 1,800,000 matches
Percent: 23.6%
Last update: 42 seconds ago
Message: Simulating matches for 2027-04
```

Progress bars should support these states:

- `not_started`: empty bar.
- `running` with known total: determinate progress bar.
- `running` with unknown total: indeterminate bar plus processed count and
  heartbeat age.
- `succeeded`: full bar with final count summary.
- `failed`: failed bar state with error summary.

Long-running stages must persist progress periodically during execution. A stage
should update progress every configured row-count interval, object-count
interval, or elapsed-time interval, whichever comes first. The UI should show a
stale warning when the latest heartbeat is older than the configured threshold,
but stale progress should be treated as an operational warning rather than an
automatic failure.

## Stage 3: Student Dataset Release Generation

The Student Dataset Release Generation stage should manage creation of
student-facing parquet dataset releases from the clean, validated simulation
database.

This stage should be treated as a controlled export and publication workflow,
not as part of the core simulation generation pipeline.

### Purpose

The purpose of this stage is to allow the instructor/operator to generate
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

### Release Readiness Requirements

Student dataset release generation must be blocked unless all release
readiness requirements pass.

Required readiness checks:

- The source generation run is the current generation run.
- The source generation run has `status = succeeded`.
- All monthly batches in the selected release scope have `processing_status = succeeded`.
- No generation, seed ingest, seed normalization, or other write-heavy job is running.
- Seed/reference readiness checks pass.
- The student-facing table and column projection inventory is complete.
- Every included table has every exported column classified.
- No unclassified table or column is allowed in the release.
- Protected-field scan passes before parquet writing.
- Hidden rating, generator configuration, seed, operational metadata, and job/log fields are absent from projected export dataframes.
- Referential integrity checks pass for the projected student-facing tables.
- No validation blockers are present.

If any readiness check fails, the UI should disable release generation and show
the blocking reason. Readiness validation should run before data quality
injection and before writing parquet files.

### Release Types

The stage should support two release types:

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

### Release Tracking Model

Student dataset generation should have a release-level database entity. This is
still the final stage inside Workload Orchestration; it is not a separate
top-level tab. The release entity exists so the system can track a coherent
student release package across multiple parquet files, validation steps, data
quality injection, and manifest generation.

`export_runs` should remain lower-level export/file tracking. It should not be
overloaded as the operator-facing student release record.

Recommended new ORM/database tables for the build process:

```text
student_dataset_releases
student_dataset_release_files
```

Recommended `student_dataset_releases` fields:

- `id`
- `release_name`
- `release_type`: `historical_baseline` or `monthly_incremental`
- `release_month`
- `generation_run_id`
- `data_quality_level`
- `output_path`
- `status`: `pending`, `running`, `succeeded`, or `failed`
- `created_at`
- `completed_at`
- `error_message`

Recommended `student_dataset_release_files` fields:

- `id`
- `release_id`
- `table_name`
- `file_path`
- `row_count`
- `schema_hash`
- `checksum`
- `created_at`

The release table should be the source for release history, release status,
output folder display, and student release validation summaries. File-level
records should be used for reconciliation, checksums, row counts, and per-file
debugging.

### Student Dataset Controls

Inputs:

- release name
- release type
- source generation run
- source configuration profile/version display only
- release month
- historical month count
- include approved operational source tables
- include visible rating history
- include rating deltas
- include data dictionary
- include release manifest
- include table relationship guide
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

The first version should export approved operational-style table extracts. It
must not generate instructor-prebuilt dimensional models, fact tables, or
derived summary tables for students. Students are expected to construct those
structures themselves as part of the assignment.

Student-facing table files should use operational-style names that mirror the
approved source tables unless a safe rename is required for clarity.

```text
players.parquet
clubs.parquet
regions.parquet
teams.parquet
team_memberships.parquet
matches.parquet
games.parquet
rating_history.parquet
```

Metadata:

```text
release_manifest.parquet
data_dictionary.parquet
table_relationships.parquet
```

The release must not include files such as:

```text
dim_players.parquet
dim_clubs.parquet
dim_regions.parquet
fact_matches.parquet
fact_games.parquet
fact_rating_history.parquet
monthly_player_summary.parquet
monthly_region_summary.parquet
```

Tournament/event data, if implemented:

```text
tournaments.parquet
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

The Student Dataset Release Generation stage should include a dedicated Data Quality
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
players
clubs
regions
teams
team_memberships
matches
games
rating_history
tournaments
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

- release readiness checks passed
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

The stage should include:

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

The Student Dataset Release Generation stage should include the following guardrails:

- disable export until source generation run is complete
- allow export only from the current generation run with `status = succeeded`
- require all selected-scope monthly batches to have `processing_status = succeeded`
- block export while any generation, seed ingest, seed normalization, or other write-heavy job is running
- disable export if seed/reference readiness checks fail
- block export if table/column projection classification is incomplete
- block export if protected-field scan fails
- block export if validation blockers are present
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
3. Server creates any other required pending orchestration rows such as `generation_runs`.
4. Server commits the pending launch state.
5. Server starts background execution.
6. Background worker updates `job_status`.
7. UI polls status endpoints with HTMX.
8. UI renders progress, current phase, and logs.

For the current implementation, local background execution uses an in-process
thread pool. The request handler owns validation and durable registration of
pending work, but it does not own the runtime of the long-running job after
that commit.

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
- `generation_preview`
- `generation_run`
- `validation`
- `export`

### Job Status States

Use explicit job lifecycle states.

Recommended states:

```text
pending
running
succeeded
failed
```

Definitions:

- `pending`: Job record has been created but execution has not started.
- `running`: Job is actively executing.
- `succeeded`: Job finished successfully.
- `failed`: Job ended with an unrecovered error.

Version 1 should not include job cancellation states. Cancellation is a future
feature and should not appear in the current job status lifecycle until the
system has a real cancellation mechanism.

The ORM and database schema will be updated during the build process so the
`job_status.status` constraint supports exactly:

```text
pending
running
succeeded
failed
```

### Job Ownership Hierarchy

The UI should not treat every job as an isolated event. Jobs should be displayed in relation to the higher-level simulation objects they affect.

Recommended hierarchy:

```text
generation_run
  -> monthly_batches
      -> job_stage_progress entries
  -> job_status entries
```

This relationship should help the operator understand whether a job belongs to seed preparation, a generation run, a monthly batch, or a specific pipeline stage.

### Structured Job Metadata

`job_status` should gain structured JSON metadata for job-level counts and
result summaries. Per-stage progress should be stored in `job_stage_progress`,
not only inside job-level metadata.

Recommended column:

```text
metadata_json
```

Potential contents:

- Current batch.
- Total batch count.
- Rows read.
- Rows written.
- Rows rejected.
- Stage result summaries.
- Output file references.
- Validation warning counts.

This metadata should support richer job summaries without replacing the
dedicated stage progress table.

### Job Stage Progress

Add a dedicated `job_stage_progress` table to support per-stage progress bars.

Recommended fields:

- `id`
- `job_status_id`
- `generation_run_id`
- `batch_id`
- `stage_name`
- `stage_sequence`
- `status`: `pending`, `running`, `succeeded`, or `failed`
- `progress_current`
- `progress_total`, nullable when unknown
- `progress_unit`
- `progress_percent`, nullable when total is unknown
- `last_heartbeat_at`
- `progress_message`
- `started_at`
- `completed_at`
- `error_message`
- `metadata_json`
- `created_at`
- `updated_at`

The web UI should render progress bars from this table. Long-running workers
should update the current stage row periodically while work is running.

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

## Monthly Batch States

Monthly batches should use the same simplified lifecycle model as other
operator-facing execution records.

Recommended `monthly_batches.processing_status` values:

```text
pending
running
succeeded
failed
```

Definitions:

- `pending`: Batch record exists, but the batch has not started.
- `running`: One or more generation stages for the batch are executing.
- `succeeded`: All implemented generation stages for the batch completed successfully.
- `failed`: The batch failed and the generation run must be treated as failed.

Validation and student dataset release/export are post-generation workflow steps.
They should not appear as monthly batch states. The database schema should not
include `validating`, `exporting`, `completed`, or `superseded` as Version 1
monthly batch states.

## Generation Run States

Generation runs should use explicit lifecycle states.

Recommended states:

```text
not_started
running
succeeded
failed
```

Definitions:

- `not_started`: The generation run record or plan exists, but no generation work has started.
- `running`: Generation is actively executing.
- `succeeded`: Generation completed successfully and the current database contents are usable for validation and export.
- `failed`: Generation failed and the current database contents should be treated as incomplete or unreliable.

The database is intentionally designed to hold one generation's domain data at a
time. The control panel should therefore treat generation runs as lifecycle
records for the current database population, not as a selectable catalog of
historical scenarios.

Only the current generation run with `status = succeeded` should be eligible as
the source for student dataset release generation. The control panel should not
offer historical generation runs as export sources unless their associated
generated domain data still exists in the database.

Failed runs are not resumable in Version 1. A failed run leaves generated data
in an incomplete or unreliable state. Retrying generation requires a new full
destructive run from the beginning.

The ORM and database schema will be updated during the build process so the
`generation_runs.status` constraint supports exactly:

```text
not_started
running
succeeded
failed
```

## Progress Reporting

The UI needs real progress for long-running jobs, not just a spinner or stage
boundary updates.

Show both batch-level progress and one progress bar for each visible stage:

```text
Job: generation_run
Status: running
Current batch: 2024-04-01
Stages:
  players             succeeded  100%
  club_memberships    succeeded  100%
  teams               succeeded  100%
  matches             running     62.5%  18,400 / 34,900 matches
  ratings             not_started 0%
```

For the first version, progress must be persisted at stage level:

- Each stage has a status.
- Each stage has a progress bar.
- Each stage records `progress_current`.
- Each stage records `progress_total` when known.
- Each stage records `progress_unit`.
- Each running stage records `last_heartbeat_at`.
- Each running stage records a short progress message.
- Completed stages retain final counts and summary metadata.

Expected progress units include:

- Players generated.
- Club memberships created.
- Teams formed.
- Matches generated.
- Rating updates written.
- Files exported during student dataset release generation.

The implementation does not need perfect estimates for every stage. When a total
is known, the UI should render a determinate progress bar. When a total is not
known, the UI should render an indeterminate progress bar with current count,
unit, and heartbeat age.

The ORM and database schema will be updated during the build process to support
stage-level progress snapshots in the dedicated `job_stage_progress` table. The
key requirement is that the progress state is durable and pollable while the
worker is still running.

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
POST /control/generation/preview
POST /control/jobs/start-generation
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
- Require explicit confirmation before starting a destructive generation run.
- Disable start buttons when prerequisite checks fail.
- Show the selected database URL, database alias, or environment label in the header.
- Prevent launching two write-heavy jobs concurrently unless the job types are proven safe to run in parallel.
- Freeze configuration payloads into generation runs.
- Preserve immutable configuration versions.
- Make clear that generation deletes/rebuilds generated data but does not delete seed/reference data.
- Require additional confirmation for production writes.
- Display a summary of expected affected rows when available.

## Concurrency Policy

The initial implementation should be conservative.

Recommended rules:

- Only one generation job may run at a time.
- Seed ingest and seed normalization may not run while a generation job is active.
- A new generation run may start only when no generation run is `running`.
- Read-only status refreshes may run concurrently.
- Validation jobs may run concurrently only if they do not mutate shared state.
- Production write actions should be serialized.

If concurrency rules are violated, the UI should disable the action and explain which running job is blocking it.

## Idempotency And Rerun Strategy

The Version 1 rerun strategy should be intentionally simple.

- Generation runs always start from the beginning.
- Starting a generation run is destructive to generated data.
- Generation runs do not delete seed/reference data or saved configuration versions.
- No mid-run start, selected-batch start, or partial resume is allowed.
- Failed generation runs cannot resume from the failed stage or month.
- Retrying after failure requires creating a new generation run and performing a new destructive full run.

This avoids turning the first control panel into a complex orchestration tool.
Stage-level rerun, selective replacement, and partial recovery controls belong
in the future enhancement backlog.

Seed ingest and seed normalization are separate workflows. They may have their
own replacement confirmations, but they are not part of the destructive
generation reset.

Seed dataset version lineage and historical seed replay are future
enhancements. They should not be included in the Version 1 rerun model.

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
      seed_config_tab.html
      player_match_config_tab.html
      orchestration_tab.html
      job_status.html
      generation_runs.html
      monthly_batches.html
      student_dataset_release_panel.html
      student_dataset_validation.html
      raw_seed_runs.html
      validation_summary.html
  static/
    control.css
```

### Job Execution

For local development, an in-process FastAPI background execution model is
acceptable for the first version. This may use `BackgroundTasks` or a small
application-owned thread pool.

If jobs need cancellation, restart durability, or multiple workers, move to a
real queue later. The design should avoid assuming that request handlers own
the job lifecycle.

### Frontend

Use restrained operational styling:

- Dense but readable tables.
- Clear status chips.
- Compact form groups.
- Sticky job status area.
- Tabs for the three major workflows.
- No landing page.
- No decorative cards inside cards.
- No SPA framework for the first implementation.

The first screen should be the control panel itself.

## Suggested Build Order

1. Add FastAPI app shell and `/control` route.
2. Render one-page layout with three tabs.
3. Add environment header and persistent status strip.
4. Add read-only status panels for configuration, generation runs, monthly batches, raw load runs, and jobs.
5. Add job-status polling partial.
6. Add configuration viewer.
7. Add configuration validation and save-new-version flow with the temporary JSON editor.
8. Add backend metadata scaffolding for the future generated editor.
9. Add schema-driven generated configuration form renderer.
10. Add configuration diff summary.
11. Add raw ingest and normalize job launch actions.
12. Add full generation preview action.
13. Add full destructive generation launch action.
14. Add persisted per-stage progress updates and progress bars.
15. Add student dataset release generation as the final workload stage.
16. Add structured job metadata.
17. Add structured job logs.
18. Add cancellation and log detail views.

## Open Design Questions

- Should configuration editing use generated forms from a schema, or manually maintained grouped forms?
  - Answer: Configuration editing should use schema-driven generated forms. The backend configuration models should remain the source of truth for field definitions, validation metadata, defaults, ranges, and descriptions. The web layer should render those fields inside manually curated groups organized around major simulation domains.
- Should `job_status` gain structured JSON metadata for stage counts and result summaries?
  - Answer: Yes. This is important to clearly articulate status and avoid overloading simple text fields.
- Should long-running jobs be cancellable in the first version?
  - Answer: No. Do not add cancellation states to the Version 1 job lifecycle. Place cancellation controls and cancellation-specific states in the future enhancement backlog.
- Should the web layer support multiple named environments, or only the local development database?
  - Answer: The web layer should support development and production environments. These should be two databases with the exact same schema design. The active environment must be displayed clearly, and production write actions should require stronger confirmation.
- Should validation/export be visible as disabled stages immediately, or hidden until implemented?
  - Answer: Show validation and student dataset release as disabled/planned post-generation workflow steps if useful. They are not Version 1 generation completion criteria and should be visually distinct from incomplete implemented stages.
- Should React be introduced later if the UI grows?
  - Answer: Not by default. The preferred long-term posture is still server-rendered HTML with HTMX unless the control panel develops requirements that clearly justify a SPA framework.

## Future Enhancement Backlog

### Student Dataset Release Enhancements

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
- Seed dataset version lineage.
- Historical seed snapshot replay.
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

Build the first version as a single-page HTMX control panel with server-rendered partials and background jobs. Keep it intentionally operational: seed-data configuration on one tab, player-and-match configuration on a second tab, workload orchestration on a third, with a persistent job status strip that always tells the operator what is running and what happened last.

The most important architectural boundary is that the web layer should remain a control plane. It should expose, validate, launch, and observe backend workflows. It should not become the owner of simulation, generation, rating, or pipeline business logic.
