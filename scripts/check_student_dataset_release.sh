#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SQL_SCRIPT="$ROOT_DIR/scripts/student_dataset_duckdb_quality_check.sql"
if [[ -x "$ROOT_DIR/.venv/bin/duckdb" ]]; then
    RUN_MODE="duckdb-cli"
    DUCKDB_BIN="$ROOT_DIR/.venv/bin/duckdb"
elif [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    RUN_MODE="python-module"
    PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
else
    RUN_MODE="duckdb-cli"
    DUCKDB_BIN="duckdb"
fi

usage() {
    cat <<'EOF'
Usage: ./scripts/check_student_dataset_release.sh <release_dir>

Runs DuckDB-only completeness and integrity checks against one exported
student dataset release folder.

Arguments:
  release_dir    Path to one concrete release folder containing manifest.json
                 and the student dataset Parquet files.

Example:
  ./scripts/check_student_dataset_release.sh \
    /home/brett/projects/pickleball-sim/data/student_dataset_exports/run_32_student_dataset_publish_smoke/run_32_student_dataset_publish_smoke_initial_history
EOF
}

fail() {
    printf '[student-dataset-qc] ERROR: %s\n' "$*" >&2
    exit 1
}

log() {
    printf '[student-dataset-qc] %s\n' "$*"
}

if [[ $# -ne 1 ]]; then
    usage >&2
    exit 1
fi

case "$1" in
    --help|-h)
        usage
        exit 0
        ;;
esac

RELEASE_DIR="$1"

[[ -d "$RELEASE_DIR" ]] || fail "Release directory does not exist: $RELEASE_DIR"
[[ -f "$RELEASE_DIR/manifest.json" ]] || fail "manifest.json not found in: $RELEASE_DIR"
[[ -f "$SQL_SCRIPT" ]] || fail "DuckDB QC SQL script not found: $SQL_SCRIPT"

if [[ "${RUN_MODE:-}" == "python-module" ]]; then
    [[ -x "$PYTHON_BIN" ]] || fail "Python interpreter is not executable: $PYTHON_BIN"
elif [[ "$DUCKDB_BIN" != "duckdb" ]]; then
    [[ -x "$DUCKDB_BIN" ]] || fail "DuckDB binary is not executable: $DUCKDB_BIN"
elif ! command -v duckdb >/dev/null 2>&1; then
    fail "DuckDB runtime not found. Expected $ROOT_DIR/.venv/bin/duckdb, $ROOT_DIR/.venv/bin/python, or duckdb on PATH."
fi

log "Running DuckDB quality checks for $RELEASE_DIR"

if [[ "${RUN_MODE:-}" == "python-module" ]]; then
    RELEASE_DIR="$RELEASE_DIR" SQL_SCRIPT="$SQL_SCRIPT" "$PYTHON_BIN" - <<'PY'
import os
from pathlib import Path

import duckdb

release_dir = os.environ["RELEASE_DIR"]
sql_script = Path(os.environ["SQL_SCRIPT"]).read_text(encoding="utf-8")

connection = duckdb.connect()
escaped_release_dir = release_dir.replace("'", "''")
connection.execute(f"SET VARIABLE release_dir = '{escaped_release_dir}'")
connection.execute(sql_script)
PY
else
    {
        printf "SET VARIABLE release_dir = '%s';\n" "${RELEASE_DIR//\'/\'\'}"
        printf ".read %s\n" "$SQL_SCRIPT"
    } | "$DUCKDB_BIN"
fi
