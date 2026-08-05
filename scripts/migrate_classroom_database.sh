#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/napa_database_backup_common.sh
source "$ROOT_DIR/scripts/lib/napa_database_backup_common.sh"

BACKUP_DIR=""
DATABASE="$NAPA_POSTGRES_DB"
CONTAINER="$NAPA_POSTGRES_CONTAINER"
POSTGRES_USER_NAME="$NAPA_POSTGRES_USER"
POSTGRES_HOST_NAME="$NAPA_POSTGRES_HOST"
POSTGRES_PORT_VALUE="$NAPA_POSTGRES_PORT"
SAFETY_OUTPUT_ROOT="$ROOT_DIR/backups/classroom_safety"
ALLOW_VERSION_MISMATCH="false"
RESTORE_GLOBALS="false"
SKIP_ANALYZE="false"
SKIP_APP_CHECK="false"
INCOMING_VERIFY_DEEP="false"

usage() {
    cat <<'EOF'
Usage: ./scripts/migrate_classroom_database.sh --backup-dir <path> [options]

Safely replace the existing configured classroom database with an incoming NAPA
backup package while preserving the application's normal database name.

The workflow is:
  verify incoming backup
  create safety backup of the current classroom database
  verify safety backup
  replace the existing classroom database with the incoming backup
  validate the restored classroom database

Options:
  --backup-dir <path>          Incoming backup package directory to restore. Required.
  --database <name>            Existing classroom database to protect and replace.
                               Default: POSTGRES_DB or pickleball
  --container <name>           PostgreSQL Docker container. Default: POSTGRES_CONTAINER or pickleball-postgres
  --user <name>                PostgreSQL user. Default: POSTGRES_USER or postgres
  --host <host>                Host for application connectivity validation. Default: POSTGRES_HOST or localhost
  --port <port>                Port for application connectivity validation. Default: POSTGRES_PORT or 5432
  --safety-output-dir <path>   Root directory for the generated safety backup package.
                               Default: ./backups/classroom_safety
  --deep-verify-incoming       Run deep verification on the incoming backup package.
  --allow-version-mismatch     Pass through to restore_database.sh.
  --restore-globals            Pass through to restore_database.sh.
  --skip-analyze               Pass through to restore_database.sh.
  --skip-app-check             Pass through to validate_restored_database.sh.
  --help                       Show this help text
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --backup-dir)
            [[ $# -ge 2 ]] || napa_fail "--backup-dir requires a value."
            BACKUP_DIR="$2"
            shift 2
            ;;
        --database)
            [[ $# -ge 2 ]] || napa_fail "--database requires a value."
            DATABASE="$2"
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
        --host)
            [[ $# -ge 2 ]] || napa_fail "--host requires a value."
            POSTGRES_HOST_NAME="$2"
            shift 2
            ;;
        --port)
            [[ $# -ge 2 ]] || napa_fail "--port requires a value."
            POSTGRES_PORT_VALUE="$2"
            shift 2
            ;;
        --safety-output-dir)
            [[ $# -ge 2 ]] || napa_fail "--safety-output-dir requires a value."
            SAFETY_OUTPUT_ROOT="$2"
            shift 2
            ;;
        --deep-verify-incoming)
            INCOMING_VERIFY_DEEP="true"
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
        --skip-app-check)
            SKIP_APP_CHECK="true"
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

run_backup_and_capture_dir() {
    local output
    output="$(
        "$ROOT_DIR/scripts/backup_database.sh" \
            --database "$DATABASE" \
            --container "$CONTAINER" \
            --user "$POSTGRES_USER_NAME" \
            --output-dir "$SAFETY_OUTPUT_ROOT"
    )"
    printf '%s\n' "$output"
}

extract_backup_dir() {
    awk -F'Backup package: ' '/Backup package:/ { print $2 }' | tail -n 1
}

napa_require_project_root
napa_require_docker
napa_require_running_container "$CONTAINER"
napa_require_pg_ready "$CONTAINER" "$DATABASE" "$POSTGRES_USER_NAME"
napa_require_database_exists "$CONTAINER" "$DATABASE" "$POSTGRES_USER_NAME"
[[ -x "$ROOT_DIR/scripts/backup_database.sh" ]] || napa_fail "backup_database.sh is missing or not executable."
[[ -x "$ROOT_DIR/scripts/verify_database_backup.sh" ]] || napa_fail "verify_database_backup.sh is missing or not executable."
[[ -x "$ROOT_DIR/scripts/restore_database.sh" ]] || napa_fail "restore_database.sh is missing or not executable."
[[ -x "$ROOT_DIR/scripts/validate_restored_database.sh" ]] || napa_fail "validate_restored_database.sh is missing or not executable."

napa_log "Incoming backup: $BACKUP_DIR"
napa_log "Classroom database: $DATABASE"
napa_log "Container: $CONTAINER"
napa_log "Safety backup root: $SAFETY_OUTPUT_ROOT"

napa_log "Verifying incoming backup package..."
if [[ "$INCOMING_VERIFY_DEEP" == "true" ]]; then
    "$ROOT_DIR/scripts/verify_database_backup.sh" \
        --backup-dir "$BACKUP_DIR" \
        --container "$CONTAINER" \
        --user "$POSTGRES_USER_NAME" \
        --deep
else
    "$ROOT_DIR/scripts/verify_database_backup.sh" \
        --backup-dir "$BACKUP_DIR" \
        --container "$CONTAINER" \
        --user "$POSTGRES_USER_NAME"
fi

napa_log "Creating safety backup of existing classroom database..."
SAFETY_BACKUP_OUTPUT="$(run_backup_and_capture_dir)"
printf '%s\n' "$SAFETY_BACKUP_OUTPUT"
SAFETY_BACKUP_DIR="$(printf '%s\n' "$SAFETY_BACKUP_OUTPUT" | extract_backup_dir)"
[[ -n "$SAFETY_BACKUP_DIR" ]] || napa_fail "Could not determine safety backup directory from backup output."
[[ -d "$SAFETY_BACKUP_DIR" ]] || napa_fail "Safety backup directory was not created: $SAFETY_BACKUP_DIR"

napa_log "Verifying safety backup..."
"$ROOT_DIR/scripts/verify_database_backup.sh" \
    --backup-dir "$SAFETY_BACKUP_DIR" \
    --database "$DATABASE" \
    --container "$CONTAINER" \
    --user "$POSTGRES_USER_NAME"

napa_log "Replacing existing classroom database '$DATABASE'..."
RESTORE_ARGS=(
    --backup-dir "$BACKUP_DIR"
    --target-db "$DATABASE"
    --container "$CONTAINER"
    --user "$POSTGRES_USER_NAME"
    --replace-existing
)
if [[ "$ALLOW_VERSION_MISMATCH" == "true" ]]; then
    RESTORE_ARGS+=(--allow-version-mismatch)
fi
if [[ "$RESTORE_GLOBALS" == "true" ]]; then
    RESTORE_ARGS+=(--restore-globals)
fi
if [[ "$SKIP_ANALYZE" == "true" ]]; then
    RESTORE_ARGS+=(--skip-analyze)
fi
"$ROOT_DIR/scripts/restore_database.sh" "${RESTORE_ARGS[@]}"

napa_log "Validating restored classroom database..."
VALIDATE_ARGS=(
    --backup-dir "$BACKUP_DIR"
    --database "$DATABASE"
    --container "$CONTAINER"
    --user "$POSTGRES_USER_NAME"
    --host "$POSTGRES_HOST_NAME"
    --port "$POSTGRES_PORT_VALUE"
)
if [[ "$SKIP_APP_CHECK" == "true" ]]; then
    VALIDATE_ARGS+=(--skip-app-check)
fi
"$ROOT_DIR/scripts/validate_restored_database.sh" "${VALIDATE_ARGS[@]}"

napa_log "Classroom database migration completed successfully."
napa_log "Classroom database: $DATABASE"
napa_log "Safety backup: $SAFETY_BACKUP_DIR"
