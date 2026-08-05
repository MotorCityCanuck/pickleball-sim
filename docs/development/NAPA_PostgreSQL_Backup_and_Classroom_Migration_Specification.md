# NAPA PostgreSQL Database Backup and Classroom Migration Specification

**Document Type:** Technical Specification and Implementation Plan  
**Project:** DSB6000 NAPA Pickleball Simulation  
**Purpose:** Preserve, migrate, restore, and validate the instructor PostgreSQL simulation database on the classroom laptop environment  
**Primary Audience:** Instructor / Codex implementation workflow  
**Status:** Implementation Specification

---

## 1. Purpose

This document defines the required scripts, controls, validation steps, and operating procedures needed to:

1. Create a complete, verifiable backup of the NAPA PostgreSQL database running in Docker.
2. Preserve the exact database state used to generate the final 250K production dataset.
3. Move the backup from the development machine to the classroom laptop.
4. Restore the database into the classroom laptop PostgreSQL Docker environment.
5. Validate that the restored database is functionally and structurally equivalent to the source database.
6. Provide repeatable backup and restore procedures suitable for future development freezes, instructor testing, and classroom tournament execution.

The primary requirement is preservation of the **exact database state** required for the instructor-run NAPA tournament simulation. The migration process must not regenerate, rebuild, normalize, reseed, or otherwise alter the source simulation data.

---

## 2. Background and Design Context

The NAPA simulation environment uses PostgreSQL running in a Docker container as the operational database for the synthetic pickleball data generator and tournament simulation.

The instructor intends to:

- complete generation and certification of the 250K production dataset;
- preserve the exact database state associated with that dataset;
- move the generator application and PostgreSQL database to a classroom laptop;
- use the preserved database for later instructor-run tournament simulations; and
- prevent subsequent development or testing activity from accidentally changing the frozen production database.

The migration mechanism must therefore preserve database state independently of the application repository.

Git source control is not sufficient because the database contains generated data and state that are not reproduced solely from the application code.

---

## 3. Objectives

The solution must provide a simple, reliable workflow with the following capabilities:

### 3.1 Backup

Create a complete logical PostgreSQL backup containing:

- schemas;
- tables;
- table data;
- sequences;
- indexes;
- constraints;
- views;
- functions;
- triggers;
- other database-local objects supported by `pg_dump`.

The backup process must also capture PostgreSQL global objects where relevant, including:

- roles;
- role attributes;
- grants;
- other cluster-level objects supported by `pg_dumpall --globals-only`.

### 3.2 Verification

A backup must not be considered valid merely because the backup command completes successfully.

The process must verify:

- backup archive readability;
- backup file existence;
- non-zero backup size;
- checksum generation;
- metadata completeness;
- source database connectivity;
- expected source database identity;
- source row counts for critical tables.

An optional deep verification mode should restore the backup into a temporary validation database and compare critical source/restore counts.

### 3.3 Migration

The solution must support copying the frozen backup package from the development machine to the classroom laptop using a normal file transfer mechanism such as:

- external SSD;
- secure network share;
- Synology NAS;
- SCP/SFTP;
- another instructor-controlled file transfer mechanism.

The implementation must not assume a specific transport method.

### 3.4 Restore

The classroom laptop must be able to:

- initialize the PostgreSQL Docker environment;
- verify PostgreSQL compatibility;
- restore global objects if needed;
- create a new target database;
- restore the database backup;
- validate the restored environment;
- prevent accidental overwrite of an existing database unless explicitly requested.

### 3.5 Validation

The restored database must be validated before it is accepted for classroom use.

Validation must include at minimum:

- database connection;
- schema/object presence;
- critical table presence;
- row-count comparison;
- foreign-key integrity checks where practical;
- PostgreSQL restore success;
- application connectivity;
- backup checksum validation.

---

## 4. Non-Goals

The implementation is not intended to:

- create a new data-generation process;
- regenerate the 250K dataset;
- migrate raw Parquet student datasets;
- modify the NAPA schema;
- transform data during migration;
- upgrade PostgreSQL;
- change hidden simulation parameters;
- rebuild the database from source code;
- alter release contents;
- combine multiple releases into a single database;
- introduce cloud database services.

The migration should preserve the existing database as-is.

---

## 5. Required Script Set

Codex must implement the following scripts under the repository's existing `scripts/` directory unless the current repository structure strongly indicates a different established location.

```text
scripts/
    backup_database.sh
    restore_database.sh
    verify_database_backup.sh
    validate_restored_database.sh
```

An additional orchestration script is recommended:

```text
scripts/
    freeze_database_release.sh
```

If a common shell utility framework already exists in the repository, the new scripts should reuse it rather than duplicate environment discovery, logging, or Docker helper logic.

---

# 6. `backup_database.sh`

## 6.1 Purpose

Create a complete, timestamped, verifiable PostgreSQL backup package.

## 6.2 Required Behavior

The script must:

1. enable strict shell execution;
2. load database configuration from the established project configuration or environment;
3. identify the PostgreSQL Docker container;
4. confirm the container is running;
5. confirm PostgreSQL is accepting connections;
6. confirm the configured source database exists;
7. capture relevant environment metadata;
8. run `pg_dump` using PostgreSQL custom archive format;
9. capture global objects using `pg_dumpall --globals-only`;
10. generate a backup manifest;
11. generate SHA-256 checksums;
12. capture row counts for defined critical tables;
13. run archive verification;
14. return a non-zero exit code on any failure.

Recommended shell safety:

```bash
set -euo pipefail
```

## 6.3 Backup Format

The database backup must use PostgreSQL custom format:

```bash
pg_dump -Fc
```

The custom format is required because it:

- is compressed;
- supports selective inspection;
- supports `pg_restore`;
- provides better restore control than plain SQL;
- can be validated using `pg_restore --list`.

## 6.4 Output Structure

Each backup must be placed in a unique timestamped directory.

Example:

```text
backups/
  napa_2026-08-05_131500/
    database.dump
    postgres_globals.sql
    manifest.txt
    row_counts.csv
    SHA256SUMS
```

The script should support an alternate output directory through a command-line option.

Example:

```bash
./scripts/backup_database.sh \
    --output-dir /mnt/d/napa_backups
```

## 6.5 Required Manifest Contents

`manifest.txt` must include at minimum:

```text
backup_timestamp=
source_hostname=
source_os=
git_commit=
git_branch=
docker_container=
docker_image=
postgres_version=
database_name=
database_size=
backup_file=
backup_file_size=
globals_file=
verification_status=
```

Where available, also record:

```text
generator_release=
dataset_scale=
release_name=
certification_status=
certification_timestamp=
```

The script must not fabricate values that are not available. Unknown values should be recorded as:

```text
UNKNOWN
```

## 6.6 Critical Table Row Counts

The script must capture row counts for all application-critical PostgreSQL tables.

Codex must inspect the actual schema and identify the authoritative table list rather than hard-code assumptions from this document.

At minimum, the table list should include the major NAPA entities corresponding to:

- players;
- teams;
- team memberships;
- matches;
- match teams;
- match team players;
- match games;
- regions;
- clubs;
- club memberships;
- player registrations;
- player assessment history;
- monthly batches;

plus any generator-specific control, configuration, audit, simulation, hidden-bias, or metadata tables required to reproduce the frozen simulation state.

The resulting file should use a machine-readable format such as:

```csv
schema,table,row_count
public,players,250123
public,teams,1048576
...
```

The actual schemas and table names must be discovered from the running database.

---

# 7. `verify_database_backup.sh`

## 7.1 Purpose

Confirm that a backup package is complete and readable before it is moved or accepted as a frozen release.

## 7.2 Required Checks

The script must verify:

- backup directory exists;
- `database.dump` exists;
- backup is non-zero length;
- `postgres_globals.sql` exists;
- `manifest.txt` exists;
- `row_counts.csv` exists;
- `SHA256SUMS` exists;
- all SHA-256 checksums pass;
- `pg_restore --list database.dump` succeeds;
- archive contains expected database objects;
- manifest database name matches requested/expected database.

Example archive validation:

```bash
pg_restore --list database.dump > /dev/null
```

Any failed check must cause a non-zero exit code.

## 7.3 Optional Deep Verification

Support:

```bash
./scripts/verify_database_backup.sh \
    --deep
```

Deep verification should:

1. create a temporary database;
2. restore the backup;
3. compare critical row counts;
4. optionally execute integrity queries;
5. drop the temporary database after successful verification.

The temporary validation database must have an unmistakable name such as:

```text
napa_backup_validation_<timestamp>
```

The script must not operate on the production database during deep validation.

---

# 8. `restore_database.sh`

## 8.1 Purpose

Restore a previously created NAPA backup package into the PostgreSQL Docker environment on the classroom laptop.

## 8.2 Safety Requirements

The restore script must default to safe behavior.

It must:

- refuse to overwrite an existing database by default;
- require explicit confirmation or a specific force flag before destructive action;
- clearly display source backup and destination database;
- validate checksums before restore;
- verify Docker/PostgreSQL availability;
- stop immediately if archive verification fails.

Example:

```bash
./scripts/restore_database.sh \
    --backup-dir /path/to/napa_2026-08-05_131500 \
    --target-db napa_250k_frozen
```

If the database already exists:

```text
ERROR: Database napa_250k_frozen already exists.
Restore aborted.
```

A force option may be implemented:

```bash
--replace-existing
```

but must never be assumed implicitly.

## 8.3 PostgreSQL Compatibility

The script must identify:

- source PostgreSQL version from the manifest;
- destination PostgreSQL version;
- Docker image/version in use.

If major-version compatibility is questionable, the script should abort with a clear explanation unless an explicit override is supplied.

The implementation should prefer restoring into the same PostgreSQL major version used on the source development machine.

## 8.4 Restore Sequence

The default sequence should be:

```text
Verify backup package
        ↓
Check PostgreSQL
        ↓
Check version compatibility
        ↓
Restore global objects
        ↓
Create target database
        ↓
Restore database.dump
        ↓
Run ANALYZE if appropriate
        ↓
Run restored database validation
        ↓
Report success
```

## 8.5 Global Objects

The script should safely restore `postgres_globals.sql`.

It must tolerate already-existing standard PostgreSQL roles where appropriate and must not unnecessarily modify unrelated roles.

If the project database uses only the existing container's standard application role, Codex may implement targeted handling rather than blindly applying all cluster globals.

This behavior should be documented.

---

# 9. `validate_restored_database.sh`

## 9.1 Purpose

Provide a formal acceptance test that the classroom database matches the frozen source database sufficiently for instructor use.

## 9.2 Required Checks

The script must verify:

### Database availability

- target database exists;
- target accepts connections;
- expected application user can connect.

### Object inventory

Compare expected critical objects against the restored database.

At minimum:

- schemas;
- tables;
- critical views/functions where application execution depends on them.

### Row counts

Compare restored row counts against `row_counts.csv`.

Any mismatch must be reported.

Recommended output:

```text
PASS players                   source=250123 restored=250123
PASS teams                     source=1048576 restored=1048576
PASS matches                   source=3812450 restored=3812450
FAIL match_games               source=5321021 restored=5321019
```

A mismatch in any required table must result in failure.

### Application connectivity

Where practical, invoke an existing lightweight application/database health check rather than starting a full simulation.

The validation should confirm that the generator/control-panel application can establish a database connection to the restored database.

### Integrity checks

Reuse existing realism audit or database certification routines where appropriate.

The restore validation script should not duplicate mature validation logic that already exists in the application.

---

# 10. `freeze_database_release.sh`

## 10.1 Purpose

Provide a single instructor-facing command to freeze the production database after certification.

Recommended usage:

```bash
./scripts/freeze_database_release.sh 250k
```

## 10.2 Required Workflow

The script should orchestrate existing application capabilities wherever possible.

Recommended flow:

```text
Confirm target release
        ↓
Confirm database
        ↓
Run realism/database certification
        ↓
Require certification success
        ↓
Capture current Git commit
        ↓
Create database backup
        ↓
Verify backup
        ↓
Generate freeze manifest
        ↓
Mark backup package as frozen
```

If the repository already has separate export tooling for the student-facing Parquet data, the freeze script may optionally record the exported dataset path and checksum, but it should not take ownership of that export unless explicitly designed to do so.

---

# 11. Frozen Release Protection

Once the 250K production database is frozen, the instructor must be able to distinguish it from active development databases.

Recommended naming:

```text
napa_250k_frozen
```

or another project-standard name.

The frozen backup package must be treated as immutable.

Recommended operating practice:

```text
development DB     -> may continue changing
250K frozen DB     -> classroom/tournament source of truth
backup archive     -> immutable recovery copy
```

If the same PostgreSQL container hosts multiple databases, the scripts must operate only on the explicitly selected database.

No script may assume that the container contains only one database.

---

# 12. Multi-Database Container Compatibility

The backup and restore scripts must support a PostgreSQL container containing multiple NAPA databases.

Example:

```text
postgres container
    ├── napa_dev
    ├── napa_5k
    ├── napa_50k
    └── napa_250k_frozen
```

All scripts must require or resolve an explicit database target.

Destructive operations must be scoped only to that target database.

The introduction of these scripts must not require splitting databases into separate containers.

---

# 13. Configuration Requirements

The scripts must reuse existing environment configuration where possible.

Avoid embedding credentials in the scripts.

Supported sources may include:

- `.env`;
- Docker Compose environment variables;
- project configuration files;
- shell environment variables.

Example variables:

```text
POSTGRES_CONTAINER=
POSTGRES_HOST=
POSTGRES_PORT=
POSTGRES_USER=
POSTGRES_DB=
```

Passwords must not be:

- committed to Git;
- printed in logs;
- stored in the manifest;
- written into backup metadata.

---

# 14. Logging Requirements

Each script must produce readable console output.

Example:

```text
[napa-backup] Database: napa_250k
[napa-backup] Container: pickleball-postgres
[napa-backup] Checking PostgreSQL...
[napa-backup] Capturing row counts...
[napa-backup] Creating database.dump...
[napa-backup] Creating globals backup...
[napa-backup] Generating SHA256 checksums...
[napa-backup] Verifying archive...
[napa-backup] Backup completed successfully.
```

On failure:

```text
[napa-backup] ERROR: pg_dump failed.
```

Avoid excessively verbose PostgreSQL output unless a verbose/debug option is enabled.

---

# 15. Command-Line Interface

Recommended common options:

```text
--database
--container
--output-dir
--backup-dir
--target-db
--deep
--replace-existing
--verbose
--help
```

Each script must implement:

```bash
--help
```

with clear usage documentation.

---

# 16. Backup Storage Rules

Backups must not be committed to Git.

Codex must verify `.gitignore` contains appropriate entries such as:

```gitignore
/backups/
*.dump
*.backup
```

Do not ignore SQL generally because project SQL source files may be version-controlled.

The implementation should not automatically delete old backups unless a separate explicit retention feature is requested later.

---

# 17. Classroom Laptop Migration Procedure

The repository documentation must include the following operating sequence.

## 17.1 Development Machine

```text
1. Complete final 250K generation.
2. Run database certification / realism audit.
3. Correct any unacceptable issues.
4. Freeze application code at an identified Git commit.
5. Run freeze_database_release.sh.
6. Confirm backup verification succeeds.
7. Copy the complete backup directory to secondary storage.
8. Preserve an additional backup copy.
```

## 17.2 Classroom Laptop

```text
1. Install/confirm Docker Desktop.
2. Clone or update the NAPA application repository.
3. Checkout the frozen application Git commit or release tag.
4. Start the PostgreSQL container.
5. Copy the backup package to the laptop.
6. Run verify_database_backup.sh.
7. Run restore_database.sh.
8. Run validate_restored_database.sh.
9. Start the NAPA application.
10. Execute a non-destructive smoke test.
```

---

# 18. Freeze Manifest

The production freeze package should contain a second high-level file:

```text
FREEZE_MANIFEST.md
```

Recommended contents:

```markdown
# NAPA Production Database Freeze

Release: 250K
Freeze Date:
Database:
PostgreSQL Version:
Docker Image:
Git Commit:
Git Tag:
Certification Result:
Backup Verification:
Deep Restore Verification:
Backup SHA-256:
Instructor Notes:
```

This file is intended to make it obvious which code and database state belong together.

---

# 19. Acceptance Criteria

The implementation is complete only when all of the following are demonstrated.

## Backup

- [ ] Backup script successfully backs up the running database.
- [ ] Backup uses PostgreSQL custom archive format.
- [ ] PostgreSQL globals are captured.
- [ ] Manifest is generated.
- [ ] Critical row counts are captured.
- [ ] SHA-256 checksums are generated.
- [ ] Archive verification succeeds.

## Restore

- [ ] Backup restores into a fresh database.
- [ ] Existing database is not overwritten accidentally.
- [ ] Global objects are handled safely.
- [ ] PostgreSQL version compatibility is checked.
- [ ] Restore failure causes a non-zero return code.

## Validation

- [ ] Restored database is accessible.
- [ ] Critical table counts match the source.
- [ ] Required database objects are present.
- [ ] Application can connect.
- [ ] Existing certification/realism audit can run against the restored database.
- [ ] Deep verification succeeds on a test restore.

## Migration

- [ ] Backup can be copied to another machine.
- [ ] Classroom laptop restore procedure is documented.
- [ ] Backup is independent of Docker volume identity.
- [ ] Backup does not depend on WSL filesystem paths from the original machine.
- [ ] Same backup can be restored repeatedly into clean environments.

---

# 20. Test Plan

Codex must add or document tests covering at least the following scenarios.

### Test 1 — Normal backup

Expected:

```text
backup succeeds
manifest generated
checksums pass
pg_restore --list succeeds
```

### Test 2 — PostgreSQL container stopped

Expected:

```text
backup aborts
clear error returned
no successful backup status recorded
```

### Test 3 — Invalid database name

Expected:

```text
backup aborts safely
```

### Test 4 — Corrupted backup

Modify/corrupt a copy of `database.dump`.

Expected:

```text
checksum verification fails
restore is refused
```

### Test 5 — Restore to new database

Expected:

```text
database created
restore succeeds
row counts match
```

### Test 6 — Restore over existing database

Expected:

```text
restore refused without --replace-existing
```

### Test 7 — Deep verification

Expected:

```text
temporary DB created
backup restored
counts validated
temporary DB removed
```

### Test 8 — Classroom migration simulation

Copy backup to another path/environment.

Expected:

```text
restore does not depend on original local filesystem paths
```

---

# 21. Documentation Deliverables

Codex must update or create repository documentation describing:

```text
docs/database_backup_restore.md
```

The document must contain:

- purpose;
- prerequisites;
- backup procedure;
- verification procedure;
- transfer procedure;
- restore procedure;
- validation procedure;
- recovery from common failures;
- examples;
- frozen production database handling.

The repository README should include a short link to this document rather than duplicating the instructions.

---

# 22. Implementation Constraints

Codex must follow these constraints:

1. Do not change existing database schemas solely to support backup.
2. Do not change generator logic.
3. Do not change simulation logic.
4. Do not alter hidden bias configuration behavior.
5. Do not introduce a new database technology.
6. Reuse existing Docker/PostgreSQL configuration.
7. Reuse existing certification and realism-audit capabilities where appropriate.
8. Do not store passwords in scripts or generated manifests.
9. Do not require the Docker volume to be copied directly.
10. Prefer standard PostgreSQL utilities available inside the PostgreSQL container.
11. Maintain Linux/WSL compatibility.
12. Design the restore workflow so it can run on the instructor's Windows classroom laptop using Docker Desktop and WSL.

---

# 23. Recommended Implementation Sequence

Codex should implement the feature incrementally.

## Phase 1 — Repository Discovery

Inspect:

- Docker Compose configuration;
- PostgreSQL container naming;
- environment variables;
- database initialization;
- schema structure;
- existing shell scripts;
- logging conventions;
- certification/realism-audit entry points;
- `.gitignore`;
- application database configuration.

Do not begin by hard-coding assumed values.

## Phase 2 — Backup Foundation

Implement:

```text
backup_database.sh
verify_database_backup.sh
```

Validate against a development database.

## Phase 3 — Restore

Implement:

```text
restore_database.sh
validate_restored_database.sh
```

Perform a restore into a new local database.

## Phase 4 — Deep Verification

Implement temporary restore validation and row-count comparison.

## Phase 5 — Freeze Workflow

Implement:

```text
freeze_database_release.sh
FREEZE_MANIFEST.md generation
```

Integrate existing certification.

## Phase 6 — Migration Dry Run

Simulate the classroom migration by:

1. creating a backup;
2. copying it outside the repository;
3. removing/creating a clean target database;
4. restoring;
5. validating;
6. launching the application against the restored database.

---

# 24. Design Decision Summary

The required migration strategy is:

```text
PostgreSQL logical backup
        +
PostgreSQL globals backup
        +
metadata manifest
        +
critical row-count baseline
        +
cryptographic checksums
        +
restore validation
```

The Docker volume itself is **not** the primary migration artifact.

A Docker volume snapshot may optionally be maintained as a secondary disaster-recovery artifact, but the supported classroom migration mechanism must be based on PostgreSQL-native backup and restore tooling.

---

# 25. Expected Final User Experience

The desired instructor workflow should be approximately:

### Freeze on Development Machine

```bash
./scripts/freeze_database_release.sh 250k
```

Result:

```text
NAPA 250K database freeze completed successfully.

Backup:
backups/napa_250k_2026-08-05_131500/

Database archive: VERIFIED
Checksums:         VERIFIED
Row counts:        CAPTURED
Certification:     PASSED
Git commit:        <commit>
```

### Restore on Classroom Laptop

```bash
./scripts/restore_database.sh \
    --backup-dir /path/to/napa_250k_2026-08-05_131500 \
    --target-db napa_250k_frozen
```

Then:

```bash
./scripts/validate_restored_database.sh \
    --backup-dir /path/to/napa_250k_2026-08-05_131500 \
    --database napa_250k_frozen
```

Result:

```text
NAPA database migration validation PASSED.

Database:          napa_250k_frozen
Archive checksum:  PASS
Required objects:  PASS
Row counts:        PASS
Application access: PASS
Certification:     PASS

Database is ready for classroom tournament use.
```

---

# 26. Final Requirement

The implementation must provide confidence that the database used for the classroom tournament is the same frozen database state that was certified and preserved after creation of the official NAPA 250K production dataset.

A migration must be considered successful only after the restored database passes the defined validation process.

**Backup creation alone is not sufficient. Restore validation is a required part of the solution.**
