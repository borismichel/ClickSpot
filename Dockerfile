# ClickSpot application image — Python backend, Dagster orchestrator, and the
# offline seed loader all ship from this one image. The three compose services
# (backend / dagster / seed) run it with different commands; the codebase is
# identical, so a single image keeps pulls small and versions in lockstep.
#
# Pinned to Python 3.10 because requirements.lock is compiled for 3.10
# (`uv pip compile --python-version 3.10`); using the same minor avoids
# resolving wheels the lockfile never saw.

# ---- builder: resolve the hashed lockfile into a self-contained venv --------
FROM python:3.10-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1

# build-essential covers any dependency that only publishes an sdist for the
# platform; the toolchain stays in the builder and never reaches the runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH

WORKDIR /app
COPY requirements.lock ./
# requirements.lock carries hashes, so pip runs in --require-hashes mode and
# installs the exact, fully transitive set CLI-6 was tested against.
RUN pip install --no-cache-dir -r requirements.lock

# ---- runtime: slim image with just the venv + source ------------------------
FROM python:3.10-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/opt/venv/bin:$PATH

# curl backs the container healthcheck; tini reaps the uvicorn/dagster children.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=app:app . .

# ~/.clickspot holds the SQLite app store, LLM key config, and the discovered
# customer.json; DAGSTER_HOME holds Dagster run/event storage. Both are mounted
# as named volumes in compose so they persist across restarts.
RUN mkdir -p /home/app/.clickspot /home/app/dagster_home \
    && chown -R app:app /home/app

USER app

ENV HOME=/home/app \
    DAGSTER_HOME=/home/app/dagster_home \
    CLICKHOUSE_HOST=clickhouse \
    CLICKHOUSE_PORT=8123 \
    CLICKHOUSE_USER=hs2ch \
    CLICKHOUSE_PASSWORD=hs2ch

# 8192 = FastAPI, 8194 = Dagster webserver.
EXPOSE 8192 8194

ENTRYPOINT ["tini", "--"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8192"]
