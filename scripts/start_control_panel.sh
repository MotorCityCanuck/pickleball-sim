#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    VENV_PYTHON="$ROOT_DIR/.venv/bin/python"
else
    VENV_PYTHON="$BACKEND_DIR/venv/bin/python"
fi
HOST="0.0.0.0"
PORT="8000"
OPEN_BROWSER="true"
RELOAD="false"
SERVER_PID=""
WORKER_PID=""

usage() {
    cat <<'EOF'
Usage: ./scripts/start_control_panel.sh [options]

Starts the local Postgres container, runs the FastAPI control panel with the
project virtualenv, starts the durable worker, waits for the page to respond,
and opens /control.

Options:
  --host <host>       Bind host for uvicorn. Default: 0.0.0.0
  --port <port>       Bind port for uvicorn. Default: 8000
  --no-browser        Do not open the browser automatically
  --reload            Enable uvicorn --reload for UI-only development.
                      Do not use reload while running background jobs.
  --no-reload         Explicitly disable uvicorn --reload. This is the default.
  --help              Show this help text
EOF
}

log() {
    printf '[start-control-panel] %s\n' "$*"
}

fail() {
    printf '[start-control-panel] ERROR: %s\n' "$*" >&2
    exit 1
}

cleanup() {
    local exit_code
    exit_code=$?
    if [[ -n "$WORKER_PID" ]] && kill -0 "$WORKER_PID" >/dev/null 2>&1; then
        kill "$WORKER_PID" >/dev/null 2>&1 || true
        wait "$WORKER_PID" >/dev/null 2>&1 || true
    fi
    if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" >/dev/null 2>&1; then
        kill "$SERVER_PID" >/dev/null 2>&1 || true
        wait "$SERVER_PID" >/dev/null 2>&1 || true
    fi
    exit "$exit_code"
}

select_compose_cmd() {
    if docker compose version >/dev/null 2>&1; then
        echo "docker compose"
        return
    fi
    if command -v docker-compose >/dev/null 2>&1; then
        echo "docker-compose"
        return
    fi
    fail "Neither 'docker compose' nor 'docker-compose' is available."
}

wait_for_postgres() {
    local attempts
    attempts=30
    for ((i = 1; i <= attempts; i++)); do
        if docker exec pickleball-postgres pg_isready -U postgres -d pickleball >/dev/null 2>&1; then
            log "Postgres is ready."
            return
        fi
        sleep 1
    done
    fail "Postgres did not become ready within ${attempts}s."
}

wait_for_app() {
    local url attempts
    url="$1"
    attempts=60
    for ((i = 1; i <= attempts; i++)); do
        if ! kill -0 "$SERVER_PID" >/dev/null 2>&1; then
            wait "$SERVER_PID" || true
            fail "The FastAPI server exited before becoming ready."
        fi

        if "$VENV_PYTHON" - <<PY >/dev/null 2>&1
from urllib.request import urlopen
urlopen("$url", timeout=1)
PY
        then
            log "Control panel is responding at $url"
            return
        fi
        sleep 1
    done
    fail "The control panel did not become ready within ${attempts}s."
}

open_browser() {
    local url
    url="$1"

    if [[ "$OPEN_BROWSER" != "true" ]]; then
        return
    fi

    if command -v wslview >/dev/null 2>&1; then
        wslview "$url" >/dev/null 2>&1 &
        return
    fi
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$url" >/dev/null 2>&1 &
        return
    fi
    if command -v open >/dev/null 2>&1; then
        open "$url" >/dev/null 2>&1 &
        return
    fi
    if command -v python3 >/dev/null 2>&1; then
        python3 -m webbrowser "$url" >/dev/null 2>&1 &
        return
    fi

    log "No supported browser opener found. Open $url manually."
}

find_existing_server_pids() {
    pgrep -f "app.main:app.*--port ${PORT}" || true
}

find_existing_worker_pids() {
    pgrep -f "backend/scripts/run_background_worker.py" || true
}

stop_pids() {
    local label pids wait_seconds check_fn
    label="$1"
    pids="$2"
    wait_seconds="$3"
    check_fn="$4"

    if [[ -z "$pids" ]]; then
        return 1
    fi

    log "Stopping existing ${label}..."
    while IFS= read -r pid; do
        [[ -n "$pid" ]] || continue
        kill "$pid" >/dev/null 2>&1 || true
    done <<< "$pids"

    for _ in $(seq 1 "$wait_seconds"); do
        if ! "$check_fn"; then
            return 0
        fi
        sleep 1
    done

    while IFS= read -r pid; do
        [[ -n "$pid" ]] || continue
        kill -9 "$pid" >/dev/null 2>&1 || true
    done <<< "$pids"
    sleep 1

    if "$check_fn"; then
        fail "Existing ${label} could not be stopped cleanly."
    fi
    return 0
}

have_existing_server_pids() {
    [[ -n "$(find_existing_server_pids)" ]]
}

have_existing_worker_pids() {
    [[ -n "$(find_existing_worker_pids)" ]]
}

stop_existing_server() {
    local pids
    pids="$(find_existing_server_pids)"
    stop_pids "control panel server on port ${PORT}" "$pids" 10 port_in_use
}

stop_existing_worker() {
    local pids
    pids="$(find_existing_worker_pids)"
    stop_pids "durable background worker" "$pids" 10 have_existing_worker_pids
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --host)
            [[ $# -ge 2 ]] || fail "--host requires a value."
            HOST="$2"
            shift 2
            ;;
        --port)
            [[ $# -ge 2 ]] || fail "--port requires a value."
            PORT="$2"
            shift 2
            ;;
        --no-browser)
            OPEN_BROWSER="false"
            shift
            ;;
        --reload)
            RELOAD="true"
            shift
            ;;
        --no-reload)
            RELOAD="false"
            shift
            ;;
        --help)
            usage
            exit 0
            ;;
        *)
            fail "Unknown argument: $1"
            ;;
    esac
done

command -v docker >/dev/null 2>&1 || fail "'docker' is required."
[[ -f "$ROOT_DIR/compose.yaml" ]] || fail "compose.yaml not found in project root."
[[ -x "$VENV_PYTHON" ]] || fail "Expected virtualenv interpreter at $VENV_PYTHON"

COMPOSE_CMD="$(select_compose_cmd)"
APP_URL="http://127.0.0.1:${PORT}/control"

trap cleanup EXIT INT TERM

url_responds() {
    local url
    url="$1"
    "$VENV_PYTHON" - <<PY >/dev/null 2>&1
from urllib.request import urlopen
urlopen("$url", timeout=1)
PY
}

port_in_use() {
    "$VENV_PYTHON" - <<PY >/dev/null 2>&1
import socket

sock = socket.socket()
sock.settimeout(1)
try:
    sock.connect(("127.0.0.1", int("$PORT")))
except OSError:
    raise SystemExit(1)
finally:
    sock.close()
PY
}

log "Starting Postgres container..."
(cd "$ROOT_DIR" && $COMPOSE_CMD up -d postgres)
wait_for_postgres

log "Checking backend dependencies in the virtualenv..."
"$VENV_PYTHON" -c "import duckdb, fastapi, jinja2, multipart, pyarrow, starlette, uvicorn"

stop_existing_worker || true

if port_in_use; then
    if url_responds "$APP_URL"; then
        stop_existing_server || fail "A control panel is responding at $APP_URL, but its process could not be identified for restart."
    fi
    fail "Port ${PORT} is already in use by another process. Stop it or rerun with --port <port>."
fi

if [[ "$RELOAD" == "true" ]]; then
    log "Uvicorn reload is enabled. The durable worker will still be restarted, but avoid running in-process generation/export/compare background jobs in this mode."
    RELOAD_ARGS=(--reload --reload-dir "$BACKEND_DIR")
else
    RELOAD_ARGS=()
fi

log "Starting durable background worker..."
"$VENV_PYTHON" "$BACKEND_DIR/scripts/run_background_worker.py" \
    --queues realism_audit &
WORKER_PID=$!

log "Starting FastAPI control panel on ${HOST}:${PORT}..."
"$VENV_PYTHON" -m uvicorn app.main:app \
    --app-dir "$BACKEND_DIR" \
    --host "$HOST" \
    --port "$PORT" \
    "${RELOAD_ARGS[@]}" &
SERVER_PID=$!

wait_for_app "$APP_URL"
open_browser "$APP_URL"

log "Control panel and durable worker are running. Press Ctrl+C to stop both."
log "Postgres will continue running in Docker until you stop it."

wait "$SERVER_PID"
