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
scripts/validate_restored_database.sh
scripts/freeze_database_release.sh
```

Shared shell helpers live in:

```text
scripts/lib/napa_database_backup_common.sh
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

## Restore on the classroom laptop

Start PostgreSQL:

```bash
docker compose up -d postgres
```

Verify the copied backup first:

```bash
./scripts/verify_database_backup.sh \
  --backup-dir /path/to/copied/napa_pickleball_<timestamp> \
  --database pickleball
```

Restore into a fresh classroom database:

```bash
./scripts/restore_database.sh \
  --backup-dir /path/to/copied/napa_pickleball_<timestamp> \
  --target-db napa_250k_frozen
```

The restore script refuses to overwrite an existing target database by default.

To intentionally replace only the named target database:

```bash
./scripts/restore_database.sh \
  --backup-dir /path/to/copied/napa_pickleball_<timestamp> \
  --target-db napa_250k_frozen \
  --replace-existing
```

Do not use `--replace-existing` unless replacing that specific target database
is intended.

## Validate a restored database

After restore:

```bash
./scripts/validate_restored_database.sh \
  --backup-dir /path/to/copied/napa_pickleball_<timestamp> \
  --database napa_250k_frozen
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
[validate_restored_database] Database is ready for classroom tournament use: napa_250k_frozen
```

## Application startup against restored DB

Set `DATABASE_URL` to point the app at the restored classroom DB:

```bash
export DATABASE_URL=postgresql://postgres:postgres@localhost:5432/napa_250k_frozen
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
Database 'napa_250k_frozen' already exists. Restore aborted.
```

Fix:

- choose a new target database name, or
- rerun with `--replace-existing` only if replacing that exact database is
  intended

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

Use a clear separation between active development and frozen classroom data:

```text
pickleball          active development/default database
napa_250k_frozen    classroom frozen database
backup package      immutable recovery artifact
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
6. Run `verify_database_backup.sh`.
7. Run `restore_database.sh`.
8. Run `validate_restored_database.sh`.
9. Start the application against the restored database.
10. Execute a non-destructive smoke test.
