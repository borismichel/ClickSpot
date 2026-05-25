#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

START_AFTER=0
SEED_DEMO=0
INSTALL_MODE="${CLICKSPOT_INSTALL_MODE:-locked}"

usage() {
  cat <<'USAGE'
Usage: scripts/bootstrap.sh [--start] [--seed] [--editable]

Bootstraps a Docker-free local ClickSpot checkout:
  - creates .venv
  - installs Python dependencies
  - creates .env from .env.example if missing
  - installs the local ClickHouse binary/config under .clickhouse/
  - installs frontend npm dependencies

Options:
  --start     Run ./start.sh after bootstrapping
  --seed      Start ClickHouse and load demo-data/clickspot-demo-data.csv
  --editable  Resolve Python dependencies from pyproject.toml instead of requirements.lock
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --start) START_AFTER=1 ;;
    --seed) SEED_DEMO=1 ;;
    --editable) INSTALL_MODE="editable" ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[bootstrap]${NC} $1"; }
warn() { echo -e "${YELLOW}[bootstrap]${NC} $1"; }
die()  { echo "[bootstrap] $1" >&2; exit 1; }

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

log "Checking prerequisites..."
require_command python3
require_command node
require_command npm
require_command curl
require_command tar

python3 - <<'PY' || die "Python 3.10+ is required"
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY

node - <<'JS' || die "Node.js 20.19+ is required"
const [major, minor] = process.versions.node.split(".").map(Number);
process.exit(major > 20 || (major === 20 && minor >= 19) ? 0 : 1);
JS

log "Creating Python virtualenv..."
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip

if [ "$INSTALL_MODE" = "locked" ] && [ -f requirements.lock ]; then
  log "Installing Python dependencies from requirements.lock..."
  # --no-deps: the lockfile is the full pinned closure; don't re-resolve against
  # PyPI (keeps locked installs reproducible — see Dockerfile / CLI-56).
  pip install --no-deps -r requirements.lock
  pip install -e . --no-deps
else
  log "Installing Python dependencies from pyproject.toml..."
  pip install -e ".[dev]"
fi

if [ ! -f .env ]; then
  log "Creating .env from .env.example..."
  cp .env.example .env
else
  warn ".env already exists; leaving it unchanged"
fi

log "Installing local ClickHouse runtime..."
CLICKHOUSE_HOST="${CLICKHOUSE_HOST:-localhost}" \
  CLICKHOUSE_PORT="${CLICKHOUSE_PORT:-8124}" \
  CLICKHOUSE_USER="${CLICKHOUSE_USER:-hs2ch}" \
  CLICKHOUSE_PASSWORD="${CLICKHOUSE_PASSWORD:-hs2ch}" \
  scripts/clickhouse-local.sh ensure

log "Installing frontend dependencies..."
if [ -f frontend/package-lock.json ]; then
  npm --prefix frontend ci
else
  npm --prefix frontend install
fi

if [ "$SEED_DEMO" = "1" ]; then
  log "Starting ClickHouse and loading demo data..."
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
  scripts/clickhouse-local.sh start
  python scripts/init_clickhouse.py
  python scripts/seed.py
fi

log "Bootstrap complete."
if [ "$START_AFTER" = "1" ]; then
  exec ./start.sh
fi

cat <<'NEXT'

Next:
  ./start.sh

For an offline demo warehouse:
  ./scripts/bootstrap.sh --seed
NEXT
