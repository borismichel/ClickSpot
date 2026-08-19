# Settings & environment

ClickSpot is configured through environment variables (in `.env` or your shell), the
in-app Settings drawer, and a couple of files under `~/.clickspot/`. This page covers the
environment variables; LLM keys and HubSpot scopes have their own pages.

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `HUBSPOT_TOKEN` | No | HubSpot private app token. Required only for live HubSpot extraction. Omit to use the offline demo seed (`make seed`). |
| `HUBSPOT_HUB_ID` | No | HubSpot portal/hub ID — builds canonical record URLs for the frontend and MCP responses. Only needed alongside `HUBSPOT_TOKEN`. |
| `HUBSPOT_REGION` | No | Region code (`na1`, `eu1`, `na2`, …) for the click-through URL subdomain. Auto-detected from `HUBSPOT_TOKEN` on the first bronze call and cached in `~/.clickspot/customer.json`; set explicitly only when running MCP without the token. |
| `CLICKHOUSE_HOST` | Yes | ClickHouse hostname (default: `localhost`) |
| `CLICKHOUSE_PORT` | Yes | ClickHouse HTTP port (default: `8124`) |
| `CLICKHOUSE_USER` | Yes | ClickHouse username (default: `hs2ch`) |
| `CLICKHOUSE_PASSWORD` | Yes | ClickHouse password (default: `hs2ch`) |
| `DAGSTER_HOME` | Recommended | Persistent Dagster storage directory |
| `DAGSTER_GRAPHQL_URL` | No | Dagster GraphQL endpoint the backend calls to reload the code location after a Settings → Properties change (default: `http://localhost:8194/graphql`). Compose overrides it to `http://dagster:8194/graphql`, since Dagster runs as a separate service there. |
| `ANTHROPIC_API_KEY` | Optional | Anthropic API key for Claude |
| `OPENAI_API_KEY` | Optional | OpenAI API key for GPT-4o |
| `CLICKSPOT_CLICKHOUSE_MODE` | Optional | `local`, `docker`, or `external`. Auto-picked when unset (see [Install & run](../getting-started/install.md#choosing-a-clickhouse-mode)). |
| `CLICKSPOT_TRUSTED_HOSTS` | No | Comma-separated IPs/CIDRs allowed to write LLM keys via the Settings drawer, in addition to loopback. See below. |

## Trusted hosts

The Settings drawer writes (LLM keys, Claude OAuth token) are restricted to loopback. Behind
Docker, the backend sees those requests coming from the bridge gateway rather than
`127.0.0.1` (a `172.x` address on a native Linux bridge, `192.168.x` under Docker Desktop),
so the bundled demo defaults `CLICKSPOT_TRUSTED_HOSTS` to the RFC1918 private ranges
(`10.0.0.0/8,172.16.0.0/12,192.168.0.0/16`). That's why the in-app key form works against
the loopback-bound demo on any Docker runtime without extra setup.

!!! warning "If you expose ClickSpot beyond localhost"
    The guard can't tell a host request from a LAN one once both arrive through the same
    bridge or proxy. If you opt into LAN exposure (see
    [Install & run](../getting-started/install.md#run-with-docker-recommended)), treat key
    writes as exposed too and gate them with your own auth. Set `CLICKSPOT_TRUSTED_HOSTS`
    yourself for custom networks or a non-default reverse proxy.

## Files under `~/.clickspot/`

| File | Purpose |
|---|---|
| `customer.json` | Portal pipeline names, stages, currency, company name. Auto-discovered on first run, then editable. See [Connect HubSpot](../getting-started/connect-hubspot.md). |
| `config.json` | LLM provider configuration written by the Settings drawer. See [LLM providers](llm-providers.md). |

## Adding data

**New HubSpot property.** Add one tuple in `silver_config.py`:

```python
DIM_DEALS["columns"].append(("new_field", "hs_property_name", "String"))
```

**New computed metric.** Add to `app/engine/metrics.py`:

```python
COMPUTED_METRICS["new_metric"] = {
    "label": "New Metric", "format": "percent", "table": "dim_deals",
    "sql": "countIf(condition) / nullIf(count(), 0)",
}
```
