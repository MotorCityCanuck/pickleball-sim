# NAPA Database Backup, Restore, and Classroom Migration

This document describes the supported workflow for freezing, transferring,
restoring, and validating the NAPA PostgreSQL database for classroom laptop
demonstrations.

The migration artifact is a PostgreSQL logical backup package. Do not copy the
Docker volume as the primary migration mechanism.

## Purpose

Use this workflow when the instructor needs to preserve the exact database state
behind a certified NAPA production dataset, move it to another machine, and run
classroom tournament demonstrations without regenerating data.

The backup and restore scripts preserve:

- schemas
- table data
- sequences
- indexes
- constraints
- views/functions/triggers included by `pg_dump`
- PostgreSQL globals captured by `pg_dumpall --globals-only`
- metadata, row-count baselines, and SHA-256 checksums

The workflow intentionally does not regenerate, reseed, normalize, or transform
simulation data.

## Scripts

The operational scripts live in `scripts/`:

```text
scripts/backup_database.sh
scripts/verify_database_backup.sh
scripts/restore_database.sh
scripts/migrate_classroom_database.sh
scripts/validate_restored_database.sh
scripts/freeze_database_release.sh
```

Shared shell helpers live in:

```text
scripts/lib/napa_database_backup_common.sh
```

## Control panel integration

The instructor control panel now includes a `Database Migration` tab that:

- shows current configured database identity and connection state
- discovers backup packages from the repository `backups/` directory
- launches detached backup operations through the existing shell scripts
- launches detached same-name classroom restore operations through `scripts/migrate_classroom_database.sh`
- renders persistent operation status and log output from filesystem state rather than relying on ORM progress rows during restore

The UI orchestration layer does not reimplement `pg_dump` or `pg_restore`.

Persistent control-panel migration state is stored under:

```text
runtime/database_migration/
  latest_status.json
  database_migration.lock
  operations/<operation_id>.json
```

Operation logs are stored under:

```text
logs/database_migration_<operation_id>.log
```

## Prerequisites

On both the development machine and classroom laptop:

- Docker Desktop with WSL integration enabled
- repository checkout available in WSL
- PostgreSQL container running from `compose.yaml`
- PostgreSQL 16 preferred, matching the project `postgres:16` image
- backend Python environment available for application connectivity checks

Start PostgreSQL:

```bash
docker compose up -d postgres
```

Default connection assumptions:

```text
POSTGRES_CONTAINER=pickleball-postgres
POSTGRES_USER=postgres
POSTGRES_DB=pickleball
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

Override these with environment variables or script flags when needed.

Passwords must not be committed, printed in logs, or written into backup
metadata.

## Backup package structure

A backup package is a timestamped directory:

```text
backups/
  napa_pickleball_2026-08-05_152110/
    database.dump
    postgres_globals.sql
    manifest.txt
    row_counts.csv
    SHA256SUMS
    release_certification.log
    FREEZE_MANIFEST.md
```

Core files:

- `database.dump`: PostgreSQL custom archive from `pg_dump -Fc`
- `postgres_globals.sql`: cluster globals from `pg_dumpall --globals-only`
- `manifest.txt`: source metadata and verification status
- `row_counts.csv`: source row-count baseline for restored validation
- `SHA256SUMS`: checksums for the backup package files
- `FREEZE_MANIFEST.md`: high-level instructor-facing freeze record

Backup packages are ignored by git through `/backups/`, `*.dump`, and
`*.backup`.

## Normal backup

Create a backup of the default database:

```bash
./scripts/backup_database.sh
```

Create a backup in an external or transfer-friendly location:

```bash
./scripts/backup_database.sh \
  --database pickleball \
  --output-dir /mnt/d/napa_backups
```

Expected result:

```text
[backup_database] Backup completed successfully.
[backup_database] Backup package: /path/to/napa_pickleball_<timestamp>
```

## Verify a backup

Always verify a package before transferring it:

```bash
./scripts/verify_database_backup.sh \
  --backup-dir /path/to/napa_pickleball_<timestamp> \
  --database pickleball
```

This checks:

- required files
- manifest completeness
- row-count baseline format
- SHA-256 checksums
- archive readability with `pg_restore --list`
- archive table inventory against `row_counts.csv`

Run deep verification when time allows:

```bash
./scripts/verify_database_backup.sh \
  --backup-dir /path/to/napa_pickleball_<timestamp> \
  --database pickleball \
  --deep
```

Deep verification creates a temporary database named
`napa_backup_validation_<timestamp>`, restores the archive into it, compares row
counts, checks foreign-key constraint validation state, and drops the temporary
database.

## Freeze a production release

After final generation and certification readiness, use the freeze wrapper:

```bash
./scripts/freeze_database_release.sh 250k \
  --database pickleball \
  --output-dir /mnt/d/napa_backups \
  --deep
```

The freeze workflow:

1. confirms Docker/PostgreSQL/database access
2. runs release certification
3. creates a backup
4. verifies the backup
5. optionally runs deep restore verification
6. copies `release_certification.log` into the backup package
7. writes `FREEZE_MANIFEST.md`

For local script smoke tests only:

```bash
./scripts/freeze_database_release.sh smoke \
  --database pickleball \
  --output-dir /tmp/napa_freeze_smoke \
  --skip-certification
```

Do not use `--skip-certification` for production freezes.

Current implementation note: if release certification fails, the freeze script
aborts before backup and reports the retained certification log path. During
implementation testing, the existing certification runner required
`generation_run_id` for `player_roster_summary`; that certification-runner issue
must be resolved or parameterized before a production freeze can complete.

## Transfer procedure

After verification succeeds on the development machine:

1. Copy the complete backup package directory.
2. Keep the directory intact.
3. Do not copy only `database.dump`.
4. Preserve at least one secondary copy.
5. Use any instructor-controlled transfer mechanism:
   - external SSD
   - secure network share
   - NAS
   - SCP/SFTP

The scripts do not depend on the original filesystem path.

## Classroom migration on the laptop

Start PostgreSQL:

```bash
docker compose up -d postgres
```

Verify the copied backup first:

```bash
./scripts/verify_database_backup.sh \
  --backup-dir /path/to/copied/napa_pickleball_<timestamp>
```

The normal classroom workflow preserves the application's existing configured
database name. Do not restore into `napa_250k_frozen` and do not change
`DATABASE_URL` for the normal classroom path.

Run the protected migration wrapper:

```bash
./scripts/migrate_classroom_database.sh \
  --backup-dir /path/to/copied/napa_pickleball_<timestamp>
```

By default this targets the currently configured database name, typically
`pickleball`. The wrapper enforces this sequence:

1. verify the incoming backup package
2. create a complete safety backup of the current classroom database
3. verify that safety backup
4. replace the existing classroom database with the incoming backup
5. validate the restored classroom database

The script leaves the application’s normal database name unchanged, so the
existing `DATABASE_URL` continues to work.

You can override the protected database name when needed:

```bash
./scripts/migrate_classroom_database.sh \
  --backup-dir /path/to/copied/napa_pickleball_<timestamp> \
  --database pickleball
```

Optional safety controls:

```bash
./scripts/migrate_classroom_database.sh \
  --backup-dir /path/to/copied/napa_pickleball_<timestamp> \
  --safety-output-dir /mnt/d/classroom_safety_backups \
  --deep-verify-incoming
```

The generated safety backup is a normal verified PostgreSQL backup package and
can be used to recover the classroom machine’s pre-migration state if needed.

## Alternate restore path for testing

`restore_database.sh` remains available for non-classroom cases such as:

- restoring into a scratch database for testing
- validating a backup in an alternate database name
- local deep verification workflows

Example:

```bash
./scripts/restore_database.sh \
  --backup-dir /path/to/copied/napa_pickleball_<timestamp> \
  --target-db napa_restore_test
```

## Validate a restored database

After a same-name classroom migration:

```bash
./scripts/validate_restored_database.sh \
  --backup-dir /path/to/copied/napa_pickleball_<timestamp> \
  --database pickleball
```

Validation checks:

- backup package verification
- target database existence and readiness
- restored schema/table inventory
- row-count equality against `row_counts.csv`
- foreign-key constraint validation state
- lightweight SQLAlchemy application connectivity

Expected result:

```text
[validate_restored_database] NAPA database migration validation PASSED.
[validate_restored_database] Database is ready for classroom tournament use: pickleball
```

## Application startup against restored DB

The normal classroom migration path does not require changing `DATABASE_URL`.
Start the application with its existing configuration:

```bash
./scripts/start_control_panel.sh --no-browser
```

Then open the control panel and run only non-destructive smoke checks before
classroom use.

## Common failures

### Docker is unavailable

Symptom:

```text
Docker is not available. Start Docker Desktop and confirm WSL integration is enabled.
```

Fix:

- start Docker Desktop
- enable WSL integration for the current distro
- rerun `docker version`

### PostgreSQL container is not running

Symptom:

```text
PostgreSQL container 'pickleball-postgres' is not running.
```

Fix:

```bash
docker compose up -d postgres
```

### Target database already exists

Symptom:

```text
Database 'pickleball' already exists. Restore aborted.
```

Fix:

- for classroom replacement, use `migrate_classroom_database.sh`, which creates
  and verifies a safety backup before replacing the existing configured
  database
- for alternate-database testing, choose a different `--target-db`, or rerun
  `restore_database.sh --replace-existing` only when that exact non-classroom
  target is intended

### Checksum verification fails

Do not restore the package. Recopy the complete backup directory from the source
or regenerate the backup from the development machine.

### PostgreSQL major-version mismatch

Use the same PostgreSQL major version as the source backup whenever possible.
The project default is PostgreSQL 16.

Use `--allow-version-mismatch` only when the compatibility risk has been
accepted explicitly.

### Application connectivity fails

Confirm:

- `DATABASE_URL` points to the restored database
- PostgreSQL port mapping is active
- backend virtualenv dependencies are installed
- the restored DB accepts direct `psql` connections

## Recommended production naming

For the classroom laptop, keep the application’s configured operational database
name unchanged and treat the incoming logical backup package as the frozen
artifact:

```text
pickleball      configured classroom application database
backup package  immutable frozen recovery artifact
safety backup   pre-replacement classroom rollback artifact
```

No script assumes the PostgreSQL container contains only one database.

## Development-machine checklist

1. Complete final production generation.
2. Run certification/realism audit.
3. Resolve unacceptable issues.
4. Freeze source code at a known commit or tag.
5. Run `freeze_database_release.sh`.
6. Confirm backup verification succeeds.
7. Copy the complete backup package to secondary storage.
8. Preserve an additional backup copy.

## Classroom-laptop checklist

1. Install/confirm Docker Desktop.
2. Clone or update the repository.
3. Checkout the frozen commit or tag from `FREEZE_MANIFEST.md`.
4. Start PostgreSQL.
5. Copy the backup package to the laptop.
6. Run `migrate_classroom_database.sh`.
7. Confirm restored validation succeeds.
8. Preserve the generated safety backup.
9. Start the application against the restored database.
10. Execute a non-destructive smoke test.
