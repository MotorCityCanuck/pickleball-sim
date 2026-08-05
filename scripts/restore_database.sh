#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/napa_database_backup_common.sh
source "$ROOT_DIR/scripts/lib/napa_database_backup_common.sh"

BACKUP_DIR=""
TARGET_DB=""
CONTAINER="$NAPA_POSTGRES_CONTAINER"
POSTGRES_USER_NAME="$NAPA_POSTGRES_USER"
REPLACE_EXISTING="false"
ALLOW_VERSION_MISMATCH="false"
RESTORE_GLOBALS="false"
SKIP_ANALYZE="false"
CREATED_TARGET_DB="false"

usage() {
    cat <<'EOF'
Usage: ./scripts/restore_database.sh --backup-dir <path> --target-db <name> [options]

Restore a verified NAPA PostgreSQL backup package into the Docker PostgreSQL
environment. The script refuses to overwrite an existing database unless
--replace-existing is explicitly supplied.

Options:
  --backup-dir <path>          Backup package directory to restore. Required.
  --target-db <name>           Destination database to create and restore into. Required.
  --container <name>           PostgreSQL Docker container. Default: POSTGRES_CONTAINER or pickleball-postgres
  --user <name>                PostgreSQL user. Default: POSTGRES_USER or postgres
  --replace-existing           Drop and recreate target database if it already exists.
                               This is destructive and scoped only to --target-db.
  --allow-version-mismatch     Permit restore when source/destination PostgreSQL
                               major versions differ or cannot be compared.
  --restore-globals            Apply postgres_globals.sql before database restore.
                               By default globals are skipped to avoid changing
                               the classroom container's standard postgres role.
  --skip-analyze               Skip ANALYZE after restore.
  --help                       Show this help text

Default restore sequence:
  verify backup package
  check Docker/PostgreSQL
  compare PostgreSQL major versions
  optionally restore globals
  create target database
  restore database.dump
  run ANALYZE
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --backup-dir)
            [[ $# -ge 2 ]] || napa_fail "--backup-dir requires a value."
            BACKUP_DIR="$2"
            shift 2
            ;;
        --target-db)
            [[ $# -ge 2 ]] || napa_fail "--target-db requires a value."
            TARGET_DB="$2"
            shift 2
            ;;
        --container)
            [[ $# -ge 2 ]] || napa_fail "--container requires a value."
            CONTAINER="$2"
            shift 2
            ;;
        --user)
            [[ $# -ge 2 ]] || napa_fail "--user requires a value."
            POSTGRES_USER_NAME="$2"
            shift 2
            ;;
        --replace-existing)
            REPLACE_EXISTING="true"
            shift
            ;;
        --allow-version-mismatch)
            ALLOW_VERSION_MISMATCH="true"
            shift
            ;;
        --restore-globals)
            RESTORE_GLOBALS="true"
            shift
            ;;
        --skip-analyze)
            SKIP_ANALYZE="true"
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            napa_fail "Unknown argument: $1"
            ;;
    esac
done

[[ -n "$BACKUP_DIR" ]] || napa_fail "--backup-dir is required."
[[ -n "$TARGET_DB" ]] || napa_fail "--target-db is required."

BACKUP_FILE="$BACKUP_DIR/database.dump"
GLOBALS_FILE="$BACKUP_DIR/postgres_globals.sql"
MANIFEST_FILE="$BACKUP_DIR/manifest.txt"

cleanup_failed_restore() {
    local exit_code
    exit_code=$?
    if [[ "$exit_code" -ne 0 && "$CREATED_TARGET_DB" == "true" ]]; then
        napa_warn "Restore failed after creating '$TARGET_DB'. Dropping incomplete target database."
        napa_terminate_database_connections "$CONTAINER" "$TARGET_DB" "$POSTGRES_USER_NAME" || true
        napa_drop_database "$CONTAINER" "$TARGET_DB" "$POSTGRES_USER_NAME" || true
    fi
    exit "$exit_code"
}

restore_globals_if_requested() {
    if [[ "$RESTORE_GLOBALS" != "true" ]]; then
        napa_log "Skipping globals restore by default."
        napa_log "Use --restore-globals only if this backup contains required non-standard roles."
        return
    fi

    napa_log "Restoring PostgreSQL globals from postgres_globals.sql..."
    napa_warn "Applying globals may alter cluster-level roles. Existing-role errors are tolerated."
    docker exec -i "$CONTAINER" psql -v ON_ERROR_STOP=0 -U "$POSTGRES_USER_NAME" -d postgres < "$GLOBALS_FILE" >/dev/null
}

check_version_compatibility() {
    local source_version source_major destination_version destination_major
    source_version="$(napa_manifest_value "$MANIFEST_FILE" postgres_version 2>/dev/null || printf '%s\n' UNKNOWN)"
    source_major="$(napa_postgres_major_version "$source_version")"
    destination_version="$(napa_postgres_version "$CONTAINER" postgres "$POSTGRES_USER_NAME")"
    destination_major="$(napa_postgres_major_version "$destination_version")"

    napa_log "Source PostgreSQL: $source_version"
    napa_log "Destination PostgreSQL: $destination_version"

    if [[ "$source_major" == "UNKNOWN" || "$destination_major" == "UNKNOWN" ]]; then
        [[ "$ALLOW_VERSION_MISMATCH" == "true" ]] || napa_fail "Could not determine PostgreSQL major-version compatibility. Rerun with --allow-version-mismatch to override."
        napa_warn "Proceeding despite unknown PostgreSQL major-version compatibility."
        return
    fi

    if [[ "$source_major" != "$destination_major" ]]; then
        [[ "$ALLOW_VERSION_MISMATCH" == "true" ]] || napa_fail "PostgreSQL major-version mismatch: source=$source_major destination=$destination_major. Rerun with --allow-version-mismatch to override."
        napa_warn "Proceeding despite PostgreSQL major-version mismatch: source=$source_major destination=$destination_major."
    fi
}

napa_require_project_root
napa_require_command docker
[[ -f "$ROOT_DIR/scripts/verify_database_backup.sh" ]] || napa_fail "verify_database_backup.sh not found."

napa_log "Backup directory: $BACKUP_DIR"
napa_log "Target database: $TARGET_DB"
napa_log "Container: $CONTAINER"

[[ -d "$BACKUP_DIR" ]] || napa_fail "Backup directory does not exist: $BACKUP_DIR"
[[ -s "$BACKUP_FILE" ]] || napa_fail "database.dump is missing or empty: $BACKUP_FILE"
[[ -s "$GLOBALS_FILE" ]] || napa_fail "postgres_globals.sql is missing or empty: $GLOBALS_FILE"
[[ -s "$MANIFEST_FILE" ]] || napa_fail "manifest.txt is missing or empty: $MANIFEST_FILE"

napa_log "Verifying backup package before restore..."
"$ROOT_DIR/scripts/verify_database_backup.sh" \
    --backup-dir "$BACKUP_DIR" \
    --container "$CONTAINER"

napa_log "Checking PostgreSQL container..."
napa_require_docker
napa_require_running_container "$CONTAINER"
napa_require_pg_ready "$CONTAINER" postgres "$POSTGRES_USER_NAME"

check_version_compatibility

if napa_database_exists "$CONTAINER" "$TARGET_DB" "$POSTGRES_USER_NAME"; then
    if [[ "$REPLACE_EXISTING" != "true" ]]; then
        napa_fail "Database '$TARGET_DB' already exists. Restore aborted. Use --replace-existing to drop and recreate it."
    fi
    napa_warn "Replacing existing database '$TARGET_DB'."
    napa_terminate_database_connections "$CONTAINER" "$TARGET_DB" "$POSTGRES_USER_NAME"
    napa_drop_database "$CONTAINER" "$TARGET_DB" "$POSTGRES_USER_NAME"
fi

trap cleanup_failed_restore EXIT INT TERM

restore_globals_if_requested

napa_log "Creating target database '$TARGET_DB'..."
napa_create_database "$CONTAINER" "$TARGET_DB" "$POSTGRES_USER_NAME"
CREATED_TARGET_DB="true"

napa_log "Restoring database.dump into '$TARGET_DB'..."
napa_pg_restore_database "$CONTAINER" "$TARGET_DB" "$POSTGRES_USER_NAME" < "$BACKUP_FILE"

if [[ "$SKIP_ANALYZE" != "true" ]]; then
    napa_log "Running ANALYZE..."
    napa_analyze_database "$CONTAINER" "$TARGET_DB" "$POSTGRES_USER_NAME"
fi

trap - EXIT INT TERM

napa_log "Restore completed successfully."
napa_log "Restored database: $TARGET_DB"
