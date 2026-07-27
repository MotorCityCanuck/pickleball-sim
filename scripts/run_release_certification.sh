#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
RUNNER_SCRIPT="$BACKEND_DIR/scripts/run_release_certification.py"

usage() {
    cat <<'EOF'
Usage: ./scripts/run_release_certification.sh [certification options]

Wrapper for the phase-1 release certification runner.

Examples:
  ./scripts/run_release_certification.sh --list-queries
  ./scripts/run_release_certification.sh
  ./scripts/run_release_certification.sh \
    --query player_age_distribution \
    --query club_fill_ratio_outliers \
    --query weekend_match_share

Notes:
  - The certification run always uses the latest generation run and the latest batch within that run.
  - Historical run or batch targeting is intentionally disabled.
  - A JSON snapshot is saved by default under data/realism_audit_snapshots/.
  - Use --no-save-snapshot to skip snapshot persistence.
EOF
}

fail() {
    printf '[run-release-certification] ERROR: %s\n' "$*" >&2
    exit 1
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    usage
    exit 0
fi

[[ -x "$VENV_PYTHON" ]] || fail "Expected virtualenv interpreter at $VENV_PYTHON"
[[ -f "$RUNNER_SCRIPT" ]] || fail "Runner not found at $RUNNER_SCRIPT"

exec "$VENV_PYTHON" "$RUNNER_SCRIPT" "$@"
