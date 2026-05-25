#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# Load env
if [ -f .env ]; then
  set -a; source .env; set +a
fi

# Activate project venv
if [ -f "$ROOT/.venv/bin/activate" ]; then
  source "$ROOT/.venv/bin/activate"
fi

# Ensure DAGSTER_HOME exists
mkdir -p "${DAGSTER_HOME:-$ROOT/.dagster_home}"

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[start]${NC} $1"; }
warn() { echo -e "${YELLOW}[start]${NC} $1"; }
err()  { echo -e "${RED}[start]${NC} $1"; }

# Track background PIDs for cleanup
PIDS=()
LOCAL_CLICKHOUSE_STARTED=0
cleanup() {
  echo
  log "Shutting down..."
  # "${PIDS[@]:-}" plus the guard keeps cleanup safe under `set -u` on macOS's
  # stock Bash 3.2, where expanding an empty array reads as an unbound variable.
  for pid in "${PIDS[@]:-}"; do
    [ -n "$pid" ] || continue
    kill "$pid" 2>/dev/null && wait "$pid" 2>/dev/null || true
  done
  if [ "$LOCAL_CLICKHOUSE_STARTED" = "1" ]; then
    "$ROOT/scripts/clickhouse-local.sh" stop || true
  fi
  log "Done."
}
trap cleanup EXIT INT TERM

# ---------- 1. ClickHouse ----------
# Default per platform: the docker-free native binary on Linux (the only OS its
# auto-download supports), the ClickHouse container everywhere else — so a fresh
# clone runs on macOS and Windows too. Override with CLICKSPOT_CLICKHOUSE_MODE.
if [ -n "${CLICKSPOT_CLICKHOUSE_MODE:-}" ]; then
  CLICKHOUSE_MODE="$CLICKSPOT_CLICKHOUSE_MODE"
elif [ "$(uname -s)" = "Linux" ]; then
  CLICKHOUSE_MODE="local"
else
  CLICKHOUSE_MODE="docker"
fi
log "Starting ClickHouse (${CLICKHOUSE_MODE})..."
case "$CLICKHOUSE_MODE" in
  local)
    if ! curl -sf "http://${CLICKHOUSE_HOST:-localhost}:${CLICKHOUSE_PORT:-8124}/ping" >/dev/null 2>&1; then
      LOCAL_CLICKHOUSE_STARTED=1
    fi
    "$ROOT/scripts/clickhouse-local.sh" start
    ;;
  docker)
    if ! docker info >/dev/null 2>&1; then
      err "Docker isn't running. Start Docker Desktop and retry, or set"
      err "CLICKSPOT_CLICKHOUSE_MODE=external in .env to point at your own ClickHouse."
      exit 1
    fi
    # Only the clickhouse service: start.sh runs FastAPI/Dagster/frontend on the
    # host, so bringing up the full compose stack would double-bind their ports.
    if docker compose ps --status running clickhouse 2>/dev/null | grep -q clickhouse; then
      log "ClickHouse container already running"
    else
      docker compose up -d clickhouse
    fi
    ;;
  external)
    log "Using external ClickHouse at ${CLICKHOUSE_HOST:-localhost}:${CLICKHOUSE_PORT:-8124}"
    ;;
  *)
    err "Unknown CLICKSPOT_CLICKHOUSE_MODE=$CLICKHOUSE_MODE (expected local, docker, or external)"
    exit 1
    ;;
esac

# Wait for ClickHouse to accept connections in every mode.
log "Waiting for ClickHouse..."
for i in $(seq 1 60); do
  if curl -sf "http://${CLICKHOUSE_HOST:-localhost}:${CLICKHOUSE_PORT:-8124}/ping" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
if ! curl -sf "http://${CLICKHOUSE_HOST:-localhost}:${CLICKHOUSE_PORT:-8124}/ping" >/dev/null 2>&1; then
  err "ClickHouse is not reachable at ${CLICKHOUSE_HOST:-localhost}:${CLICKHOUSE_PORT:-8124}"
  exit 1
fi
log "ClickHouse ready on port ${CLICKHOUSE_PORT:-8124}"

# ---------- 2. Init schemas (idempotent) ----------
log "Ensuring ClickHouse schemas..."
python scripts/init_clickhouse.py

# ---------- 2a. Customer config hint (first-run portal setup) ----------
if [ ! -f "$HOME/.clickspot/customer.json" ]; then
  warn "No ~/.clickspot/customer.json found."
  warn "On first run, the LLM will produce generic SQL without portal-specific filters."
  warn "After bronze+silver load, run: python -m app.customer.onboarding"
  warn "to walk through pipelines / main pipeline / canonical revenue column."
fi

# ---------- 3. FastAPI ----------
log "Starting FastAPI on :8192..."
uvicorn app.main:app --host 0.0.0.0 --port 8192 --reload --log-level info &
PIDS+=($!)

# ---------- 4. Dagster ----------
log "Starting Dagster on :8194..."
dagster dev -p 8194 &
PIDS+=($!)

# ---------- 5. Frontend dev server ----------
log "Starting frontend on :8193..."
cd frontend
npm install --silent
npx vite --port 8193 &
PIDS+=($!)
cd "$ROOT"

echo
log "All services running:"
log "  ClickHouse  → http://localhost:${CLICKHOUSE_PORT:-8124}"
log "  FastAPI     → http://localhost:8192"
log "  Dagster     → http://localhost:8194"
log "  Frontend    → http://localhost:8193"
echo
log "Press Ctrl+C to stop all services"

# Wait for any child to exit
wait
