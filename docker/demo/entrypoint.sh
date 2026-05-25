#!/usr/bin/env bash
# Runtime entrypoint for the all-in-one preloaded demo image. Starts ClickHouse
# (reading the baked warehouse) and the FastAPI backend (serving the built
# frontend) on a single published port. No seeding happens here — the data is
# already in the image.
set -euo pipefail

DATA=/var/lib/clickspot-ch
PORT="${PORT:-8080}"

# The data layer is baked read/written by uid 101; keep ownership sane in case
# the image runs under a remapped user.
chown -R clickhouse:clickhouse "$DATA" /var/log/clickhouse-server 2>/dev/null || true

setpriv --reuid=clickhouse --regid=clickhouse --init-groups \
    clickhouse-server --config-file=/etc/clickhouse-server/config.xml &
CH_PID=$!

shutdown() { kill -TERM "$CH_PID" "${APP_PID:-}" 2>/dev/null || true; }
trap shutdown TERM INT

echo "[clickspot] waiting for ClickHouse..."
for _ in $(seq 1 60); do
    if curl -sf http://localhost:8123/ping >/dev/null 2>&1; then break; fi
    sleep 1
done

cd /app

# The in-app key form PUTs to a settings endpoint that accepts loopback only.
# Docker maps the host's loopback-bound port in via the bridge, so uvicorn sees
# the request from the bridge gateway rather than 127.0.0.1 — trust the private
# bridge range so the form works out of the box. The published port stays
# loopback-bound, so this doesn't expose key writes beyond the host. An operator
# value (e.g. for a custom network) is respected.
export CLICKSPOT_TRUSTED_HOSTS="${CLICKSPOT_TRUSTED_HOSTS:-172.16.0.0/12}"

echo "[clickspot] starting ClickSpot on http://localhost:${PORT}"
echo "[clickspot] clicking works with no key; set ANTHROPIC_API_KEY or OPENAI_API_KEY to enable chat."
/opt/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" &
APP_PID=$!

# Exit (and tear everything down) as soon as either process dies.
wait -n
shutdown
wait 2>/dev/null || true
