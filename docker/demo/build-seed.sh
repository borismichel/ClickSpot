#!/usr/bin/env bash
# Build-time only: start ClickHouse, load the demo warehouse, shut it down.
# Runs inside a `docker build` RUN step so the materialised bronze->silver->
# gold->anon warehouse is baked into the image layer at /var/lib/clickspot-ch.
set -euo pipefail

DATA=/var/lib/clickspot-ch

mkdir -p "$DATA"
chown -R clickhouse:clickhouse "$DATA" /var/log/clickhouse-server

# ClickHouse refuses to run as root, so drop to the clickhouse user. setpriv
# execs (rather than forks), so $! is the real clickhouse-server PID and the
# TERM below shuts it down gracefully.
setpriv --reuid=clickhouse --regid=clickhouse --init-groups \
    clickhouse-server --config-file=/etc/clickhouse-server/config.xml &
CH_PID=$!

echo "[build-seed] waiting for ClickHouse..."
for _ in $(seq 1 60); do
    if curl -sf http://localhost:8123/ping >/dev/null 2>&1; then break; fi
    sleep 1
done
curl -sf http://localhost:8123/ping >/dev/null

# The compose stack gets the `bronze` database for free from the ClickHouse
# container's CLICKHOUSE_DB env. Here we start clickhouse-server directly, so
# create it ourselves before seeding — seed.py opens its client against the
# bronze database before run_init() would create it.
echo "[build-seed] ensuring 'bronze' database exists..."
curl -sf "http://localhost:8123/?user=${CLICKHOUSE_USER:-hs2ch}&password=${CLICKHOUSE_PASSWORD:-hs2ch}" \
    --data-binary 'CREATE DATABASE IF NOT EXISTS bronze' >/dev/null

echo "[build-seed] loading demo warehouse (this runs the CLI-6 seed pipeline)..."
cd /app
/opt/venv/bin/python scripts/seed.py

echo "[build-seed] flushing + stopping ClickHouse..."
kill -TERM "$CH_PID"
wait "$CH_PID" 2>/dev/null || true

echo "[build-seed] done — warehouse baked at $DATA"
