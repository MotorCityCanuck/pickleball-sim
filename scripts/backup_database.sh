#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/napa_database_backup_common.sh
source "$ROOT_DIR/scripts/lib/napa_database_backup_common.sh"

DATABASE="$NAPA_POSTGRES_DB"
CONTAINER="$NAPA_POSTGRES_CONTAINER"
POSTGRES_USER_NAME="$NAPA_POSTGRES_USER"
OUTPUT_ROOT="$ROOT_DIR/backups"
VERBOSE="false"

usage() {
    cat <<'EOF'
Usage: ./scripts/backup_database.sh [options]

Create a complete, timestamped, verifiable PostgreSQL backup package for the
NAPA database running in Docker.

Options:
  --database <name>     Source database to back up. Default: POSTGRES_DB or pickleball
  --container <name>    PostgreSQL Docker container. Default: POSTGRES_CONTAINER or pickleball-postgres
  --user <name>         PostgreSQL user. Default: POSTGRES_USER or postgres
  --output-dir <path>   Directory under which the timestamped backup directory is created.
                        Default: ./backups
  --verbose             Print extra progress details
  --help                Show this help text

Output:
  <output-dir>/napa_<database>_<timestamp>/
    database.dump
    postgres_globals.sql
    manifest.txt
    row_counts.csv
    SHA256SUMS

Environment:
  POSTGRES_CONTAINER, POSTGRES_USER, POSTGRES_DB may be used as defaults.
  Passwords are not printed or written to backup metadata.
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
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
        --output-dir)
            [[ $# -ge 2 ]] || napa_fail "--output-dir requires a value."
            OUTPUT_ROOT="$2"
            shift 2
            ;;
        --verbose)
            VERBOSE="true"
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

sanitize_slug() {
    local value
    value="$1"
    value="${value//[^A-Za-z0-9_.-]/_}"
    printf '%s\n' "$value"
}

file_size_bytes() {
    local file_path
    file_path="$1"
    stat -c '%s' "$file_path" 2>/dev/null || stat -f '%z' "$file_path"
}

write_manifest() {
    local manifest_path backup_timestamp source_hostname source_os git_commit git_branch
    local docker_image postgres_version database_size backup_size globals_size
    local verification_status

    manifest_path="$1"
    backup_timestamp="$2"
    source_hostname="$(hostname 2>/dev/null || printf '%s\n' UNKNOWN)"
    source_os="$(uname -a 2>/dev/null || printf '%s\n' UNKNOWN)"
    git_commit="$(napa_git_commit)"
    git_branch="$(napa_git_branch)"
    docker_image="$(napa_container_image "$CONTAINER")"
    postgres_version="$(napa_postgres_version "$CONTAINER" "$DATABASE" "$POSTGRES_USER_NAME")"
    database_size="$(napa_database_size "$CONTAINER" "$DATABASE" "$POSTGRES_USER_NAME")"
    backup_size="$(file_size_bytes "$BACKUP_FILE")"
    globals_size="$(file_size_bytes "$GLOBALS_FILE")"
    verification_status="$3"

    {
        printf 'backup_timestamp=%s\n' "$backup_timestamp"
        printf 'source_hostname=%s\n' "$source_hostname"
        printf 'source_os=%s\n' "$source_os"
        printf 'git_commit=%s\n' "$git_commit"
        printf 'git_branch=%s\n' "$git_branch"
        printf 'docker_container=%s\n' "$CONTAINER"
        printf 'docker_image=%s\n' "$docker_image"
        printf 'postgres_version=%s\n' "$postgres_version"
        printf 'database_name=%s\n' "$DATABASE"
        printf 'database_size=%s\n' "$database_size"
        printf 'backup_file=%s\n' "$(basename "$BACKUP_FILE")"
        printf 'backup_file_size=%s\n' "$backup_size"
        printf 'globals_file=%s\n' "$(basename "$GLOBALS_FILE")"
        printf 'globals_file_size=%s\n' "$globals_size"
        printf 'row_counts_file=%s\n' "$(basename "$ROW_COUNTS_FILE")"
        printf 'checksums_file=%s\n' "$(basename "$CHECKSUMS_FILE")"
        printf 'verification_status=%s\n' "$verification_status"
        printf 'generator_release=%s\n' "UNKNOWN"
        printf 'dataset_scale=%s\n' "UNKNOWN"
        printf 'release_name=%s\n' "UNKNOWN"
        printf 'certification_status=%s\n' "UNKNOWN"
        printf 'certification_timestamp=%s\n' "UNKNOWN"
    } > "$manifest_path"
}

capture_row_counts() {
    local output_file table_sql count_sql schema_name table_name
    output_file="$1"

    printf 'schema,table,row_count\n' > "$output_file"

    table_sql="
        SELECT table_schema || E'\t' || table_name
        FROM information_schema.tables
        WHERE table_type = 'BASE TABLE'
          AND table_schema NOT IN ('pg_catalog', 'information_schema')
          AND table_schema NOT LIKE 'pg_toast%'
        ORDER BY table_schema, table_name;
    "

    while IFS=$'\t' read -r schema_name table_name; do
        [[ -n "${schema_name:-}" && -n "${table_name:-}" ]] || continue
        count_sql="
            SELECT
                $(napa_quote_sql_literal "$schema_name") || ',' ||
                $(napa_quote_sql_literal "$table_name") || ',' ||
                count(*)::text
            FROM $(napa_quote_identifier "$schema_name").$(napa_quote_identifier "$table_name");
        "
        napa_psql_quiet "$CONTAINER" "$DATABASE" "$POSTGRES_USER_NAME" -c "$count_sql" >> "$output_file"
        if [[ "$VERBOSE" == "true" ]]; then
            napa_log "Captured row count for ${schema_name}.${table_name}"
        fi
    done < <(napa_psql_quiet "$CONTAINER" "$DATABASE" "$POSTGRES_USER_NAME" -c "$table_sql")

    [[ "$(wc -l < "$output_file" | tr -d '[:space:]')" -gt 1 ]] || napa_fail "No application tables were discovered for row count capture."
}

napa_require_project_root
napa_require_docker
napa_require_command stat
napa_require_command tr
napa_require_command wc
napa_require_command hostname

BACKUP_SLUG="napa_$(sanitize_slug "$DATABASE")_$(napa_timestamp_local_slug)"
BACKUP_DIR="$OUTPUT_ROOT/$BACKUP_SLUG"
BACKUP_FILE="$BACKUP_DIR/database.dump"
GLOBALS_FILE="$BACKUP_DIR/postgres_globals.sql"
MANIFEST_FILE="$BACKUP_DIR/manifest.txt"
ROW_COUNTS_FILE="$BACKUP_DIR/row_counts.csv"
CHECKSUMS_FILE="$BACKUP_DIR/SHA256SUMS"

napa_log "Database: $DATABASE"
napa_log "Container: $CONTAINER"
napa_log "Output: $BACKUP_DIR"

[[ ! -e "$BACKUP_DIR" ]] || napa_fail "Backup directory already exists: $BACKUP_DIR"

napa_log "Checking PostgreSQL container..."
napa_require_running_container "$CONTAINER"
napa_require_pg_ready "$CONTAINER" "$DATABASE" "$POSTGRES_USER_NAME"
napa_require_database_exists "$CONTAINER" "$DATABASE" "$POSTGRES_USER_NAME"

mkdir -p "$BACKUP_DIR"

napa_log "Capturing row counts..."
capture_row_counts "$ROW_COUNTS_FILE"

napa_log "Creating database.dump..."
napa_pg_dump "$CONTAINER" "$DATABASE" "$POSTGRES_USER_NAME" > "$BACKUP_FILE"
[[ -s "$BACKUP_FILE" ]] || napa_fail "Database dump was not created or is empty."

napa_log "Creating globals backup..."
napa_pg_dumpall_globals "$CONTAINER" "$POSTGRES_USER_NAME" > "$GLOBALS_FILE"
[[ -s "$GLOBALS_FILE" ]] || napa_fail "Globals backup was not created or is empty."

napa_log "Writing manifest..."
write_manifest "$MANIFEST_FILE" "$(napa_timestamp_utc)" "PENDING"

napa_log "Verifying archive readability..."
napa_pg_restore_list "$CONTAINER" < "$BACKUP_FILE" >/dev/null

napa_log "Updating manifest verification status..."
write_manifest "$MANIFEST_FILE" "$(napa_timestamp_utc)" "VERIFIED"

napa_log "Generating SHA-256 checksums..."
napa_write_sha256sums "$CHECKSUMS_FILE" \
    "$BACKUP_FILE" \
    "$GLOBALS_FILE" \
    "$MANIFEST_FILE" \
    "$ROW_COUNTS_FILE"

napa_log "Backup completed successfully."
napa_log "Backup package: $BACKUP_DIR"
