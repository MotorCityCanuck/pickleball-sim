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
SKIP_BACKUP_VERIFY="false"
SKIP_APP_CHECK="false"
VERBOSE="false"

usage() {
    cat <<'EOF'
Usage: ./scripts/validate_restored_database.sh --backup-dir <path> --database <name> [options]

Validate that a restored NAPA PostgreSQL database matches a frozen backup
package sufficiently for classroom use.

Options:
  --backup-dir <path>       Backup package directory containing row_counts.csv
                            and manifest.txt. Required.
  --database <name>         Restored database to validate. Required.
  --container <name>        PostgreSQL Docker container. Default: POSTGRES_CONTAINER or pickleball-postgres
  --user <name>             PostgreSQL user. Default: POSTGRES_USER or postgres
  --host <host>             Host used for application connectivity check. Default: POSTGRES_HOST or localhost
  --port <port>             Port used for application connectivity check. Default: POSTGRES_PORT or 5432
  --skip-backup-verify      Skip full backup package verification. Row counts and
                            manifest are still required.
  --skip-app-check          Skip lightweight SQLAlchemy application connectivity check.
  --verbose                 Print extra details
  --help                    Show this help text

Validation checks:
  backup checksum/archive verification
  target database existence and readiness
  required schemas/tables from row_counts.csv
  source/restored row-count equality
  invalid foreign-key constraint inventory
  lightweight SQLAlchemy application connection
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
        --skip-backup-verify)
            SKIP_BACKUP_VERIFY="true"
            shift
            ;;
        --skip-app-check)
            SKIP_APP_CHECK="true"
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
[[ -n "$DATABASE" ]] || napa_fail "--database is required."

MANIFEST_FILE="$BACKUP_DIR/manifest.txt"
ROW_COUNTS_FILE="$BACKUP_DIR/row_counts.csv"

require_backup_baseline_files() {
    [[ -d "$BACKUP_DIR" ]] || napa_fail "Backup directory does not exist: $BACKUP_DIR"
    [[ -s "$MANIFEST_FILE" ]] || napa_fail "manifest.txt is missing or empty: $MANIFEST_FILE"
    [[ -s "$ROW_COUNTS_FILE" ]] || napa_fail "row_counts.csv is missing or empty: $ROW_COUNTS_FILE"
}

table_exists() {
    local schema_name table_name schema_literal table_literal
    schema_name="$1"
    table_name="$2"
    schema_literal="$(napa_quote_sql_literal "$schema_name")"
    table_literal="$(napa_quote_sql_literal "$table_name")"
    [[ "$(napa_psql_quiet "$CONTAINER" "$DATABASE" "$POSTGRES_USER_NAME" -c "
        SELECT 1
        FROM information_schema.tables
        WHERE table_type = 'BASE TABLE'
          AND table_schema = ${schema_literal}
          AND table_name = ${table_literal};
    " | tr -d '[:space:]')" == "1" ]]
}

table_row_count() {
    local schema_name table_name
    schema_name="$1"
    table_name="$2"
    napa_psql_quiet "$CONTAINER" "$DATABASE" "$POSTGRES_USER_NAME" -c "
        SELECT count(*)::text
        FROM $(napa_quote_identifier "$schema_name").$(napa_quote_identifier "$table_name");
    " | tr -d '[:space:]'
}

validate_row_counts() {
    local schema_name table_name expected_count actual_count failures checked
    failures=0
    checked=0

    while IFS=, read -r schema_name table_name expected_count; do
        [[ "$schema_name" != "schema" ]] || continue
        [[ -n "${schema_name:-}" && -n "${table_name:-}" && -n "${expected_count:-}" ]] || continue

        if ! table_exists "$schema_name" "$table_name"; then
            printf 'FAIL %-40s source=%s restored=MISSING\n' "${schema_name}.${table_name}" "$expected_count"
            failures=$((failures + 1))
            continue
        fi

        actual_count="$(table_row_count "$schema_name" "$table_name")"
        if [[ "$actual_count" == "$expected_count" ]]; then
            printf 'PASS %-40s source=%s restored=%s\n' "${schema_name}.${table_name}" "$expected_count" "$actual_count"
        else
            printf 'FAIL %-40s source=%s restored=%s\n' "${schema_name}.${table_name}" "$expected_count" "$actual_count"
            failures=$((failures + 1))
        fi
        checked=$((checked + 1))
    done < "$ROW_COUNTS_FILE"

    [[ "$checked" -gt 0 ]] || napa_fail "No row-count entries were checked."
    [[ "$failures" -eq 0 ]] || napa_fail "Row-count validation failed for $failures table(s)."
}

validate_schema_inventory() {
    local expected_schema_count restored_schema_count restored_table_count
    expected_schema_count="$(
        awk -F, 'NR > 1 && $1 != "" { seen[$1]=1 } END { print length(seen) }' "$ROW_COUNTS_FILE"
    )"
    restored_schema_count="$(
        napa_psql_quiet "$CONTAINER" "$DATABASE" "$POSTGRES_USER_NAME" -c "
            SELECT count(DISTINCT table_schema)::text
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
              AND table_schema NOT IN ('pg_catalog', 'information_schema')
              AND table_schema NOT LIKE 'pg_toast%';
        " | tr -d '[:space:]'
    )"
    restored_table_count="$(
        napa_psql_quiet "$CONTAINER" "$DATABASE" "$POSTGRES_USER_NAME" -c "
            SELECT count(*)::text
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
              AND table_schema NOT IN ('pg_catalog', 'information_schema')
              AND table_schema NOT LIKE 'pg_toast%';
        " | tr -d '[:space:]'
    )"

    napa_log "Expected schema count from backup: $expected_schema_count"
    napa_log "Restored schema count: $restored_schema_count"
    napa_log "Restored application table count: $restored_table_count"

    [[ "$restored_table_count" -ge "$(($(wc -l < "$ROW_COUNTS_FILE") - 1))" ]] || napa_fail "Restored table inventory is smaller than row_counts.csv baseline."
}

validate_constraints() {
    local invalid_fk_count
    invalid_fk_count="$(
        napa_psql_quiet "$CONTAINER" "$DATABASE" "$POSTGRES_USER_NAME" -c "
            SELECT count(*)::text
            FROM pg_constraint
            WHERE contype = 'f'
              AND NOT convalidated;
        " | tr -d '[:space:]'
    )"

    [[ "$invalid_fk_count" == "0" ]] || napa_fail "Restored database has $invalid_fk_count unvalidated foreign-key constraint(s)."
    napa_log "Foreign-key constraint validation state: PASS"
}

select_python() {
    if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
        printf '%s\n' "$ROOT_DIR/.venv/bin/python"
        return
    fi
    if [[ -x "$ROOT_DIR/backend/venv/bin/python" ]]; then
        printf '%s\n' "$ROOT_DIR/backend/venv/bin/python"
        return
    fi
    if command -v python3 >/dev/null 2>&1; then
        command -v python3
        return
    fi
    napa_fail "No Python interpreter found for application connectivity check."
}

application_database_url() {
    "$PYTHON_BIN" - "$DATABASE" "$POSTGRES_HOST_NAME" "$POSTGRES_PORT_VALUE" "$ROOT_DIR/backend" <<'PY'
import sys
from os import environ
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

backend_dir = Path(sys.argv[4])
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.core.config import DEFAULT_DATABASE_URL  # noqa: E402

database, host, port = sys.argv[1:4]
base_url = environ.get("DATABASE_URL") or DEFAULT_DATABASE_URL
parts = urlsplit(base_url)
path = "/" + database

netloc = parts.netloc
userinfo = ""
hostport = netloc
if "@" in netloc:
    userinfo, hostport = netloc.rsplit("@", 1)
    userinfo = userinfo + "@"

if host:
    hostport = host
    if port:
        hostport = f"{hostport}:{port}"

print(urlunsplit((parts.scheme, userinfo + hostport, path, parts.query, parts.fragment)))
PY
}

validate_application_connectivity() {
    local database_url
    PYTHON_BIN="$(select_python)"
    database_url="$(application_database_url)"

    napa_log "Checking application SQLAlchemy connectivity..."
    (
        cd "$ROOT_DIR/backend"
        DATABASE_URL="$database_url" "$PYTHON_BIN" - <<'PY'
from sqlalchemy import text

from app.db.session import create_database_engine

engine = create_database_engine(echo=False)
with engine.connect() as conn:
    value = conn.execute(text("SELECT 1")).scalar_one()
    if value != 1:
        raise SystemExit("database connectivity probe returned unexpected result")
print("application_connectivity=PASS")
PY
    ) >/dev/null
}

napa_require_project_root
napa_require_command awk
napa_require_command tr
napa_require_command wc

napa_log "Backup directory: $BACKUP_DIR"
napa_log "Database: $DATABASE"
napa_log "Container: $CONTAINER"

require_backup_baseline_files

if [[ "$SKIP_BACKUP_VERIFY" != "true" ]]; then
    napa_log "Verifying backup package..."
    "$ROOT_DIR/scripts/verify_database_backup.sh" \
        --backup-dir "$BACKUP_DIR" \
        --container "$CONTAINER"
else
    napa_warn "Skipping full backup package verification."
fi

napa_log "Checking restored database availability..."
napa_require_docker
napa_require_running_container "$CONTAINER"
napa_require_pg_ready "$CONTAINER" "$DATABASE" "$POSTGRES_USER_NAME"
napa_require_database_exists "$CONTAINER" "$DATABASE" "$POSTGRES_USER_NAME"

napa_log "Checking restored object inventory..."
validate_schema_inventory

napa_log "Comparing source and restored row counts..."
validate_row_counts

napa_log "Checking foreign-key constraint validation state..."
validate_constraints

if [[ "$SKIP_APP_CHECK" != "true" ]]; then
    validate_application_connectivity
    napa_log "Application connectivity: PASS"
else
    napa_warn "Skipping application connectivity check."
fi

napa_log "NAPA database migration validation PASSED."
napa_log "Database is ready for classroom tournament use: $DATABASE"
