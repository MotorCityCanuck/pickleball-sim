#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SQL_FILE="$ROOT_DIR/sql/generation_runtime_metrics_report.sql"
DEFAULT_DATABASE_URL="postgresql://postgres:postgres@localhost:5432/pickleball"
POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-pickleball-postgres}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-pickleball}"

RUN_ID=""
DATABASE_URL_ARG="${DATABASE_URL:-$DEFAULT_DATABASE_URL}"

usage() {
    cat <<'EOF'
Usage: ./scripts/run_generation_metrics_report.sh [options]

Runs the generation runtime instrumentation report with psql.

Options:
  --run-id ID          Analyze a specific generation_runs.id.
                       Defaults to the latest run with runtime metrics.
  --database-url URL   Override DATABASE_URL for this invocation.
  -h, --help           Show this help text.

Examples:
  ./scripts/run_generation_metrics_report.sh
  ./scripts/run_generation_metrics_report.sh --run-id 16
  DATABASE_URL=postgresql://postgres:postgres@localhost:5432/pickleball \
    ./scripts/run_generation_metrics_report.sh
EOF
}

fail() {
    printf '[generation-metrics-report] ERROR: %s\n' "$*" >&2
    exit 1
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --run-id)
            [[ $# -ge 2 ]] || fail "--run-id requires a value"
            RUN_ID="$2"
            shift 2
            ;;
        --database-url)
            [[ $# -ge 2 ]] || fail "--database-url requires a value"
            DATABASE_URL_ARG="$2"
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            fail "Unknown option: $1"
            ;;
    esac
done

[[ -f "$SQL_FILE" ]] || fail "SQL report not found at $SQL_FILE"

if command -v psql >/dev/null 2>&1; then
    exec psql "$DATABASE_URL_ARG" \
        --set=ON_ERROR_STOP=1 \
        --set=run_id="$RUN_ID" \
        --file="$SQL_FILE"
fi

if command -v docker >/dev/null 2>&1 \
    && docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$POSTGRES_CONTAINER"; then
    exec docker exec -i "$POSTGRES_CONTAINER" \
        psql \
        --username="$POSTGRES_USER" \
        --dbname="$POSTGRES_DB" \
        --set=ON_ERROR_STOP=1 \
        --set=run_id="$RUN_ID" \
        < "$SQL_FILE"
fi

fail "psql is not installed and Docker container '$POSTGRES_CONTAINER' is not running"
