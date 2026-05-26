# MCP server

ClickSpot ships an MCP (Model Context Protocol) server that exposes the **anonymized**
warehouse to Claude Desktop and other MCP clients. It uses the same schema prompt and the
same SQL guardrails as in-app chat, so you can query your CRM from your assistant of choice
without your data reaching the model.

## What it exposes

- The masked `silver_anon` / `gold_anon` warehouse, not the raw silver/gold tables. See
  [The medallion warehouse](../concepts/warehouse.md) and
  [The privacy model](../concepts/privacy.md).
- Two tools: `get_schema` (the full table/column catalog, dictionary patterns, and query
  rules) and `run_sql` (a guarded, read-only query path).
- The same table whitelist and mutation-blocking guardrails as in-app chat, plus an MCP-only
  rule: activity and engagement tables (calls, emails, notes, tasks) are absent from the
  anon layer and rejected, because their free-text content can't be reliably masked.

There's no LLM inside the server. Your MCP client writes the SQL; the server grounds it with
schema context and runs it under guardrails.

## Connect Claude Desktop

The server runs from source over stdio, which is what Claude Desktop expects. Start with the
demo stack already running (so ClickHouse is up) and add a server entry to your
`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "clickspot": {
      "command": "/path/to/ClickSpot/.venv/bin/python",
      "args": ["-m", "app.mcp.server"],
      "env": {
        "CLICKHOUSE_HOST": "localhost",
        "CLICKHOUSE_PORT": "8124",
        "CLICKHOUSE_USER": "hs2ch",
        "CLICKHOUSE_PASSWORD": "hs2ch",
        "HUBSPOT_HUB_ID": "12345678",
        "HUBSPOT_REGION": "na1"
      }
    }
  }
}
```

A few notes on the fields:

- **`command`** points at the Python interpreter from the repo's virtual environment. The
  source install (`./bootstrap.sh` / `pip install -e .`) registers ClickSpot as an editable
  package in that venv, so `python -m app.mcp.server` and the top-level `silver_config` module
  resolve no matter which directory Claude Desktop launches the process from — you don't need a
  `cwd` field (Claude Desktop doesn't reliably honor it) or `PYTHONPATH`.
- **`CLICKHOUSE_*`** match your running warehouse; the values above are the demo defaults
  (`make seed` / the Compose stack). The server connects read-only (`readonly=2`), so it
  can't write even if asked.
- **`HUBSPOT_HUB_ID`** and **`HUBSPOT_REGION`** are optional. Set them to get clickable
  HubSpot record URLs appended to results; leave them out and the data is still served, just
  without the deep links. `HUBSPOT_REGION` has to be explicit here because there's no
  `HUBSPOT_TOKEN` to auto-detect it from. See [Settings & environment](../configuration/index.md).

Restart Claude Desktop after editing the config. The `clickspot` server shows up in its MCP
list, and you can ask schema-aware questions that run as validated, read-only queries
against the anonymized warehouse.

!!! tip "Start every session with the schema"
    Have the client call `get_schema` once at the start of a conversation. It loads the
    table catalog, dictionary patterns, relative-date guidance, and the masking policy, so
    the SQL it writes lands on the first try.

## For the implementation

The server lives in `app/mcp/` (`server.py`, `guardrails.py`, `pii.py`) and runs via
`python -m app.mcp.server`. The [Backend](../backend.md) doc covers the MCP section in
detail: the allowlist, the activity denylist, and the PII filtering.
