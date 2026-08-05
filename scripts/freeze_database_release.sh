#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
# shellcheck source=scripts/lib/napa_database_backup_common.sh
source "$ROOT_DIR/scripts/lib/napa_database_backup_common.sh"

RELEASE_LABEL=""
DATABASE="$NAPA_POSTGRES_DB"
CONTAINER="$NAPA_POSTGRES_CONTAINER"
POSTGRES_USER_NAME="$NAPA_POSTGRES_USER"
POSTGRES_HOST_NAME="$NAPA_POSTGRES_HOST"
POSTGRES_PORT_VALUE="$NAPA_POSTGRES_PORT"
OUTPUT_ROOT="$ROOT_DIR/backups"
DEEP_VERIFY="false"
SKIP_CERTIFICATION="false"
CERTIFICATION_ARGS=()

usage() {
    cat <<'EOF'
Usage: ./scripts/freeze_database_release.sh <release-label> [options] [-- <certification args>]

Create an instructor-facing frozen NAPA database release package after
certification. The command backs up the selected database, verifies the backup,
and writes FREEZE_MANIFEST.md into the backup package.

Examples:
  ./scripts/freeze_database_release.sh 250k --database pickleball --deep
  ./scripts/freeze_database_release.sh 250k --output-dir /mnt/d/napa_backups
  ./scripts/freeze_database_release.sh 250k -- --no-save-snapshot

Options:
  --database <name>       Source database to freeze. Default: POSTGRES_DB or pickleball
  --container <name>      PostgreSQL Docker container. Default: POSTGRES_CONTAINER or pickleball-postgres
  --user <name>           PostgreSQL user. Default: POSTGRES_USER or postgres
  --host <host>           Host for certification DATABASE_URL. Default: POSTGRES_HOST or localhost
  --port <port>           Port for certification DATABASE_URL. Default: POSTGRES_PORT or 5432
  --output-dir <path>     Directory under which the timestamped backup directory is created.
                          Default: ./backups
  --deep                  Run deep restore verification after backup verification
  --skip-certification    Skip release certification. Intended only for local script
                          smoke tests, not production freezes.
  --help                  Show this help text

Arguments after -- are passed to release certification.
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
        --output-dir)
            [[ $# -ge 2 ]] || napa_fail "--output-dir requires a value."
            OUTPUT_ROOT="$2"
            shift 2
            ;;
        --deep)
            DEEP_VERIFY="true"
            shift
            ;;
        --skip-certification)
            SKIP_CERTIFICATION="true"
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        --)
            shift
            CERTIFICATION_ARGS=("$@")
            break
            ;;
        --*)
            napa_fail "Unknown argument: $1"
            ;;
        *)
            if [[ -z "$RELEASE_LABEL" ]]; then
                RELEASE_LABEL="$1"
                shift
            else
                napa_fail "Unexpected positional argument: $1"
            fi
            ;;
    esac
done

[[ -n "$RELEASE_LABEL" ]] || napa_fail "A release label is required, for example: 250k."

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
    napa_fail "No Python interpreter found for release certification."
}

application_database_url() {
    "$PYTHON_BIN" - "$DATABASE" "$POSTGRES_HOST_NAME" "$POSTGRES_PORT_VALUE" "$BACKEND_DIR" <<'PY'
import sys
from os import environ
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

database, host, port, backend_dir = sys.argv[1:5]
backend_path = Path(backend_dir)
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.core.config import DEFAULT_DATABASE_URL  # noqa: E402

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

run_certification() {
    local certification_log database_url
    certification_log="$1"
    database_url="$(application_database_url)"

    if [[ "$SKIP_CERTIFICATION" == "true" ]]; then
        napa_warn "Skipping release certification by explicit request. Do not use this for production freezes."
        printf 'certification_status=SKIPPED\n' > "$certification_log"
        return
    fi

    [[ -f "$BACKEND_DIR/scripts/run_release_certification.py" ]] || napa_fail "Release certification runner not found."

    napa_log "Running release certification..."
    if ! (
        cd "$BACKEND_DIR"
        DATABASE_URL="$database_url" "$PYTHON_BIN" "$BACKEND_DIR/scripts/run_release_certification.py" "${CERTIFICATION_ARGS[@]}"
    ) > "$certification_log" 2>&1; then
        napa_fail "Release certification failed. Log retained at: $certification_log"
    fi
}

run_backup() {
    local backup_output backup_dir
    backup_output="$(
        "$ROOT_DIR/scripts/backup_database.sh" \
            --database "$DATABASE" \
            --container "$CONTAINER" \
            --user "$POSTGRES_USER_NAME" \
            --output-dir "$OUTPUT_ROOT"
    )"
    printf '%s\n' "$backup_output"
    backup_dir="$(printf '%s\n' "$backup_output" | awk -F'Backup package: ' '/Backup package:/ { print $2 }' | tail -n 1)"
    [[ -n "$backup_dir" ]] || napa_fail "Could not determine backup package path from backup output."
    [[ -d "$backup_dir" ]] || napa_fail "Backup package directory was not created: $backup_dir"
}

verify_backup() {
    local backup_dir
    backup_dir="$1"
    if [[ "$DEEP_VERIFY" == "true" ]]; then
        "$ROOT_DIR/scripts/verify_database_backup.sh" \
            --backup-dir "$backup_dir" \
            --database "$DATABASE" \
            --container "$CONTAINER" \
            --user "$POSTGRES_USER_NAME" \
            --deep
    else
        "$ROOT_DIR/scripts/verify_database_backup.sh" \
            --backup-dir "$backup_dir" \
            --database "$DATABASE" \
            --container "$CONTAINER" \
            --user "$POSTGRES_USER_NAME"
    fi
}

backup_archive_sha256() {
    local backup_dir
    backup_dir="$1"
    awk '$2 == "database.dump" { print $1; found=1; exit } END { if (!found) exit 1 }' "$backup_dir/SHA256SUMS" 2>/dev/null || printf '%s\n' UNKNOWN
}

write_freeze_manifest() {
    local backup_dir certification_log freeze_manifest postgres_version docker_image
    local git_commit git_branch backup_sha verification_status deep_status certification_status
    backup_dir="$1"
    certification_log="$2"
    freeze_manifest="$backup_dir/FREEZE_MANIFEST.md"

    postgres_version="$(napa_manifest_value "$backup_dir/manifest.txt" postgres_version 2>/dev/null || printf '%s\n' UNKNOWN)"
    docker_image="$(napa_manifest_value "$backup_dir/manifest.txt" docker_image 2>/dev/null || printf '%s\n' UNKNOWN)"
    verification_status="$(napa_manifest_value "$backup_dir/manifest.txt" verification_status 2>/dev/null || printf '%s\n' UNKNOWN)"
    git_commit="$(napa_manifest_value "$backup_dir/manifest.txt" git_commit 2>/dev/null || napa_git_commit)"
    git_branch="$(napa_manifest_value "$backup_dir/manifest.txt" git_branch 2>/dev/null || napa_git_branch)"
    backup_sha="$(backup_archive_sha256 "$backup_dir")"

    if [[ "$SKIP_CERTIFICATION" == "true" ]]; then
        certification_status="SKIPPED"
    else
        certification_status="PASSED"
    fi

    if [[ "$DEEP_VERIFY" == "true" ]]; then
        deep_status="PASSED"
    else
        deep_status="NOT_RUN"
    fi

    {
        printf '# NAPA Production Database Freeze\n\n'
        printf 'Release: %s\n' "$RELEASE_LABEL"
        printf 'Freeze Date: %s\n' "$(napa_timestamp_utc)"
        printf 'Database: %s\n' "$DATABASE"
        printf 'Backup Package: %s\n' "$backup_dir"
        printf 'PostgreSQL Version: %s\n' "$postgres_version"
        printf 'Docker Image: %s\n' "$docker_image"
        printf 'Git Commit: %s\n' "$git_commit"
        printf 'Git Branch: %s\n' "$git_branch"
        printf 'Git Tag: %s\n' "$(git -C "$ROOT_DIR" describe --tags --exact-match 2>/dev/null || printf '%s\n' UNKNOWN)"
        printf 'Certification Result: %s\n' "$certification_status"
        printf 'Certification Log: %s\n' "$(basename "$certification_log")"
        printf 'Backup Verification: %s\n' "$verification_status"
        printf 'Deep Restore Verification: %s\n' "$deep_status"
        printf 'Backup SHA-256: %s\n' "$backup_sha"
        printf 'Instructor Notes: \n'
    } > "$freeze_manifest"
}

napa_require_project_root
napa_require_docker
napa_require_running_container "$CONTAINER"
napa_require_pg_ready "$CONTAINER" "$DATABASE" "$POSTGRES_USER_NAME"
napa_require_database_exists "$CONTAINER" "$DATABASE" "$POSTGRES_USER_NAME"
[[ -x "$ROOT_DIR/scripts/backup_database.sh" ]] || napa_fail "backup_database.sh is missing or not executable."
[[ -x "$ROOT_DIR/scripts/verify_database_backup.sh" ]] || napa_fail "verify_database_backup.sh is missing or not executable."

PYTHON_BIN="$(select_python)"

napa_log "Release: $RELEASE_LABEL"
napa_log "Database: $DATABASE"
napa_log "Container: $CONTAINER"
napa_log "Output root: $OUTPUT_ROOT"

PRE_FREEZE_DIR="$(mktemp -d /tmp/napa_freeze.XXXXXX)"
CERTIFICATION_LOG="$PRE_FREEZE_DIR/release_certification.log"

run_certification "$CERTIFICATION_LOG"
napa_log "Release certification completed."

napa_log "Creating verified database backup..."
BACKUP_RUN_OUTPUT="$(run_backup)"
printf '%s\n' "$BACKUP_RUN_OUTPUT"
BACKUP_DIR="$(printf '%s\n' "$BACKUP_RUN_OUTPUT" | awk -F'Backup package: ' '/Backup package:/ { print $2 }' | tail -n 1)"
[[ -n "$BACKUP_DIR" ]] || napa_fail "Could not determine backup package path from backup output."

napa_log "Verifying backup package..."
verify_backup "$BACKUP_DIR"

cp "$CERTIFICATION_LOG" "$BACKUP_DIR/release_certification.log"
write_freeze_manifest "$BACKUP_DIR" "$BACKUP_DIR/release_certification.log"
rm -rf "$PRE_FREEZE_DIR"

napa_log "NAPA ${RELEASE_LABEL} database freeze completed successfully."
napa_log "Backup: $BACKUP_DIR"
napa_log "Database archive: VERIFIED"
napa_log "Checksums: VERIFIED"
napa_log "Row counts: CAPTURED"
napa_log "Certification: $(if [[ "$SKIP_CERTIFICATION" == "true" ]]; then printf 'SKIPPED'; else printf 'PASSED'; fi)"
