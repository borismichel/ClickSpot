# MCP server

ClickSpot ships an MCP (Model Context Protocol) server that exposes the **anonymized**
warehouse to Claude Desktop and other MCP clients. It uses the same schema prompt and the
same SQL guardrails as in-app chat — so you can query your CRM from your assistant of
choice without your data reaching the model.

## What it exposes

- The masked `silver_anon` / `gold_anon` warehouse, not the raw silver/gold tables — see
  [The medallion warehouse](../concepts/warehouse.md) and
  [The privacy model](../concepts/privacy.md).
- The same table whitelist and mutation-blocking guardrails as in-app chat.

## Connecting Claude Desktop

Point an MCP client (such as Claude Desktop) at the ClickSpot MCP server. The client can
then ask schema-aware questions and run validated, read-only queries against the anonymized
warehouse.

!!! note "Running MCP without the token"
    `HUBSPOT_REGION` is normally auto-detected from `HUBSPOT_TOKEN`. When running MCP
    without the token, set `HUBSPOT_REGION` explicitly so click-through record URLs resolve
    to the right subdomain. See [Settings & environment](../configuration/index.md).

For the server implementation, see the [Backend](../backend.md) doc (the MCP section under
`app/mcp/`).

<!-- UXDesigner (CLI-118 follow-up): expand into a concrete setup walkthrough — the exact
Claude Desktop config block (command/args/env), starting the server, and a screenshot of a
query running in Claude Desktop. Confirm the exact connection command with CTO before
publishing. Run the humanify skill. -->
