#!/usr/bin/env bash

# Shared helpers for NAPA PostgreSQL backup, verification, restore, and
# classroom migration scripts.
#
# This file is intended to be sourced by executable scripts. It defines common
# defaults and functions, but does not perform Docker/PostgreSQL operations at
# source time.

set -euo pipefail

NAPA_DB_COMMON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAPA_ROOT_DIR="$(cd "${NAPA_DB_COMMON_DIR}/../.." && pwd)"

NAPA_DEFAULT_POSTGRES_CONTAINER="pickleball-postgres"
NAPA_DEFAULT_POSTGRES_USER="postgres"
NAPA_DEFAULT_POSTGRES_DB="pickleball"
NAPA_DEFAULT_POSTGRES_HOST="localhost"
NAPA_DEFAULT_POSTGRES_PORT="5432"

NAPA_POSTGRES_CONTAINER="${POSTGRES_CONTAINER:-$NAPA_DEFAULT_POSTGRES_CONTAINER}"
NAPA_POSTGRES_USER="${POSTGRES_USER:-$NAPA_DEFAULT_POSTGRES_USER}"
NAPA_POSTGRES_DB="${POSTGRES_DB:-$NAPA_DEFAULT_POSTGRES_DB}"
NAPA_POSTGRES_HOST="${POSTGRES_HOST:-$NAPA_DEFAULT_POSTGRES_HOST}"
NAPA_POSTGRES_PORT="${POSTGRES_PORT:-$NAPA_DEFAULT_POSTGRES_PORT}"

napa_script_name() {
    basename "${0:-napa-db}"
}

napa_log_prefix() {
    local script_name
    script_name="$(napa_script_name)"
    script_name="${script_name%.sh}"
    printf '[%s]' "$script_name"
}

napa_log() {
    printf '%s %s\n' "$(napa_log_prefix)" "$*"
}

napa_warn() {
    printf '%s WARN: %s\n' "$(napa_log_prefix)" "$*" >&2
}

napa_fail() {
    printf '%s ERROR: %s\n' "$(napa_log_prefix)" "$*" >&2
    exit 1
}

napa_require_command() {
    local command_name
    command_name="$1"
    command -v "$command_name" >/dev/null 2>&1 || napa_fail "'$command_name' is required."
}

napa_select_compose_cmd() {
    if docker compose version >/dev/null 2>&1; then
        printf '%s\n' "docker compose"
        return
    fi
    if command -v docker-compose >/dev/null 2>&1; then
        printf '%s\n' "docker-compose"
        return
    fi
    napa_fail "Neither 'docker compose' nor 'docker-compose' is available."
}

napa_require_project_root() {
    [[ -f "$NAPA_ROOT_DIR/compose.yaml" ]] || napa_fail "compose.yaml not found at $NAPA_ROOT_DIR."
}

napa_require_docker() {
    napa_require_command docker
    docker version >/dev/null 2>&1 || napa_fail "Docker is not available. Start Docker Desktop and confirm WSL integration is enabled."
}

napa_container_is_running() {
    local container
    container="$1"
    [[ "$(docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null || true)" == "true" ]]
}

napa_require_running_container() {
    local container
    container="$1"
    napa_container_is_running "$container" || napa_fail "PostgreSQL container '$container' is not running."
}

napa_pg_is_ready() {
    local container database user
    container="$1"
    database="$2"
    user="$3"
    docker exec "$container" pg_isready -U "$user" -d "$database" >/dev/null 2>&1
}

napa_require_pg_ready() {
    local container database user
    container="$1"
    database="$2"
    user="$3"
    napa_pg_is_ready "$container" "$database" "$user" || napa_fail "PostgreSQL is not ready for database '$database' in container '$container'."
}

napa_psql() {
    local container database user
    container="$1"
    database="$2"
    user="$3"
    shift 3
    docker exec "$container" psql -v ON_ERROR_STOP=1 -U "$user" -d "$database" "$@"
}

napa_psql_quiet() {
    local container database user
    container="$1"
    database="$2"
    user="$3"
    shift 3
    napa_psql "$container" "$database" "$user" -X -q -t -A "$@"
}

napa_database_exists() {
    local container database user database_literal
    container="$1"
    database="$2"
    user="$3"
    database_literal="$(napa_quote_sql_literal "$database")"
    [[ "$(napa_psql_quiet "$container" postgres "$user" -c "SELECT 1 FROM pg_database WHERE datname = ${database_literal};" 2>/dev/null | tr -d '[:space:]')" == "1" ]]
}

napa_require_database_exists() {
    local container database user
    container="$1"
    database="$2"
    user="$3"
    napa_database_exists "$container" "$database" "$user" || napa_fail "Database '$database' does not exist in container '$container'."
}

napa_pg_dump() {
    local container database user
    container="$1"
    database="$2"
    user="$3"
    docker exec "$container" pg_dump -U "$user" -d "$database" -Fc
}

napa_pg_dumpall_globals() {
    local container user
    container="$1"
    user="$2"
    docker exec "$container" pg_dumpall -U "$user" --globals-only
}

napa_pg_restore_list() {
    local container
    container="$1"
    docker exec -i "$container" pg_restore --list
}

napa_pg_restore_database() {
    local container database user
    container="$1"
    database="$2"
    user="$3"
    docker exec -i "$container" pg_restore -U "$user" -d "$database" --no-owner --role="$user"
}

napa_timestamp_utc() {
    date -u +"%Y%m%dT%H%M%SZ"
}

napa_timestamp_local_slug() {
    date +"%Y-%m-%d_%H%M%S"
}

napa_sha256_command() {
    if command -v sha256sum >/dev/null 2>&1; then
        printf '%s\n' "sha256sum"
        return
    fi
    if command -v shasum >/dev/null 2>&1; then
        printf '%s\n' "shasum -a 256"
        return
    fi
    napa_fail "Neither 'sha256sum' nor 'shasum' is available."
}

napa_write_sha256sums() {
    local output_file
    output_file="$1"
    shift
    [[ $# -gt 0 ]] || napa_fail "napa_write_sha256sums requires at least one file."

    local checksum_cmd
    checksum_cmd="$(napa_sha256_command)"
    (
        cd "$(dirname "$output_file")"
        for file_path in "$@"; do
            if [[ "$checksum_cmd" == "sha256sum" ]]; then
                sha256sum "$(basename "$file_path")"
            else
                shasum -a 256 "$(basename "$file_path")"
            fi
        done
    ) > "$output_file"
}

napa_verify_sha256sums() {
    local checksums_file checksum_cmd
    checksums_file="$1"
    checksum_cmd="$(napa_sha256_command)"
    (
        cd "$(dirname "$checksums_file")"
        if [[ "$checksum_cmd" == "sha256sum" ]]; then
            sha256sum -c "$(basename "$checksums_file")"
        else
            shasum -a 256 -c "$(basename "$checksums_file")"
        fi
    )
}

napa_git_value() {
    local fallback git_args
    fallback="$1"
    shift
    git_args=("$@")
    (
        cd "$NAPA_ROOT_DIR"
        git "${git_args[@]}" 2>/dev/null
    ) || printf '%s\n' "$fallback"
}

napa_git_commit() {
    napa_git_value "UNKNOWN" rev-parse HEAD
}

napa_git_branch() {
    napa_git_value "UNKNOWN" rev-parse --abbrev-ref HEAD
}

napa_container_image() {
    local container
    container="$1"
    docker inspect -f '{{.Config.Image}}' "$container" 2>/dev/null || printf '%s\n' "UNKNOWN"
}

napa_postgres_version() {
    local container database user
    container="$1"
    database="$2"
    user="$3"
    napa_psql_quiet "$container" "$database" "$user" -c "SHOW server_version;" 2>/dev/null || printf '%s\n' "UNKNOWN"
}

napa_postgres_major_version() {
    local version
    version="$1"
    version="${version%%.*}"
    version="${version%%[^0-9]*}"
    [[ -n "$version" ]] && printf '%s\n' "$version" || printf '%s\n' "UNKNOWN"
}

napa_database_size() {
    local container database user
    container="$1"
    database="$2"
    user="$3"
    napa_psql_quiet "$container" "$database" "$user" -c "SELECT pg_size_pretty(pg_database_size(current_database()));" 2>/dev/null || printf '%s\n' "UNKNOWN"
}

napa_quote_sql_literal() {
    local value
    value="$1"
    value="${value//\'/\'\'}"
    printf "'%s'" "$value"
}

napa_quote_identifier() {
    local value
    value="$1"
    value="${value//\"/\"\"}"
    printf '"%s"' "$value"
}
