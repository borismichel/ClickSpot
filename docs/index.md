---
hide:
  - navigation
---

# ClickSpot

**Ask your HubSpot CRM questions in plain English — get back SQL, charts, and dashboards.**

ClickSpot pulls your HubSpot CRM into a ClickHouse warehouse every hour, then puts a
chat box in front of it. You type a question; an LLM writes the ClickHouse SQL and hands
back a chart, a table, or a number. The model only ever sees your schema — never a single
row of your data.

[Try it in 60 seconds](getting-started/quickstart.md){ .md-button .md-button--primary }
[How it works](concepts/how-it-works.md){ .md-button }

<figure markdown>
  ![ClickSpot chat answering "show me activity trends by type" with the generated ClickHouse SQL and a 12-month multi-series trend chart](assets/screenshot-chat.png){ .shot }
  <figcaption>Real UI, synthetic demo data — no customer CRM or PII.</figcaption>
</figure>

## Who it's for

RevOps, sales-ops, and data teams who live in HubSpot and want a queryable warehouse plus
a natural-language layer over their CRM — without standing up the pipeline themselves.

## What you get

<div class="grid cards" markdown>

-   :material-chat-question: **NL → SQL chat**

    Ask in plain English. An LLM writes the ClickHouse SQL and returns a chart, table, or
    number. The model sees schema, never data. [Read more](guides/chat.md)

-   :material-view-dashboard: **Dashboards**

    Pin chat results and apply global filters (date, owner, pipeline) through rule-based
    SQL rewriting — no AI at query time. [Read more](guides/dashboards.md)

-   :material-folder-multiple: **Data Spaces**

    Scoped, configured views over the warehouse, each with its own chat, dashboards, and
    filters. [Read more](concepts/data-spaces.md)

-   :material-graph: **Linked selections**

    Pick a value anywhere and connected tables filter automatically through the
    relationship graph. [Read more](guides/data-explorer.md)

-   :material-server-network: **MCP server**

    Exposes the anonymized warehouse to Claude Desktop and other MCP clients, with the same
    guardrails as in-app chat. [Read more](guides/mcp.md)

-   :material-layers-triple: **Medallion ELT**

    Bronze → silver → gold → anon, orchestrated by Dagster with atomic rebuilds.
    [Read more](concepts/warehouse.md)

</div>

## Start here

- New to ClickSpot? Run the [60-second demo](getting-started/quickstart.md).
- Connecting your own portal? See [Install & run](getting-started/install.md) then
  [Connect HubSpot](getting-started/connect-hubspot.md).
- Want the mental model first? Read [How ClickSpot works](concepts/how-it-works.md) and
  [The privacy model](concepts/privacy.md).

ClickSpot is open source under the [MIT License](https://github.com/borismichel/ClickSpot/blob/main/LICENSE).
