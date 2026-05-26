# The privacy model

ClickSpot's central design choice: **the LLM only ever sees your schema, never your data.**
When you ask a question, the model gets table names, column types, and the property
descriptions HubSpot already publishes — enough to write correct SQL, and nothing else.

## What reaches the LLM

✅ Sent to the model:

- Table and column names
- Column types
- Property descriptions and business context from HubSpot's schema
- Your question

❌ Never sent to the model:

- Row values — no names, emails, deal amounts, notes, or call transcripts
- Query results — the SQL runs in ClickHouse after the model is done

The model's job ends when it returns the SQL. ClickSpot validates that SQL, runs it against
ClickHouse itself, and renders the result. The numbers you see were computed locally, not
by the LLM.

```
User question
    -> Schema prompt (tables + types + semantics)   ← the only thing the LLM sees
    -> LLM (Claude / GPT-4o) writes SQL
    -> SQL validation (whitelist tables, block mutations)
    -> ClickHouse executes the query                ← your data stays here
    -> Chart / table / number rendered inline
```

## Guardrails on the generated SQL

The model writing SQL doesn't mean arbitrary SQL runs. Before execution, ClickSpot:

- **Whitelists tables** — queries can only touch known warehouse tables.
- **Blocks mutations** — anything that isn't a read is rejected.

The same schema prompt and the same guardrails apply whether the query comes from in-app
chat or the [MCP server](../guides/mcp.md).

## Anonymization for external sharing

For anything that leaves your environment — the MCP server, demos — ClickSpot reads from
masked mirrors. The pipeline anonymizes silver and gold into separate `silver_anon` and
`gold_anon` databases, so the structure and relationships are intact but the values are
masked. See [The medallion warehouse](warehouse.md).

## What this means in practice

- You can point chat at production CRM data without sending that data to a model provider.
- You can expose the warehouse to Claude Desktop over MCP and keep the same guarantees.
- The privacy boundary doesn't depend on the LLM behaving — the data simply isn't in the
  prompt to begin with.

For the implementation, see the [Backend](../backend.md) doc (chat API, schema prompt
construction, and SQL validation).
