#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=scripts/lib/napa_database_backup_common.sh
source "$ROOT_DIR/scripts/lib/napa_database_backup_common.sh"

BACKUP_DIR=""
EXPECTED_DATABASE=""
CONTAINER="$NAPA_POSTGRES_CONTAINER"
POSTGRES_USER_NAME="$NAPA_POSTGRES_USER"
VERBOSE="false"
DEEP="false"

usage() {
    cat <<'EOF'
Usage: ./scripts/verify_database_backup.sh --backup-dir <path> [options]

Verify that a NAPA PostgreSQL backup package is complete, checksummed, and
readable before it is transferred, restored, or accepted as a frozen release.

Options:
  --backup-dir <path>   Backup package directory to verify. Required.
  --database <name>     Expected source database name. If provided, it must
                        match database_name in manifest.txt.
  --container <name>    PostgreSQL Docker container used for pg_restore --list.
                        Default: POSTGRES_CONTAINER or pickleball-postgres
  --user <name>         PostgreSQL user. Default: POSTGRES_USER or postgres
  --deep                Restore into a temporary validation database and compare
                        row counts. The temporary database is always dropped.
  --verbose             Print extra progress details
  --help                Show this help text

Required package files:
  database.dump
  postgres_globals.sql
  manifest.txt
  row_counts.csv
  SHA256SUMS
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
            EXPECTED_DATABASE="$2"
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
        --deep)
            DEEP="true"
            shift
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

[[ -n "$BACKUP_DIR" ]] || napa_fail "--backup-dir is required."

BACKUP_FILE="$BACKUP_DIR/database.dump"
GLOBALS_FILE="$BACKUP_DIR/postgres_globals.sql"
MANIFEST_FILE="$BACKUP_DIR/manifest.txt"
ROW_COUNTS_FILE="$BACKUP_DIR/row_counts.csv"
CHECKSUMS_FILE="$BACKUP_DIR/SHA256SUMS"
DEEP_DATABASE=""
DEEP_DATABASE_CREATED="false"

drop_deep_database() {
    if [[ "$DEEP_DATABASE_CREATED" == "true" && -n "$DEEP_DATABASE" ]]; then
        napa_log "Dropping temporary validation database '$DEEP_DATABASE'..."
        napa_terminate_database_connections "$CONTAINER" "$DEEP_DATABASE" "$POSTGRES_USER_NAME" || true
        napa_drop_database "$CONTAINER" "$DEEP_DATABASE" "$POSTGRES_USER_NAME" || true
        DEEP_DATABASE_CREATED="false"
    fi
}

cleanup_deep_database() {
    local exit_code
    exit_code=$?
    drop_deep_database
    exit "$exit_code"
}

manifest_value() {
    local key
    key="$1"
    awk -F= -v key="$key" '$1 == key { sub(/^[^=]*=/, ""); print; found=1; exit } END { if (!found) exit 1 }' "$MANIFEST_FILE"
}

require_file() {
    local file_path label
    file_path="$1"
    label="$2"
    [[ -f "$file_path" ]] || napa_fail "$label is missing: $file_path"
}

require_non_empty_file() {
    local file_path label
    file_path="$1"
    label="$2"
    require_file "$file_path" "$label"
    [[ -s "$file_path" ]] || napa_fail "$label is empty: $file_path"
}

require_manifest_key() {
    local key value
    key="$1"
    value="$(manifest_value "$key" 2>/dev/null || true)"
    [[ -n "$value" ]] || napa_fail "manifest.txt is missing required key: $key"
    if [[ "$VERBOSE" == "true" ]]; then
        napa_log "Manifest $key=$value"
    fi
}

verify_row_counts_file() {
    local header line_count invalid_rows
    header="$(head -n 1 "$ROW_COUNTS_FILE")"
    [[ "$header" == "schema,table,row_count" ]] || napa_fail "row_counts.csv has invalid header: $header"

    line_count="$(wc -l < "$ROW_COUNTS_FILE" | tr -d '[:space:]')"
    [[ "$line_count" -gt 1 ]] || napa_fail "row_counts.csv contains no table counts."

    invalid_rows="$(
        awk -F, '
            NR == 1 { next }
            NF != 3 || $1 == "" || $2 == "" || $3 !~ /^[0-9]+$/ { count++ }
            END { print count + 0 }
        ' "$ROW_COUNTS_FILE"
    )"
    [[ "$invalid_rows" == "0" ]] || napa_fail "row_counts.csv contains $invalid_rows invalid row(s)."
}

verify_manifest_files_match() {
    local backup_file globals_file row_counts_file checksums_file verification_status
    backup_file="$(manifest_value backup_file 2>/dev/null || true)"
    globals_file="$(manifest_value globals_file 2>/dev/null || true)"
    row_counts_file="$(manifest_value row_counts_file 2>/dev/null || true)"
    checksums_file="$(manifest_value checksums_file 2>/dev/null || true)"
    verification_status="$(manifest_value verification_status 2>/dev/null || true)"

    [[ "$backup_file" == "database.dump" ]] || napa_fail "manifest backup_file must be database.dump; found '$backup_file'."
    [[ "$globals_file" == "postgres_globals.sql" ]] || napa_fail "manifest globals_file must be postgres_globals.sql; found '$globals_file'."
    [[ "$row_counts_file" == "row_counts.csv" ]] || napa_fail "manifest row_counts_file must be row_counts.csv; found '$row_counts_file'."
    [[ "$checksums_file" == "SHA256SUMS" ]] || napa_fail "manifest checksums_file must be SHA256SUMS; found '$checksums_file'."
    [[ "$verification_status" == "VERIFIED" ]] || napa_fail "manifest verification_status must be VERIFIED; found '$verification_status'."
}

verify_expected_database() {
    local manifest_database
    manifest_database="$(manifest_value database_name 2>/dev/null || true)"
    [[ -n "$manifest_database" ]] || napa_fail "manifest.txt is missing database_name."

    if [[ -n "$EXPECTED_DATABASE" && "$manifest_database" != "$EXPECTED_DATABASE" ]]; then
        napa_fail "Manifest database_name '$manifest_database' does not match expected database '$EXPECTED_DATABASE'."
    fi
}

verify_archive_contains_row_count_tables() {
    local archive_list missing_count
    archive_list="$(mktemp)"

    napa_pg_restore_list "$CONTAINER" < "$BACKUP_FILE" > "$archive_list"

    missing_count="$(
        awk -F, -v list_file="$archive_list" '
            BEGIN {
                while ((getline line < list_file) > 0) {
                    archive = archive "\n" line
                }
            }
            NR == 1 { next }
            {
                table_pattern = " TABLE " $1 " " $2
                table_data_pattern = " TABLE DATA " $1 " " $2
                if (index(archive, table_pattern) == 0 && index(archive, table_data_pattern) == 0) {
                    print $1 "." $2
                    count++
                }
            }
            END { exit count > 0 ? 1 : 0 }
        ' "$ROW_COUNTS_FILE" || true
    )"
    rm -f "$archive_list"

    if [[ -n "$missing_count" ]]; then
        printf '%s\n' "$missing_count" >&2
        napa_fail "Archive does not contain one or more tables listed in row_counts.csv."
    fi
}

deep_table_exists() {
    local database schema_name table_name schema_literal table_literal
    database="$1"
    schema_name="$2"
    table_name="$3"
    schema_literal="$(napa_quote_sql_literal "$schema_name")"
    table_literal="$(napa_quote_sql_literal "$table_name")"
    [[ "$(napa_psql_quiet "$CONTAINER" "$database" "$POSTGRES_USER_NAME" -c "
        SELECT 1
        FROM information_schema.tables
        WHERE table_type = 'BASE TABLE'
          AND table_schema = ${schema_literal}
          AND table_name = ${table_literal};
    " | tr -d '[:space:]')" == "1" ]]
}

deep_table_row_count() {
    local database schema_name table_name
    database="$1"
    schema_name="$2"
    table_name="$3"
    napa_psql_quiet "$CONTAINER" "$database" "$POSTGRES_USER_NAME" -c "
        SELECT count(*)::text
        FROM $(napa_quote_identifier "$schema_name").$(napa_quote_identifier "$table_name");
    " | tr -d '[:space:]'
}

compare_deep_row_counts() {
    local database schema_name table_name expected_count actual_count failures checked
    database="$1"
    failures=0
    checked=0

    while IFS=, read -r schema_name table_name expected_count; do
        [[ "$schema_name" != "schema" ]] || continue
        [[ -n "${schema_name:-}" && -n "${table_name:-}" && -n "${expected_count:-}" ]] || continue

        if ! deep_table_exists "$database" "$schema_name" "$table_name"; then
            printf 'FAIL %-40s source=%s restored=MISSING\n' "${schema_name}.${table_name}" "$expected_count"
            failures=$((failures + 1))
            continue
        fi

        actual_count="$(deep_table_row_count "$database" "$schema_name" "$table_name")"
        if [[ "$actual_count" == "$expected_count" ]]; then
            if [[ "$VERBOSE" == "true" ]]; then
                printf 'PASS %-40s source=%s restored=%s\n' "${schema_name}.${table_name}" "$expected_count" "$actual_count"
            fi
        else
            printf 'FAIL %-40s source=%s restored=%s\n' "${schema_name}.${table_name}" "$expected_count" "$actual_count"
            failures=$((failures + 1))
        fi
        checked=$((checked + 1))
    done < "$ROW_COUNTS_FILE"

    [[ "$checked" -gt 0 ]] || napa_fail "No row-count entries were checked in deep verification."
    [[ "$failures" -eq 0 ]] || napa_fail "Deep row-count verification failed for $failures table(s)."
    napa_log "Deep row-count comparison: PASS ($checked table(s))"
}

verify_deep_constraints() {
    local database invalid_fk_count
    database="$1"
    invalid_fk_count="$(
        napa_psql_quiet "$CONTAINER" "$database" "$POSTGRES_USER_NAME" -c "
            SELECT count(*)::text
            FROM pg_constraint
            WHERE contype = 'f'
              AND NOT convalidated;
        " | tr -d '[:space:]'
    )"
    [[ "$invalid_fk_count" == "0" ]] || napa_fail "Deep verification database has $invalid_fk_count unvalidated foreign-key constraint(s)."
    napa_log "Deep foreign-key constraint validation state: PASS"
}

run_deep_verification() {
    DEEP_DATABASE="napa_backup_validation_$(date -u +"%Y%m%d%H%M%S")"

    if napa_database_exists "$CONTAINER" "$DEEP_DATABASE" "$POSTGRES_USER_NAME"; then
        napa_fail "Temporary validation database already exists: $DEEP_DATABASE"
    fi

    trap cleanup_deep_database EXIT INT TERM

    napa_log "Creating temporary validation database '$DEEP_DATABASE'..."
    napa_create_database "$CONTAINER" "$DEEP_DATABASE" "$POSTGRES_USER_NAME"
    DEEP_DATABASE_CREATED="true"

    napa_log "Restoring archive into temporary validation database..."
    napa_pg_restore_database "$CONTAINER" "$DEEP_DATABASE" "$POSTGRES_USER_NAME" < "$BACKUP_FILE"

    napa_log "Comparing row counts in temporary validation database..."
    compare_deep_row_counts "$DEEP_DATABASE"

    napa_log "Checking constraints in temporary validation database..."
    verify_deep_constraints "$DEEP_DATABASE"

    napa_log "Deep verification PASSED."

    drop_deep_database
    trap - EXIT INT TERM
}

napa_require_project_root
napa_require_command awk
napa_require_command head
napa_require_command mktemp
napa_require_command tr
napa_require_command wc

napa_log "Backup directory: $BACKUP_DIR"
napa_log "Checking required files..."
[[ -d "$BACKUP_DIR" ]] || napa_fail "Backup directory does not exist: $BACKUP_DIR"
require_non_empty_file "$BACKUP_FILE" "database.dump"
require_non_empty_file "$GLOBALS_FILE" "postgres_globals.sql"
require_non_empty_file "$MANIFEST_FILE" "manifest.txt"
require_non_empty_file "$ROW_COUNTS_FILE" "row_counts.csv"
require_non_empty_file "$CHECKSUMS_FILE" "SHA256SUMS"

napa_log "Checking manifest completeness..."
require_manifest_key backup_timestamp
require_manifest_key source_hostname
require_manifest_key source_os
require_manifest_key git_commit
require_manifest_key git_branch
require_manifest_key docker_container
require_manifest_key docker_image
require_manifest_key postgres_version
require_manifest_key database_name
require_manifest_key database_size
require_manifest_key backup_file
require_manifest_key backup_file_size
require_manifest_key globals_file
require_manifest_key globals_file_size
require_manifest_key row_counts_file
require_manifest_key checksums_file
require_manifest_key verification_status
verify_manifest_files_match
verify_expected_database

napa_log "Checking row count baseline..."
verify_row_counts_file

napa_log "Verifying SHA-256 checksums..."
napa_verify_sha256sums "$CHECKSUMS_FILE" >/dev/null

napa_log "Verifying archive readability..."
napa_require_docker
napa_require_running_container "$CONTAINER"
napa_require_pg_ready "$CONTAINER" postgres "$POSTGRES_USER_NAME"
napa_pg_restore_list "$CONTAINER" < "$BACKUP_FILE" >/dev/null

napa_log "Checking archive table inventory..."
verify_archive_contains_row_count_tables

if [[ "$DEEP" == "true" ]]; then
    napa_log "Running deep verification..."
    run_deep_verification
fi

napa_log "Backup verification PASSED."
