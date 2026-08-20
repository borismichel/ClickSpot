# First run

Once the stack is up, here's the path from a cold start to your first answered question.

## 1. Load the warehouse

1. Open the frontend at <http://localhost:8193> and go to **Settings → Data sync**.
2. Click **Sync now**.

This runs the full medallion pipeline: bronze (raw HubSpot loads) → silver (typed
dimensions, facts, bridges) → gold (aggregates) → anon (masked mirrors), with staged
progress shown on the tab. On the demo seed (`docker compose --profile demo up`, or
`make seed`) it's already loaded and you can skip this; on a live portal this is where
your CRM lands in ClickHouse. See
[The medallion warehouse](../concepts/warehouse.md) for what each layer holds.

Nothing schedules this for you: automatic refreshes ship off, so the first load is always
a manual sync. Flip **"Keep my data up to date automatically"** on the same tab for
hourly refreshes — it shows the next scheduled run time.

!!! note "The technical route"
    The tab drives Dagster under the hood. Materializing **`bronze_job`** in the Dagster
    UI at <http://localhost:8194> does the same thing (sensors chain the downstream
    layers), and the hourly schedule lives there under **Automation → Schedules**.

## 2. Configure an LLM provider

In the same **Settings** drawer (top-right), add an Anthropic API key, OpenAI key, or
Claude OAuth token.

Chat is the only feature that needs a key; everything else runs against the warehouse
directly. Details and trade-offs per provider are in
[LLM providers](../configuration/llm-providers.md).

## 3. Ask your first question

In the chat box, try something like:

> What's our pipeline coverage for this quarter?

ClickSpot builds a schema prompt, the LLM writes ClickHouse SQL, the SQL is validated and
run, and the result comes back as a chart, table, or number, with the generated SQL shown
so you can check its work.

A few good first questions on the demo data:

- *"Show me activity trends by type over the last 12 months."*
- *"Which reps have the most open pipeline?"*
- *"What's our win rate by deal source?"*

## What's next

- Save a result and pin it: [Dashboards](../guides/dashboards.md).
- Explore tables and follow relationships: [Data Explorer](../guides/data-explorer.md).
- Scope a focused view of the warehouse: [Data Spaces](../concepts/data-spaces.md).
- Query from Claude Desktop: [MCP server](../guides/mcp.md).
