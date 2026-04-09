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
cleanup() {
  echo
  log "Shutting down..."
  for pid in "${PIDS[@]}"; do
    kill "$pid" 2>/dev/null && wait "$pid" 2>/dev/null || true
  done
  log "Done."
}
trap cleanup EXIT INT TERM

# ---------- 1. ClickHouse (Docker) ----------
log "Starting ClickHouse..."
if docker compose ps --status running 2>/dev/null | grep -q clickhouse; then
  log "ClickHouse already running"
else
  docker compose up -d
  # Wait for ClickHouse to accept connections
  log "Waiting for ClickHouse..."
  for i in $(seq 1 30); do
    if curl -sf "http://localhost:${CLICKHOUSE_PORT:-8124}/ping" >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  if ! curl -sf "http://localhost:${CLICKHOUSE_PORT:-8124}/ping" >/dev/null 2>&1; then
    err "ClickHouse failed to start"; exit 1
  fi
  log "ClickHouse ready on port ${CLICKHOUSE_PORT:-8124}"
fi

# ---------- 2. Init schemas (idempotent) ----------
log "Ensuring ClickHouse schemas..."
python scripts/init_clickhouse.py

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
