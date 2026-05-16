# Architecture.md — AI-Integrated Data Generation Platform with Local Web Control Panel

Prepared: 2026-05-07

---

# 1. Purpose of This Document

This document defines the architecture, repository structure, database strategy, AI-assisted development workflow, data generation standards, local web control panel design, batch processing workflow, and implementation conventions for this application.

This application is not a public API-first SaaS application. It is a local data generation and simulation platform with a lightweight browser-based control interface.

The application is primarily a:

- synthetic data generation platform
- analytics simulation platform
- structured database population system
- local batch-processing control application
- monthly data increment processor
- Parquet export generation tool
- AI-assisted development environment

This document should be referenced regularly by Claude, Codex/OpenAI, Continue, Cursor, and GitHub Copilot.

---

# 2. Application Vision

The application is a modern, AI-assisted, containerized data generation platform designed to create large-scale synthetic datasets for analytics, experimentation, demonstrations, machine learning training, and educational purposes.

The application includes a lightweight local web control panel that allows the user to:

- configure dataset sizes using sliders and form controls
- estimate storage requirements before generation
- load seed or reference datasets through file pickers
- generate historical datasets
- process monthly data increments
- generate Parquet exports
- monitor generation status and progress
- review validation results
- inspect batch history and generated outputs

The application should emphasize reproducibility, maintainability, scalability, local workflow control, AI-assisted development, Docker-based execution, PostgreSQL persistence, and analytics-ready exports.

---

# 3. Primary Functional Goals

The application should support:

- generation of realistic synthetic entities
- historical time-series simulation
- configurable randomness and weighting
- relational consistency between generated records
- large-scale dataset generation
- analytics-ready schemas
- repeatable seeded generation runs
- configurable export pipelines
- monthly batch processing
- local web-based generation control
- front-end estimation of storage requirements
- file-based data loading
- future simulation engines
- future ML-oriented synthetic datasets

Examples of generated data may include users, players, teams, matches, transactions, events, rankings, statistics, telemetry, sensor data, healthcare-style observations, sports match histories, subscription activity, and behavioral analytics.

---

# 4. Recommended Technology Stack

## 4.1 Development Environment

| Layer | Recommended Tool | Purpose |
|---|---|---|
| IDE | Visual Studio Code | Primary development interface |
| AI Integration | Continue | Repository-aware AI integration |
| Architecture AI | Claude | Architecture, schema reasoning, simulation logic |
| Implementation AI | Codex/OpenAI | Scaffolding and implementation |
| Optional AI IDE | Cursor | Multi-file AI acceleration |
| Runtime | Docker Desktop | Local container runtime |
| Dev Environment | Dev Containers | Reproducible development |
| Source Control | Git + GitHub | Collaboration and version control |

## 4.2 Application Stack

| Layer | Recommended Tool | Purpose |
|---|---|---|
| Web Server | FastAPI | Local web server and workflow controller |
| UI Rendering | Jinja2 Templates | Server-rendered HTML |
| Dynamic UI | HTMX | Lightweight server-driven UI updates |
| Front-End Logic | Vanilla JavaScript | Sliders, estimates, client-side calculations |
| Progress Updates | Server-Sent Events or HTMX polling | Long-running job status |
| Backend Runtime | Python | Primary runtime |
| Database | PostgreSQL | Relational persistence |
| ORM | SQLAlchemy | Database queries and data access |
| Data Generation | Faker + custom generators | Synthetic data creation |
| Data Processing | Pandas | Data manipulation |
| Parquet Export | PyArrow or fastparquet | Parquet file generation |
| Validation | Pydantic | Structured validation and settings |
| Testing | Pytest | Testing framework |
| DB Inspection | DBeaver | Database inspection |
| Runtime Orchestration | Docker Compose | Multi-container runtime |

---

# 5. Architectural Principles

## 5.1 Local Control Panel, Not Public API Platform

The web server exists primarily to provide a local browser-based control panel for generation workflows. It should support forms, sliders, buttons, file uploads, generation status, batch history, export controls, and validation reports.

It should not be designed as a public API-first application unless that becomes a future requirement.

## 5.2 Separation of Responsibilities

The application should separate web control logic, generation logic, simulation logic, persistence logic, batch-processing logic, export logic, analytics logic, configuration logic, and infrastructure logic.

The web layer should trigger workflows but should not contain generation algorithms.

## 5.3 Incremental Generation

Data generation should happen incrementally and predictably. Avoid massive monolithic generators, giant one-shot generation scripts, and uncontrolled cross-module coupling.

Prefer modular generators, reusable generation utilities, composable generation pipelines, deterministic generation phases, and explicit generation run tracking.

## 5.4 AI-Assisted but Human-Governed

AI tools may generate schemas, generators, simulations, database models, web control pages, HTMX snippets, JavaScript estimators, tests, and utilities. However, humans define architecture, validate outputs, review logic, and approve designs.

## 5.5 Reproducibility

Generation runs should be reproducible using seeded randomness, deterministic generation modes, reproducible exports, configuration-driven generation, generation run metadata, and explicit batch history.

---

# 6. Repository Structure

Recommended structure:

```text
project-root/
├── .devcontainer/
├── backend/
│   ├── app/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── repositories/
│   │   ├── services/
│   │   ├── generators/
│   │   ├── simulations/
│   │   ├── batch_processing/
│   │   ├── analytics/
│   │   ├── exports/
│   │   ├── validation/
│   │   ├── web/
│   │   │   ├── routes/
│   │   │   ├── templates/
│   │   │   ├── static/
│   │   │   │   ├── css/
│   │   │   │   └── js/
│   │   │   └── forms.py
│   │   ├── utils/
│   │   └── main.py
│   ├── schema.sql
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── data/
│   ├── input/
│   ├── output/
│   ├── parquet/
│   └── uploads/
├── docs/
│   ├── architecture.md
│   ├── database.md
│   ├── generation-strategy.md
│   ├── ui-control-panel.md
│   ├── ai-development.md
│   └── setup.md
├── scripts/
├── docker-compose.yml
├── .env.example
└── README.md
```

---

# 7. Web Control Panel Architecture

## 7.1 Purpose

The web control panel is a local browser-based interface for controlling data generation and batch processing.

It should allow users to configure synthetic dataset sizes, set generation seeds, choose scenario parameters, estimate storage requirements, load input files, start generation jobs, process monthly data increments, generate Parquet files, view job progress, inspect run history, and download or locate generated outputs.

## 7.2 Recommended Web Stack

Use:

```text
FastAPI
Jinja2
HTMX
Vanilla JavaScript
Server-Sent Events or HTMX polling
```

Do not use React unless future requirements justify a full single-page application. The current application needs a smart local control panel, not a complex front-end framework.

## 7.3 Web Folder Structure

```text
backend/app/web/
├── routes/
│   ├── dashboard_routes.py
│   ├── generation_routes.py
│   ├── batch_routes.py
│   ├── export_routes.py
│   └── upload_routes.py
├── templates/
│   ├── base.html
│   ├── dashboard.html
│   ├── generation.html
│   ├── batches.html
│   ├── exports.html
│   └── partials/
│       ├── job_status.html
│       ├── storage_estimate.html
│       └── validation_summary.html
├── static/
│   ├── css/
│   │   └── app.css
│   └── js/
│       ├── storage_estimator.js
│       ├── sliders.js
│       └── progress.js
└── forms.py
```

## 7.4 UI Pages

| Page | Purpose |
|---|---|
| Dashboard | Overview of runs, status, outputs, and controls |
| Generation | Configure dataset sizes and generation parameters |
| Monthly Batches | Process new monthly increments |
| File Loading | Upload or select seed/reference datasets |
| Exports | Generate and review Parquet/CSV outputs |
| Validation | Review data quality checks |
| Settings | Configure default generation parameters |

---

# 8. Front-End Interaction Design

## 8.1 Sliders for Dataset Sizes

Use HTML range inputs for dataset sizing.

Example parameters:

- number of players
- number of regions
- months of historical data
- matches per month
- transactions per customer
- data quality issue level
- missingness percentage
- duplicate rate
- anomaly rate

The slider UI should display both the current selected value and the estimated storage impact.

## 8.2 Front-End Storage Estimation

Use vanilla JavaScript for immediate client-side estimates.

The browser should estimate:

- approximate row counts
- approximate database storage
- approximate Parquet output size
- estimated generation time
- relative workload level

These estimates do not need to be perfect. They should help the user avoid unintentionally generating datasets that are too large for the local machine.

The backend must still validate final requested sizes before execution.

## 8.3 File Picker and Dataset Loading

Use standard HTML file inputs for loading input datasets.

Supported input types may include:

- CSV
- JSON
- Parquet
- XML
- ZIP archives

Uploaded files should be stored under:

```text
data/uploads/
```

The system should record metadata about uploaded files, including filename, file type, size, upload timestamp, source purpose, and validation status.

## 8.4 Buttons for Long-Running Workflows

The UI should provide explicit buttons for major workflows:

- Generate Historical Dataset
- Process Next Monthly Batch
- Process Selected Month
- Generate Parquet Files
- Validate Generated Dataset
- Export Summary Report
- Reset Local Generated Data
- Rebuild Derived Analytics

Buttons should trigger backend jobs through FastAPI routes using HTMX or standard form posts.

## 8.5 Progress and Status Updates

Long-running jobs should show progress using HTMX polling, Server-Sent Events, or a basic page refresh fallback.

Status display should include job id, job type, current phase, percent complete if available, current message, started at, completed at, and error message if failed.

---

# 9. Database Architecture

## 9.1 Database Platform

PostgreSQL is the primary database platform.

The database supports generated entity persistence, historical simulations, monthly batch tracking, analytics experimentation, uploaded file metadata, export metadata, generation run history, and downstream analytics.

## 9.2 ORM Strategy

SQLAlchemy is the primary ORM layer. SQLAlchemy provides model definitions, relationships, query abstraction, transaction management, and schema consistency.

## 9.3 Schema Management Strategy

Database schema is managed through **SQLAlchemy ORM metadata** during active
development.

The complete executable schema is defined by the ORM models in
`backend/app/models`.

Schema creation workflow:

```bash
# Recreate a local development database from ORM metadata
python backend/scripts/recreate_db_from_orm.py
```

Rules:

- Single source of truth: SQLAlchemy ORM models
- Schema creation via controlled ORM metadata scripts
- `backend/schema.sql` is a generated/reference artifact
- Generated SQL should match ORM metadata, not diverge from it
- For development: Drop and recreate database as needed
- For students: Reproducible one-command schema setup

## 9.4 Core Operational Tables

In addition to generated domain tables, include operational metadata tables such as:

```text
generation_runs
generation_parameters
batch_runs
uploaded_files
export_runs
validation_results
job_status
```

These tables help the system track reproducibility, execution history, and generated outputs.

## 9.5 Naming Conventions

| Object | Convention |
|---|---|
| Tables | plural_snake_case |
| Columns | snake_case |
| Primary Keys | id |
| Foreign Keys | entity_id |
| Timestamps | created_at, updated_at |

## 9.6 Standard Columns

Most generated domain tables should include:

```text
id
created_at
updated_at
generation_run_id
```

Operational tables should include:

```text
id
created_at
updated_at
status
started_at
completed_at
error_message
```

Optional generation metadata:

```text
source_system
seed_value
scenario_name
simulation_version
batch_month
```

---

# 10. Generation Architecture

## 10.1 Generation Layer

Generators should live in:

```text
backend/app/generators/
```

Generators are responsible for creating synthetic entities, applying randomization, generating realistic values, maintaining relational consistency, creating temporal patterns, and enforcing generation constraints.

Example generators:

```text
player_generator.py
region_generator.py
match_generator.py
event_generator.py
ranking_generator.py
telemetry_generator.py
```

## 10.2 Simulation Layer

Simulations should live in:

```text
backend/app/simulations/
```

Simulations are responsible for historical progression, time-series evolution, weighted outcomes, scenario execution, behavior evolution, analytics scenario generation, and monthly increments.

Example simulations:

```text
season_simulation.py
monthly_batch_simulation.py
ranking_progression_simulation.py
stress_event_simulation.py
subscription_decay_simulation.py
```

## 10.3 Batch Processing Layer

Monthly batch processing should live in:

```text
backend/app/batch_processing/
```

Batch processors are responsible for identifying the next month to process, applying generation parameters, creating incremental records, preserving continuity with prior data, recording batch metadata, validating batch outputs, and triggering exports if configured.

Example modules:

```text
monthly_batch_processor.py
batch_scheduler.py
batch_validator.py
batch_metadata_service.py
```

## 10.4 Analytics Layer

Analytics utilities should live in:

```text
backend/app/analytics/
```

Analytics modules may derive metrics, create aggregates, calculate rankings, generate snapshots, build derived features, and validate generated data quality.

---

# 11. Export Architecture

Export logic should live in:

```text
backend/app/exports/
```

Supported export formats may include CSV, JSON, Parquet, and SQL dumps. Parquet export is a primary requirement.

Parquet exports should support deterministic naming, timestamping, scenario tagging, batch month tagging, generation metadata, reproducibility, and partitioning where appropriate.

Recommended Parquet output structure:

```text
data/parquet/
├── historical/
├── monthly/
├── analytics/
└── metadata/
```

Example naming:

```text
players_generation_run_001.parquet
matches_2026_01_batch_003.parquet
ranking_history_generation_run_001.parquet
```

---

# 12. Generation Workflow

Recommended full historical generation workflow:

1. User opens local web control panel.
2. User sets parameters using sliders and forms.
3. Front-end estimates storage requirements.
4. Backend validates requested parameters.
5. System creates generation run record.
6. System seeds randomness.
7. System generates core entities.
8. System generates relationships.
9. System generates historical activity.
10. System runs simulations.
11. System derives analytics.
12. System validates data quality.
13. System exports datasets if requested.
14. System records metadata and status.

Recommended monthly batch workflow:

1. User selects Process Next Monthly Batch.
2. System determines next unprocessed month.
3. System loads prior state.
4. System applies monthly generation rules.
5. System creates incremental records.
6. System updates derived metrics.
7. System validates batch results.
8. System generates monthly Parquet exports.
9. System records batch status and metadata.

---

# 13. Job Execution and Status Tracking

Long-running workflows should be represented as jobs.

Job types may include:

```text
historical_generation
monthly_batch
parquet_export
validation
analytics_rebuild
file_import
```

Job states:

```text
pending
running
completed
failed
cancelled
```

The UI should read status from a durable status source, preferably the database.

A simple first implementation may run jobs synchronously or through background tasks. If workloads grow, move job execution to a worker pattern.

Future options:

- FastAPI BackgroundTasks
- Python multiprocessing
- Celery
- RQ
- APScheduler
- custom worker process

---

# 14. File Loading Architecture

The application should support user-selected input datasets.

File upload workflow:

1. User selects a file in the browser.
2. FastAPI receives the upload.
3. File is stored in `data/uploads/`.
4. Metadata is written to `uploaded_files`.
5. File is validated.
6. User receives validation feedback.
7. File becomes available to generation workflows.

Validation should check file type, file size, expected columns, parseability, row count, schema compatibility, and encoding issues.

---

# 15. Configuration and Parameter Management

Generation parameters should be represented explicitly.

Parameters may include:

- entity counts
- date ranges
- region counts
- match counts
- seed values
- competitiveness multipliers
- data quality level
- missingness rates
- anomaly rates
- export formats
- monthly batch options

Store submitted parameters in:

```text
generation_parameters
```

This supports reproducibility and later review.

---

# 16. AI-Assisted Development Standards

## 16.1 AI Tool Roles

| Tool | Recommended Role |
|---|---|
| Claude | Architecture, database design, simulation reasoning |
| Codex/OpenAI | Scaffolding, repetitive implementation |
| Continue | Repository-aware IDE integration |
| Cursor | Optional rapid refactoring |
| Copilot | Inline suggestions |

## 16.2 Context Engineering

Maintain these files carefully:

```text
docs/architecture.md
docs/database.md
docs/generation-strategy.md
docs/ui-control-panel.md
README.md
.env.example
```

These become persistent AI context.

## 16.3 AI Prompting Standards

Good prompt example:

```text
Using docs/architecture.md, implement the generation control panel.

Requirements:
- FastAPI route for the generation page
- Jinja2 template with sliders
- vanilla JavaScript storage estimator
- HTMX button to start generation
- job_status partial for progress display
- backend validation of submitted parameters
- pytest coverage for parameter validation
```

Another good prompt:

```text
Using docs/architecture.md, implement monthly batch processing.

Requirements:
- batch_runs operational table
- monthly_batch_processor service
- continuity with prior generated data
- Parquet export after batch completion
- status tracking
- validation summary
```

## 16.4 AI Output Review Checklist

Before accepting AI-generated code:

- Does it follow repository structure?
- Is web logic separated from generation logic?
- Is generation logic modular?
- Are relationships valid?
- Is randomness reproducible?
- Are timestamps consistent?
- Are UI controls validated server-side?
- Are long-running jobs tracked?
- Are tests included?
- Does it scale?
- Does it avoid duplicated logic?

---

# 17. Testing Strategy

Use:

```text
pytest
```

Testing should validate relational integrity, generation consistency, simulation accuracy, monthly batch continuity, export correctness, deterministic seed behavior, schema correctness, upload validation, storage estimate logic, and parameter validation.

Recommended structure:

```text
tests/
├── unit/
├── integration/
├── generators/
├── simulations/
├── batch_processing/
├── exports/
├── web/
└── analytics/
```

---

# 18. Logging and Observability

Use structured logging.

Log generation runs, submitted parameters, simulation execution, monthly batch processing, upload validation, export completion, validation failures, database failures, and performance metrics.

Avoid print statements, silent failures, and swallowed exceptions.

---

# 19. Docker Architecture

Recommended services:

```text
backend
postgres
```

Optional future services:

```text
redis
worker
scheduler
analytics-engine
```

The environment should work entirely locally without required cloud dependencies.

The local web control panel should be available at a predictable local address such as:

```text
http://localhost:8000
```

---

# 20. Security Standards

Security requirements include:

- never commit secrets
- validate all form inputs
- validate all uploaded files
- review AI-generated code
- avoid unsafe SQL
- externalize configuration
- maintain dependency hygiene
- avoid exposing the local app unnecessarily beyond localhost

Because this is a local control application, authentication may not be required initially. If remote access is introduced later, authentication and authorization must be added before exposure.

---

# 21. Development Workflow

Recommended workflow:

1. Update architecture docs if needed.
2. Define generation entities.
3. Define relationships.
4. Define UI controls.
5. Define simulations.
6. Generate models.
7. Generate migrations.
8. Implement generators.
9. Implement control panel interactions.
10. Add tests.
11. Validate generated data.
12. Export Parquet files.
13. Commit changes.

---

# 22. Initial Build Priorities

Initial scaffold should include:

```text
backend/app/models/
backend/app/generators/
backend/app/simulations/
backend/app/batch_processing/
backend/app/analytics/
backend/app/exports/
backend/app/web/
backend/app/db/
backend/schema.sql
backend/tests/
docker-compose.yml
Dockerfile
.devcontainer/
.env.example
```

Initial functional goals:

- successful local container startup
- FastAPI local web control panel
- slider-based generation parameter form
- front-end storage estimate
- database connectivity
- first generated dataset
- first monthly batch workflow stub
- first Parquet export pipeline

---

# 23. Future Expansion Areas

The architecture should support future additions such as ML-generated synthetic data, vector databases, AI agents, streaming simulations, large-scale distributed generation, richer dashboard visualization, scenario editors, workload schedulers, cloud execution, synthetic healthcare datasets, synthetic sports analytics platforms, background worker execution, and real-time progress streaming.

---

# 24. Anti-Patterns to Avoid

Avoid:

- giant monolithic generators
- duplicated generation logic
- putting generation algorithms inside web routes
- direct DB logic scattered everywhere
- manual schema changes
- inconsistent randomness
- undocumented simulations
- accepting AI output without validation
- giant AI prompts generating entire systems
- building a React SPA when simple server-rendered pages are sufficient
- trusting front-end estimates without backend validation

---

# 25. Definition of Done

A feature is complete only when:

- architecture standards are followed
- tests exist
- migrations exist if needed
- generation logic is modular
- web routes are thin
- UI controls validate server-side
- outputs validate successfully
- Docker environment works
- documentation is updated
- AI-generated code has been reviewed

---

# 26. Final Guidance

This application is intended to be AI-assisted, architecture-driven, modular, reproducible, web-controlled locally, analytics-oriented, scalable, educational, and extensible.

The local web interface is a control panel for generation, simulation, batch processing, and exports. The core complexity belongs in the data generation engine, simulation logic, database schema, validation layer, and export workflows — not in a heavy front-end framework.
