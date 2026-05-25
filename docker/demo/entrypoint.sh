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
# Docker forwards the published port in via the bridge, so uvicorn sees the
# request from the bridge gateway rather than 127.0.0.1 — and which private
# address that is depends on the runtime: ~172.17.0.1 on a native Linux bridge,
# but Docker Desktop (macOS/Windows) presents a 192.168.x gateway instead. Trust
# all RFC1918 private ranges so the form works out of the box regardless. The
# source is always a private gateway (never the LAN client's own IP under NAT),
# and the published port governs who can reach the container at all, so this
# doesn't widen exposure. An operator value (e.g. for a custom network) wins.
export CLICKSPOT_TRUSTED_HOSTS="${CLICKSPOT_TRUSTED_HOSTS:-10.0.0.0/8,172.16.0.0/12,192.168.0.0/16}"

echo "[clickspot] starting ClickSpot on http://localhost:${PORT}"
echo "[clickspot] clicking works with no key; set ANTHROPIC_API_KEY or OPENAI_API_KEY to enable chat."
/opt/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" &
APP_PID=$!

# Exit (and tear everything down) as soon as either process dies.
wait -n
shutdown
wait 2>/dev/null || true
