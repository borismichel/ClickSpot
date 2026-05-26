# Quickstart

There are three ways into ClickSpot, all of them live. The fastest needs nothing but
Docker and about a minute.

## Try the preloaded demo (60 seconds)

The `:demo` image has a synthetic CRM baked in — no token, no setup, no portal to connect.

```bash
docker run --rm -p 8080:8080 ghcr.io/borismichel/clickspot:demo
```

Open <http://localhost:8080> and start clicking. The dashboards, data explorer, and
linked selections all work straight away on the demo warehouse.

Chat turns on the moment you add an LLM key:

```bash
docker run --rm -p 8080:8080 -e ANTHROPIC_API_KEY=sk-... ghcr.io/borismichel/clickspot:demo
```

!!! note "Why chat needs a key but browsing doesn't"
    Everything except chat runs against the warehouse directly. Chat is the only feature
    that calls an LLM to turn your question into SQL, so it needs an Anthropic or OpenAI
    key. The model still only sees your schema — see [The privacy model](../concepts/privacy.md).

## Self-host with Docker Compose

`docker compose up` brings up the whole stack (ClickHouse, backend, Dagster, frontend) and
seeds the demo warehouse on first boot.

```bash
docker compose up
```

Open <http://localhost:8193>. To enable chat, pass a key:

```bash
ANTHROPIC_API_KEY=sk-... docker compose up   # or OPENAI_API_KEY=sk-...
```

Got a HubSpot portal? Add `HUBSPOT_TOKEN=...` to load your own data instead of the demo
set. Full walkthrough: [Install & run](install.md) → [Connect HubSpot](connect-hubspot.md).

## Run from source

No containers at all — `./bootstrap.sh` installs the dependencies and a pinned,
single-binary ClickHouse.

```bash
./bootstrap.sh --seed --start
```

That one command bootstraps dependencies, starts ClickHouse, initializes the schemas,
loads the offline demo warehouse, and starts the app. Step-by-step instructions and the
prerequisites are in [Install & run](install.md#run-from-source).

## Where to next

| You want to… | Go to |
|---|---|
| Understand the architecture before you commit | [How ClickSpot works](../concepts/how-it-works.md) |
| Load your own HubSpot data | [Connect HubSpot](connect-hubspot.md) |
| Ask your first question | [First run](first-run.md) |
| Set environment variables | [Settings & environment](../configuration/index.md) |
