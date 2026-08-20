# Install & run

ClickSpot runs three ways: a preloaded demo image, a self-hosted Docker Compose stack, or
straight from source with no containers. Docker is the primary path; source needs no
containers at all.

## Run with Docker (recommended)

Brings up the whole stack (ClickHouse, backend, Dagster, frontend) with an empty warehouse:

```bash
docker compose up
```

To explore without a HubSpot portal, add the demo profile — it loads the bundled synthetic
warehouse (bronze → silver → gold → anon) once, then exits:

```bash
docker compose --profile demo up
```

Open <http://localhost:8193>. For chat, set a key first:

```bash
ANTHROPIC_API_KEY=sk-... docker compose up   # or OPENAI_API_KEY=sk-...
```

Got a HubSpot portal? Set `HUBSPOT_TOKEN` and `HUBSPOT_HUB_ID` in `.env`, leave
`--profile demo` off, and click **Sync now** under **Settings → Data sync** to load it
(automatic refreshes ship off — the switch on the same tab turns on hourly runs).
Released images pull from GHCR (public, no login) with `docker compose pull`.

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

### Upgrading an existing Docker deployment

Everything above that changed between releases lives in `docker-compose.yml`, not in the
application image, so an upgrade is `git pull` plus a recreate — no waiting on a published
image:

```bash
git pull
docker compose up -d --force-recreate
```

Two things to know before you do:

- **The backend and Dagster now share one `~/.clickspot`.** Dagster previously kept a
  private copy in its writable layer, which no other process could see. Adopting the shared
  volume supersedes that copy. If it held anything you care about — a hand-edited
  `customer.json`, say — copy it out first with
  `docker compose cp dagster:/home/app/.clickspot/customer.json ./customer.json.bak`.
- **The frontend health probe fix ships in the frontend image**, so it reaches you only
  once a new image is published (`docker compose pull`). Until then that container keeps
  reporting unhealthy while serving normally.

!!! warning "Already have demo records in a portal warehouse?"
    Gating the seeder stops new synthetic records; it does not remove ones already loaded.
    The seed loader mints object IDs from fixed low bands (`IdMinter._BASES` in
    `scripts/seed.py`: owners from 100,000, companies from 2,000,000, then contacts, deals,
    and the five activity types one million apart up to 9,000,000), all far below real
    HubSpot object IDs, so the two are separable — count what you have with
    `SELECT count() FROM bronze.hs_deals WHERE toUInt64OrZero(_record_id) < 10000000`
    before deciding what to delete. Cleanup tooling is not part of ClickSpot; on a
    warehouse that has only ever held demo data, dropping the databases and
    re-materializing `bronze_job` is simpler and safer than a targeted delete.

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

### Windows

`start.sh` needs a bash shell, so on native Windows use its PowerShell sibling instead:

```powershell
.\start.ps1
```

Same services, same ports. It defaults to the `docker` ClickHouse mode (Docker Desktop
required) and also accepts `external`; the Docker-free `local` mode is Linux-only — for
that, use WSL and run `./start.sh` inside it. If PowerShell blocks the script, run once
with `powershell -ExecutionPolicy Bypass -File start.ps1` or unblock your user scope with
`Set-ExecutionPolicy RemoteSigned -Scope CurrentUser`.

## Next steps

- Loading your own portal? [Connect HubSpot](connect-hubspot.md).
- Ready to ask a question? [First run](first-run.md).
- Need the full variable list? [Settings & environment](../configuration/index.md).
