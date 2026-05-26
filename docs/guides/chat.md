# Chat (NL → SQL)

Chat is the front door to ClickSpot. You ask a question in plain English; an LLM writes the
ClickHouse SQL, ClickSpot validates and runs it, and the answer comes back as a chart,
table, or number — with the generated SQL shown so you can check its work.

The model only sees your schema, never your data — see [The privacy model](../concepts/privacy.md).

<figure markdown>
  ![ClickSpot chat home with example prompts](../assets/screenshots/chat-home.png){ .shot }
  <figcaption>The chat home — start from a blank prompt or one of the suggestions.</figcaption>
</figure>

## Asking a question

Type a question and send it. ClickSpot builds a schema prompt (tables, types, and the
business context from your HubSpot properties), the LLM returns a structured response, and
the result renders inline:

```
User question
    -> Schema prompt (tables + semantics + business context)
    -> LLM (Claude / GPT-4o)
    -> Structured response {sql, viz, title, explanation, context}
    -> SQL validation (whitelist tables, block mutations)
    -> ClickHouse execution
    -> Chart / table / number rendered inline
```

<figure markdown>
  ![Chat answering "show me activity trends by type" with a 12-month multi-series trend chart and the generated SQL](../assets/screenshots/chat-activity-trends.png){ .shot }
  <figcaption>A question answered with a multi-series trend chart and the SQL behind it.</figcaption>
</figure>

## What comes back

- **A visualization** — one of six types: number, table, bar, line, funnel, or comparison.
- **The SQL** — the exact ClickHouse query, so you can read or reuse it.
- **An explanation** — what the query did and any assumptions it made.

Queries use relative date expressions (`today()`, `toStartOfMonth()`), so a saved result
stays current as time moves. Period-over-period questions come back with colored delta
badges.

## Good first questions

On the demo warehouse, try:

- *"Show me activity trends by type over the last 12 months."*
- *"Which reps have the most open pipeline?"*
- *"What's our win rate by deal source?"*
- *"What's our pipeline coverage for this quarter?"*

## Saving and pinning

Like an answer? Save it to the object library and pin it to a dashboard, where global
filters apply across every card. See [Dashboards](dashboards.md).

<!-- UXDesigner (CLI-118 follow-up): expand into a full walkthrough — composing a question,
reading the SQL/explanation panel, switching viz types, follow-up questions in a thread,
and saving to the library. Add fresh screenshots for the viz-type switch and the save flow.
Run the humanify skill across this page. -->
