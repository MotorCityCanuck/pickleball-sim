#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
AUDIT_SCRIPT="$BACKEND_DIR/scripts/run_realism_audit.py"

usage() {
    cat <<'EOF'
Usage: ./scripts/run_realism_audits.sh [audit options]

Wrapper for the standalone realism audit runner.

Examples:
  ./scripts/run_realism_audits.sh --list-queries
  ./scripts/run_realism_audits.sh
  ./scripts/run_realism_audits.sh \
    --query player_age_distribution \
    --query club_fill_ratio_outliers \
    --query weekend_match_share

Notes:
  - The audit always uses the latest generation run and the latest batch within that run.
  - Historical run or batch targeting is intentionally disabled.
EOF
}

fail() {
    printf '[run-realism-audits] ERROR: %s\n' "$*" >&2
    exit 1
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    usage
    exit 0
fi

[[ -x "$VENV_PYTHON" ]] || fail "Expected virtualenv interpreter at $VENV_PYTHON"
[[ -f "$AUDIT_SCRIPT" ]] || fail "Audit runner not found at $AUDIT_SCRIPT"

exec "$VENV_PYTHON" "$AUDIT_SCRIPT" "$@"
