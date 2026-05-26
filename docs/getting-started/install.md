# Install & run

ClickSpot runs three ways: a preloaded demo image, a self-hosted Docker Compose stack, or
straight from source with no containers. Docker is the primary path; source needs no
containers at all.

## Run with Docker (recommended)

Brings up the whole stack (ClickHouse, backend, Dagster, frontend) and loads the demo
warehouse on first boot:

```bash
docker compose up
```

Open <http://localhost:8193>. Clicking works right away. For chat, set a key first:

```bash
ANTHROPIC_API_KEY=sk-... docker compose up   # or OPENAI_API_KEY=sk-...
```

Got a HubSpot portal? Add `HUBSPOT_TOKEN=...` to load your own data instead of the demo
set. Released images pull from GHCR (public, no login) with `docker compose pull`.

| Service | URL | Notes |
|---------|-----|-------|
| Frontend | <http://localhost:8193> | Chat, dashboards, data explorer — the one URL you open |
| Dagster | <http://localhost:8194> | Pipeline orchestration |
| ClickHouse | <http://localhost:8124> | Data warehouse |

!!! warning "Ports are loopback-only by design"
    Every port binds to `127.0.0.1` only. ClickSpot has no auth, and the frontend is the
    entry point to chat-driven SQL over your CRM, so it stays on the local host by default.
    To reach it from another machine, make that opt-in yourself: change the frontend port
    in `docker-compose.yml` from `"127.0.0.1:8193:80"` to `"0.0.0.0:8193:80"` (or a
    specific host IP) and put it behind your own auth/reverse proxy. If you do, treat
    LLM-key writes as exposed too. See [Settings & environment](../configuration/index.md#trusted-hosts).

## Run from source

Prefer running without containers? You'll need:

- Python 3.10+
- Node.js 20.19+
- `curl` and `tar` for the Docker-free ClickHouse bootstrap
- Optional: a HubSpot private app token with CRM read scopes for live extraction

### Fastest path

One command bootstraps dependencies, starts ClickHouse, initializes the schemas, loads the
offline demo warehouse (CSV → bronze → silver → gold → anon), then starts the app:

```bash
./bootstrap.sh --seed --start
```

### Step by step

`make seed` needs ClickHouse already running, so run these in order:

```bash
./bootstrap.sh      # install Python + frontend deps and the local ClickHouse binary (does not start it)
make clickhouse     # start the Docker-free local ClickHouse runtime
make seed           # load the offline demo warehouse — no token, no portal (self-inits the schema)
./start.sh          # bring up the app; reuses the already-running ClickHouse
```

To walk through portal-specific config when loading your own data:

```bash
python -m app.customer.onboarding
```

This starts:

| Service | URL | Purpose |
|---------|-----|---------|
| ClickHouse | <http://localhost:8124> | Data warehouse (`.clickhouse/` local runtime by default) |
| FastAPI | <http://localhost:8192> | Backend API |
| Dagster | <http://localhost:8194> | Pipeline orchestration |
| Frontend | <http://localhost:8193> | Chat, dashboards, data explorer |

### Choosing a ClickHouse mode

ClickHouse mode is auto-picked when `CLICKSPOT_CLICKHOUSE_MODE` is unset: the Docker-free
local binary on Linux, the ClickHouse container on macOS and Windows (where the binary
can't be auto-downloaded; Docker Desktop required). Force a mode in `.env`:

| `CLICKSPOT_CLICKHOUSE_MODE` | Behavior |
|---|---|
| `local` | Native single-binary ClickHouse (default on Linux) |
| `docker` | Container from `docker-compose.yml`, any OS (default on macOS/Windows) |
| `external` | Point at a ClickHouse you already manage |

## Next steps

- Loading your own portal? [Connect HubSpot](connect-hubspot.md).
- Ready to ask a question? [First run](first-run.md).
- Need the full variable list? [Settings & environment](../configuration/index.md).
