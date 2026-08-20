# FAQ

## Does my CRM data get sent to the LLM?

No. The model only ever sees your schema: table names, column types, and the property
descriptions HubSpot publishes. The SQL it writes runs in ClickHouse; your row values never
leave your environment. See [The privacy model](concepts/privacy.md).

## Do I need a HubSpot account to try it?

No. The `:demo` image and `make seed` both load a synthetic warehouse with no token and no
portal. You only need a HubSpot private app token to load your **own** data. See
[Connect HubSpot](getting-started/connect-hubspot.md).

## Do I need an LLM key?

Only for chat. Dashboards, the data explorer, and linked selections all run against the
warehouse directly. Add an Anthropic or OpenAI key (or a Claude OAuth token) to turn chat
on. See [LLM providers](configuration/llm-providers.md).

## Is ClickSpot exposed on the network?

No, not by default. Every port binds to `127.0.0.1`, and ClickSpot has no built-in auth.
Exposing it to a LAN or VPN is opt-in and you put your own auth in front. See the warning
in [Install & run](getting-started/install.md#run-with-docker-recommended).

## How fresh is the data?

As fresh as your last sync. **Settings → Data sync** shows the last-refreshed time, a
**Sync now** button, and a switch for automatic hourly refreshes (off by default). Assets
can also be materialized on demand from the Dagster UI. See
[The medallion warehouse](concepts/warehouse.md).

## Which LLM providers are supported?

Anthropic API, OpenAI API, Claude OAuth (for Pro/Max subscribers), and the Claude CLI (from
source only). See [LLM providers](configuration/llm-providers.md).

## Can I query it from outside the app?

Yes. The [MCP server](guides/mcp.md) exposes the anonymized warehouse to Claude Desktop
and other MCP clients with the same schema prompt and guardrails as in-app chat.

## Can I run it without Docker?

Yes. `./bootstrap.sh` installs the dependencies and a pinned single-binary ClickHouse, no
containers required. See [Run from source](getting-started/install.md#run-from-source).

## How do I add a custom HubSpot property?

Add a tuple in `silver_config.py` (or `silver_config_custom.py` for portal-specific
properties). See [Settings & environment](configuration/index.md#adding-data) and
[Connect HubSpot](getting-started/connect-hubspot.md).

## Where's the source / what's the license?

ClickSpot is open source under the [MIT License](https://github.com/borismichel/ClickSpot/blob/main/LICENSE),
on GitHub at [borismichel/ClickSpot](https://github.com/borismichel/ClickSpot).
