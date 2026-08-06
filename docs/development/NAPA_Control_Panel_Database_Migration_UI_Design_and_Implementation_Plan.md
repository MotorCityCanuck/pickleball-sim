# NAPA Control Panel Database Migration UI Design and Implementation Plan

**Project:** DSB6000 NAPA Pickleball Simulation  
**Document Type:** Technical Design Specification and Codex Implementation Plan  
**Feature:** Control Panel Database Backup / Migration Support  
**Status:** Proposed Design  
**Primary Audience:** Instructor / Codex implementation workflow

---

## 1. Purpose

This document defines the design for adding a **Database Migration** capability to the NAPA instructor control panel.

The feature is intended to support one operational requirement:

> Move the exact certified PostgreSQL database from the primary development machine to the classroom demonstration laptop and restore it safely for tournament execution.

The design intentionally avoids introducing general-purpose database switching, multiple active application databases, or changes to ORM behavior.

The classroom environment should continue to use the **same PostgreSQL database name and application configuration** already expected by the NAPA application.

The migration process must preserve the existing classroom database before replacement so that the prior test environment can be recovered if needed.

---

## 2. Design Principles

### 2.1 Minimal Application Impact

The migration feature must not require:

- application-wide database-name parameterization;
- ORM model changes;
- runtime database switching;
- multiple database selectors;
- changes to normal generator logic;
- changes to tournament simulation logic.

The restored production database should use the same database name already configured for the application.

```text
Development Machine
    PostgreSQL
        └── configured NAPA database
                    │
                    │ migration backup
                    ▼
Classroom Laptop
    PostgreSQL
        └── same configured NAPA database name
```

The application should not need to know that the database contents were migrated.

### 2.2 PostgreSQL-Native Migration

The supported migration method must use PostgreSQL-native logical backup and restore tooling:

```text
pg_dump
pg_restore
pg_dumpall --globals-only
```

The Docker volume itself is not the primary migration artifact.

### 2.3 Existing Classroom Database Must Be Protected

If a database already exists on the classroom laptop, the restore process must automatically create and verify a backup of that database before replacement.

The incoming production database must never overwrite the existing classroom database without a verified rollback copy.

### 2.4 Restore Must Be Fail-Safe

The destructive portion of the restore must begin only after:

1. the incoming migration package is verified; and
2. the current classroom database has been successfully backed up and verified.

Failure of either condition must abort the restore.

### 2.5 UI Must Not Duplicate Migration Logic

The control panel must provide an instructor-friendly interface over backend migration services/scripts.

Backup, verification, and restore logic should remain independently executable from the command line.

This ensures migration remains possible even if the control panel cannot start.

---

## 3. Scope

The Database Migration feature will support:

- creation of a migration backup;
- backup verification;
- display of backup metadata;
- selection of an existing migration package;
- pre-restore protection of the current classroom database;
- controlled replacement of the existing database;
- restore validation;
- status reporting;
- migration history where practical.

The feature is instructor-only operational functionality.

---

## 4. Non-Goals

This feature is not intended to provide:

- general PostgreSQL administration;
- arbitrary database creation;
- runtime database switching;
- database browsing;
- table editing;
- backup deletion;
- database deletion;
- schema migration management;
- PostgreSQL version upgrades;
- cloud backup services;
- student-facing functionality.

---

## 5. User Experience Overview

Add a new control panel tab:

```text
Database Migration
```

Alternative acceptable label:

```text
Backup & Migration
```

The preferred label is **Database Migration** because the purpose is operational movement of the instructor database rather than general backup administration.

---

## 6. Control Panel Layout

The tab should contain four primary areas.

```text
Database Migration
│
├── Current Database
├── Create Migration Backup
├── Restore Migration Backup
└── Migration / Validation Status
```

A history panel may be included if it can be implemented cleanly without adding unnecessary persistence complexity.

---

## 7. Current Database Panel

The first section must show the identity and state of the database currently used by the application.

Recommended fields:

```text
Database Name
PostgreSQL Version
Docker Container
Database Size
Application Git Commit
Application Git Branch / Tag
Certification Status
Last Certification Timestamp
Connection Status
```

Example:

```text
Current Database

Database:             pickleball
PostgreSQL:           16.x
Container:            pickleball-postgres
Database Size:        18.4 GB
Git Commit:           4f91ae8
Certification:        PASS
Certification Date:   2026-10-10 09:42
Connection:           HEALTHY
```

The panel should clearly identify whether the control panel can reach PostgreSQL.

---

## 8. Create Migration Backup

### 8.1 Purpose

Provide an instructor-facing operation that creates a complete migration package from the currently configured database.

Primary action:

```text
[ Create Migration Backup ]
```

The UI must display the database that will be backed up.

The instructor should not select an arbitrary database.

Example:

```text
Source Database: pickleball
Destination:     /path/to/backups
Label:           NAPA_250K_Final
```

The optional label may be used to make migration packages easier to identify.

### 8.2 Required Backup Package

The backend must create a directory such as:

```text
backups/
  napa_250k_final_2026-10-10_101500/
      database.dump
      postgres_globals.sql
      manifest.txt
      row_counts.csv
      SHA256SUMS
      FREEZE_MANIFEST.md
```

Where release freeze metadata is unavailable, the backup should still be created, but unavailable values must be explicitly shown as `UNKNOWN`.

### 8.3 Backup Execution Flow

```text
User selects Create Migration Backup
                ↓
Validate database connection
                ↓
Capture database metadata
                ↓
Capture source row counts
                ↓
Run pg_dump
                ↓
Capture PostgreSQL globals
                ↓
Generate manifest
                ↓
Generate SHA-256 checksums
                ↓
Run pg_restore --list verification
                ↓
Report VERIFIED
```

The UI must not report success until verification is complete.

---

## 9. Backup Status Display

During execution, the UI should display stage progress.

Example:

```text
Creating migration backup...

[PASS] Database connection
[PASS] Source metadata captured
[PASS] Row counts captured
[PASS] PostgreSQL archive created
[PASS] Globals captured
[PASS] Checksums generated
[PASS] Archive verified

Migration backup ready.
```

On failure:

```text
Migration backup FAILED.

Failed step:
PostgreSQL archive creation

No migration package has been marked valid.
```

---

## 10. Restore Migration Backup

### 10.1 Purpose

Allow the instructor to restore a verified migration package to the classroom machine.

The design must assume that the classroom laptop may already contain an earlier NAPA database used for:

- tournament simulator testing;
- application testing;
- development verification;
- classroom dry runs.

That database must be preserved automatically before replacement.

### 10.2 Same-Name Restore Model

The incoming backup must normally restore to the same database name recorded in the backup manifest.

Example:

```text
Backup Database Name: pickleball
Current Database Name: pickleball
Restore Target:        pickleball
```

The UI should not present a general-purpose target database selector.

If the incoming manifest database name does not match the configured database name, the restore must stop and explain the mismatch.

An explicit advanced override may be implemented later if a real requirement emerges.

---

## 11. Restore Package Selection

The UI should allow the instructor to identify a migration package directory.

Preferred behavior depends on the existing UI framework and browser limitations.

Acceptable implementations include:

- selecting a backup package already stored in the configured backup directory;
- entering/pasting a server-side backup path;
- selecting from a list of discovered migration packages.

The application should not require uploading a multi-gigabyte PostgreSQL dump through the browser.

The preferred design is:

```text
Configured Backup Directory
        ↓
Backend discovers valid backup packages
        ↓
UI displays package list
```

Example:

```text
Available Migration Packages

NAPA_250K_Final_2026-10-10_101500
  Database: pickleball
  PostgreSQL: 16.x
  Size: 12.7 GB
  Certification: PASS
  Checksum: VERIFIED
```

---

## 12. Pre-Restore Validation

Before enabling the restore action, the system must verify the incoming package.

Required checks:

```text
database.dump exists
postgres_globals.sql exists
manifest.txt exists
row_counts.csv exists
SHA256SUMS exists
checksums pass
pg_restore --list succeeds
database name matches configured database
PostgreSQL major version is compatible
```

Only after those checks succeed should the UI enable:

```text
[ Restore Database ]
```

---

## 13. Mandatory Existing-Database Safety Backup

Before replacing the classroom database, the restore process must create a backup of the currently installed database.

Example output:

```text
backups/
  pre_restore/
    pickleball_before_restore_2026-10-15_083000/
        database.dump
        postgres_globals.sql
        manifest.txt
        row_counts.csv
        SHA256SUMS
```

This backup must itself be verified.

Required sequence:

```text
Verify incoming production backup
                ↓
Backup current classroom database
                ↓
Verify classroom safety backup
                ↓
ONLY THEN allow destructive restore
```

If the safety backup cannot be created or verified:

```text
RESTORE ABORTED
```

The existing classroom database must remain untouched.

---

## 14. Application Shutdown Requirement

The NAPA application and database-writing services must not remain active while the database is replaced.

Relevant processes may include:

- FastAPI control panel;
- background worker;
- generator jobs;
- realism audit jobs;
- export jobs;
- tournament simulation jobs.

The implementation must ensure no database-writing job is active before destructive replacement.

---

## 15. Important Control Panel Self-Restore Constraint

The control panel itself uses PostgreSQL.

Therefore, replacing the database from the running control panel requires special handling.

The implementation must **not** simply execute `DROP DATABASE` from a normal request handler while leaving the application running against that database.

Two implementation approaches are acceptable.

### Preferred Approach — Detached Restore Orchestrator

The control panel initiates a detached restore process that can continue after the web application exits.

```text
Control Panel
    ↓
Validate incoming package
    ↓
Request restore
    ↓
Launch detached migration orchestrator
    ↓
Return "migration beginning" response
    ↓
Control panel shuts down
    ↓
Migration orchestrator performs restore
    ↓
Migration orchestrator restarts application
```

The migration orchestrator must not depend on the application ORM connection.

This is the preferred implementation if restore is exposed directly in the UI.

### Alternative Approach — UI Assisted / CLI Executed Restore

If detached orchestration is judged unnecessarily complex or unreliable, the first implementation may use:

```text
Control panel
    ├── create backup
    ├── verify migration package
    ├── display restore command
    └── validate restored database

CLI script
    └── performs actual destructive restore
```

This remains an acceptable implementation because operational safety is more important than full browser automation.

Codex should assess the existing application startup model before choosing between these approaches.

---

## 16. Restore Confirmation

The destructive restore must require explicit confirmation.

The UI should display a warning similar to:

```text
You are about to replace the current NAPA database.

Current database:
pickleball

Incoming backup:
NAPA_250K_Final_2026-10-10_101500

A verified safety backup of the current database will be created before replacement.

The application will be temporarily unavailable during migration.
```

Recommended confirmation:

```text
[ Cancel ]   [ Backup Current DB and Restore ]
```

Avoid generic labels such as `OK`.

---

## 17. Restore Execution Flow

The complete process should be:

```text
1. Verify incoming backup package
2. Confirm incoming database identity
3. Confirm PostgreSQL compatibility
4. Check that no migration is already running
5. Create safety backup of current classroom database
6. Verify safety backup
7. Stop application/background services
8. Terminate remaining database sessions if required
9. Drop/recreate configured database
10. Restore PostgreSQL globals safely
11. Restore database archive
12. Run PostgreSQL ANALYZE if appropriate
13. Validate required objects
14. Compare row counts against migration package
15. Run application-level database health checks
16. Reuse existing certification/realism validation where appropriate
17. Restart application/background services
18. Report final migration status
```

---

## 18. Failure Handling

### 18.1 Failure Before Database Replacement

If failure occurs before the existing database is dropped:

```text
Abort migration.
Leave existing database unchanged.
```

Examples:

- incoming checksum failure;
- source archive unreadable;
- PostgreSQL version incompatibility;
- safety backup failure.

### 18.2 Failure After Database Replacement

If failure occurs after the existing database has been removed, the system must preserve enough information to perform rollback.

The safety backup path must be recorded before destructive work begins.

The migration status should clearly show:

```text
RESTORE FAILED

Rollback backup:
<path>

Recommended action:
Restore pre-restore safety backup.
```

Automatic rollback may be implemented if Codex determines it can be done reliably.

If automatic rollback is implemented, it must:

1. restore the verified pre-restore backup;
2. validate that rollback;
3. restart the application;
4. report both the migration failure and rollback result.

---

## 19. Migration State File

Because the web application may stop during restore, migration progress cannot exist only in application memory.

The detached process must maintain a durable state file.

Recommended:

```text
runtime/database_migration_status.json
```

Example:

```json
{
  "status": "restoring",
  "operation_id": "20261015_083500",
  "incoming_backup": "...",
  "safety_backup": "...",
  "current_step": "restore_database",
  "started_at": "...",
  "updated_at": "...",
  "error": null
}
```

The control panel should read this file after restart and display the final result.

Do not store credentials in the state file.

---

## 20. Migration Status Panel

After startup, the control panel should display the latest migration result.

Example:

```text
Last Database Migration

Status:             SUCCESS
Completed:          2026-10-15 08:58
Database:           pickleball
Migration Package:  NAPA_250K_Final_2026-10-10_101500
Safety Backup:      pickleball_before_restore_2026-10-15_083000
Checksum:           PASS
Row Counts:         PASS
Application Check:  PASS
```

If failure occurred:

```text
Status:             FAILED
Failed Step:        restore_database
Rollback Available: YES
Safety Backup:      ...
```

---

## 21. Backend Service Design

Migration functionality should be implemented as a separate application service/module rather than embedded in control panel route handlers.

Recommended structure:

```text
src/
  ...
  database_migration/
      backup.py
      verify.py
      restore.py
      validation.py
      models.py
      status.py
```

or reuse the repository's existing application structure if a service pattern already exists.

Route handlers should orchestrate service calls but should not contain PostgreSQL shell-command logic.

---

## 22. Script Layer

The control panel should rely on independently executable scripts or Python command modules.

Recommended scripts:

```text
scripts/
    backup_database.sh
    verify_database_backup.sh
    restore_database.sh
    validate_restored_database.sh
    migrate_classroom_database.sh
```

If the codebase already favors Python CLIs over shell orchestration, equivalent Python entry points are acceptable.

The important requirement is that the migration can be executed without the web UI.

---

## 23. `migrate_classroom_database.sh`

This should provide the one-command classroom migration workflow.

Example:

```bash
./scripts/migrate_classroom_database.sh     /path/to/NAPA_250K_Final_2026-10-10_101500
```

Expected behavior:

```text
Verify incoming backup
Backup existing classroom database
Verify safety backup
Stop application services
Restore database using same database name
Validate restored database
Restart application services
```

This script should be the same underlying orchestration used by the UI detached migration process where practical.

---

## 24. No ORM Changes Required

The design explicitly avoids changing ORM behavior.

The application continues to use its normal configured PostgreSQL database.

Before migration:

```text
Application
    ↓
Configured database: pickleball
    ↓
Classroom test data
```

After migration:

```text
Application
    ↓
Configured database: pickleball
    ↓
Frozen production data
```

The connection configuration and ORM models remain unchanged.

This feature must not introduce dynamic engine switching or session-pool reconfiguration during normal application operation.

---

## 25. Database Identity Controls

The migration package manifest must contain:

```text
database_name
postgres_version
backup_timestamp
git_commit
docker_image
database_size
```

Where available:

```text
release_name
dataset_scale
certification_status
certification_timestamp
```

The restore process must verify that:

```text
backup database name == configured application database name
```

unless a future explicitly supported migration mode says otherwise.

---

## 26. Release Freeze Integration

For the final 250K production database, the Database Migration tab should support or surface a formal freeze workflow.

Recommended action:

```text
[ Create Final Production Migration Backup ]
```

The operation should:

```text
Confirm certification PASS
        ↓
Capture Git commit
        ↓
Create database backup
        ↓
Capture globals
        ↓
Capture row counts
        ↓
Generate manifest
        ↓
Generate checksums
        ↓
Verify archive
        ↓
Mark package VERIFIED
```

The control panel should not mark a final migration package as production-ready if required certification has failed.

---

## 27. Security Requirements

The migration UI is operationally sensitive.

At minimum:

- it should exist only in the instructor control panel;
- credentials must not be displayed;
- credentials must not be stored in manifests;
- shell arguments must not expose passwords;
- user-provided paths must be validated;
- arbitrary shell execution must not be possible;
- package paths must remain within approved migration/backup locations where practical.

If authentication exists in the control panel, migration functions must require the same or higher privilege than other destructive instructor operations.

---

## 28. Concurrency Controls

Only one migration operation may execute at a time.

Use an explicit migration lock.

Possible implementation:

```text
runtime/database_migration.lock
```

If a second operation is attempted:

```text
Database migration already in progress.
```

The system must reject the second request.

---

## 29. Backup Retention

The first implementation should not automatically delete migration packages or safety backups.

Storage management should remain an explicit instructor action.

The UI may display:

```text
Backup Location
Backup Size
Created Date
```

but should not expose `Delete Backup` in the first implementation.

---

## 30. Logging

Migration operations must generate an independent log file.

Recommended:

```text
logs/database_migration_<operation_id>.log
```

Log:

- operation ID;
- start/end time;
- executed stage;
- success/failure status;
- PostgreSQL tool return codes;
- backup paths;
- validation summaries.

Do not log database passwords.

---

## 31. UI API Endpoints

Exact endpoint names should follow current application conventions.

Conceptual endpoints:

```text
GET  /api/database-migration/status
GET  /api/database-migration/current
GET  /api/database-migration/backups
POST /api/database-migration/backup
POST /api/database-migration/verify
POST /api/database-migration/restore
GET  /api/database-migration/operations/{id}
```

If the control panel uses server-rendered pages rather than a separate API architecture, Codex should adapt these operations to the established pattern rather than introduce a new frontend architecture.

---

## 32. UI State Behavior

### Backup

Disable backup action while another migration operation is active.

### Restore

Restore must remain disabled until:

```text
selected backup verified == true
```

### Migration in Progress

Display:

```text
Database migration in progress.
The control panel may become temporarily unavailable.
```

### After Restart

Read persistent migration state and display success/failure.

---

## 33. Recommended Classroom Workflow

### Before Final Migration

The classroom laptop may contain:

```text
pickleball
    └── tournament-development/test database
```

The instructor can continue testing normally.

### Final Migration

1. Copy the verified production migration package to the classroom laptop.
2. Place it in the configured migration backup directory.
3. Start the control panel.
4. Open **Database Migration**.
5. Select the final production migration package.
6. Verify package status is `VERIFIED`.
7. Start restore.
8. System automatically backs up the existing classroom database.
9. System verifies that safety backup.
10. Application services stop.
11. Existing database is replaced.
12. Production backup is restored.
13. Validation runs.
14. Application restarts.
15. Control panel displays migration success.

No database configuration changes are required.

---

## 34. Rollback Workflow

If the instructor later needs the pre-migration classroom environment:

```text
Safety backup:
pickleball_before_restore_<timestamp>
```

can be restored using the same migration tooling.

The UI may initially expose this as a normal migration package once verification succeeds.

A special rollback button is not required in version 1.

---

## 35. Validation Requirements

After production restore, validation must include:

- PostgreSQL connection success;
- expected database name;
- expected PostgreSQL version;
- required schema presence;
- required critical table presence;
- critical row-count equality;
- successful archive restore;
- application database health check;
- existing realism/certification validation where appropriate.

The restored database is not considered ready for tournament use until validation succeeds.

---

## 36. Acceptance Criteria

### UI

- [ ] Database Migration tab exists.
- [ ] Current database information displays correctly.
- [ ] Migration backup can be created.
- [ ] Backup progress and result are visible.
- [ ] Existing verified backup packages can be listed/selected.
- [ ] Incoming package verification is visible.
- [ ] Restore requires explicit confirmation.
- [ ] Migration result survives application restart.

### Backup

- [ ] PostgreSQL custom-format archive is created.
- [ ] PostgreSQL globals are captured.
- [ ] Row counts are captured.
- [ ] Manifest is generated.
- [ ] SHA-256 checksums are generated.
- [ ] Archive verification succeeds.

### Restore

- [ ] Incoming migration package is verified before restore.
- [ ] Current classroom DB is backed up automatically.
- [ ] Safety backup is verified before database replacement.
- [ ] Existing DB is restored using the same configured database name.
- [ ] Application services are stopped during destructive restore.
- [ ] Production archive restores successfully.
- [ ] Application services restart successfully.

### Validation

- [ ] Restored counts match source counts.
- [ ] Application can connect after restart.
- [ ] Existing database validation routines can execute.
- [ ] Final migration status is recorded.

### Safety

- [ ] Failure before destructive restore leaves current DB untouched.
- [ ] Safety backup location is recorded.
- [ ] Concurrent migrations are blocked.
- [ ] Credentials are not exposed.
- [ ] No ORM/database-name refactor is required.

---

## 37. Implementation Plan

### Phase 1 — Repository Discovery

Codex must first inspect the existing repository without changing behavior.

Identify:

- control panel framework and tab implementation;
- FastAPI route structure;
- frontend/server-rendering pattern;
- PostgreSQL Docker configuration;
- current database configuration;
- application startup scripts;
- background worker startup/shutdown behavior;
- existing job infrastructure;
- realism audit/certification functions;
- database utility modules;
- logging conventions;
- runtime directories;
- existing backup scripts, if any.

Deliverable:

```text
Short implementation findings summary
```

Do not redesign the application architecture unless required.

### Phase 2 — Core Backup Services

Implement/test:

```text
backup_database
verify_database_backup
```

Requirements:

- callable from CLI;
- usable independently of control panel;
- produce required migration package;
- return machine-readable status to the application.

Add unit/integration tests where practical.

### Phase 3 — Restore and Safety Backup Services

Implement:

```text
restore_database
validate_restored_database
migrate_classroom_database
```

The migration orchestration must:

1. verify incoming backup;
2. back up current database;
3. verify safety backup;
4. stop database-writing services;
5. restore same-name database;
6. validate;
7. restart services.

Test initially using non-production local databases.

### Phase 4 — Persistent Migration State

Implement:

```text
operation ID
migration lock
status JSON
migration log
```

Verify that progress/result can be read after application restart.

### Phase 5 — Control Panel Read-Only UI

Add the new tab with:

- current database information;
- existing backup packages;
- last migration status.

Do not yet expose destructive restore.

Validate styling and consistency with the existing control panel.

### Phase 6 — Backup UI Integration

Add:

```text
Create Migration Backup
Verify Backup
```

Display stage progress and final status.

Confirm the same underlying backup service works from both CLI and UI.

### Phase 7 — Restore UI Integration

Determine whether the current process model safely supports a detached migration orchestrator.

If yes:

```text
UI request
→ detached migration process
→ application shutdown
→ restore
→ restart
→ UI result after restart
```

If no, implement the safer first version:

```text
UI verifies package
UI displays exact migration command
CLI executes migration
UI displays result after restart
```

Do not force full UI automation at the expense of reliability.

### Phase 8 — Failure and Rollback Testing

Test:

- corrupt incoming archive;
- failed checksum;
- missing manifest;
- wrong database name;
- unsupported PostgreSQL version;
- safety backup failure;
- restore failure;
- application restart failure;
- validation mismatch;
- concurrent migration attempt.

Confirm existing database remains protected where expected.

### Phase 9 — Classroom Migration Dry Run

Perform a full end-to-end rehearsal.

Scenario:

```text
Classroom laptop contains earlier tournament test database.
```

Steps:

1. create production-style migration package on development machine;
2. copy package to classroom laptop;
3. verify package;
4. initiate migration;
5. verify automatic safety backup of classroom DB;
6. restore production DB under same DB name;
7. validate;
8. start control panel;
9. run tournament simulator smoke test;
10. optionally restore the pre-migration safety backup to prove rollback.

Document results.

---

## 38. Recommended Codex Implementation Prompt

> Implement the Database Migration control-panel capability defined in this design document.
>
> Begin with repository discovery. Do not make architectural changes until you have identified the existing control-panel structure, PostgreSQL configuration, startup scripts, background-worker lifecycle, certification routines, and current database utility patterns.
>
> Preserve the existing application database name. Do not introduce runtime database switching or ORM changes.
>
> Build PostgreSQL-native backup and restore services that also work independently from the command line.
>
> The restore workflow must first verify the incoming migration package, then create and verify a safety backup of the existing classroom database. The existing database may only be replaced after both validations pass.
>
> Reuse existing application conventions and infrastructure wherever practical. Prefer the least invasive implementation that satisfies the specification.
>
> Before implementing destructive UI restore, determine whether a detached restore process can safely shut down and restart the control panel. If not, implement UI-assisted verification with CLI restore rather than introducing fragile self-modifying application behavior.
>
> Add tests and documentation for the complete migration workflow.

---

## 39. Final Design Decision

The NAPA database migration capability should be implemented as a **small operational feature around the existing application**, not as a new database-management architecture.

The final design is:

```text
Same application
Same ORM
Same connection configuration
Same database name

          +

Verified PostgreSQL migration package
Automatic pre-restore classroom backup
Safe replacement process
Post-restore validation
Control panel visibility
```

This provides the required portability and safety while minimizing risk to the existing NAPA generator and tournament simulation codebase.
