# Data Explorer

The Data Explorer is the direct view of the warehouse. Browse the tables, see their typed
columns, and follow the relationships between objects. It's where linked selections live:
pick a value in one table and every connected table filters to match. No SQL, no chat, just
the modeled shape of your CRM.

## 1. Browse the schema

Open the Data Explorer and you get the bronze and silver tables with their typed columns:
the dimensions (deals, contacts, companies, owners), the facts, and the bridge tables that
join them. This is the same modeled layer chat queries against, so it's a good way to learn
what's actually in your warehouse before you start asking questions.

<figure markdown>
  ![Schema browser showing bronze and silver tables with typed columns](../assets/screenshots/explorer-schema.png){ .shot }
  <figcaption>The schema browser. Bronze and silver tables with their typed columns.</figcaption>
</figure>

## 2. Make a linked selection

Select a value in any table and all connected tables filter automatically. Pick a company,
and its deals, contacts, owners, and pipeline stages narrow to match. Pick an owner, and you
see only their deals and the contacts on them. You're navigating the CRM by relationship
rather than by writing joins.

This works by traversing the relationship graph through the silver bridge tables. The graph
has 13 bridge edges, so most CRM objects are a hop or two apart.

<figure markdown>
  ![Data explorer showing deals linked to contacts, companies, owners, and pipeline stages](../assets/screenshots/explorer-associative.png){ .shot }
  <figcaption>Linked selections. Deals connected to contacts, companies, owners, and stages.</figcaption>
</figure>

## 3. Stack and clear selections

Selections combine. Pick a pipeline and then an owner, and you've narrowed to that owner's
deals in that pipeline; every other table reflects both. Clear a selection to widen back
out, or reset everything to return to the full warehouse view.

!!! tip "Use it to scope a question before you ask it"
    Narrow to the slice you care about in the explorer, see which objects are involved, then
    take that framing into [chat](chat.md). It's often quicker to find the right question by
    poking at the relationships first.

## How it relates to the Analytics API

Linked selections are the visible surface of the [Analytics API](analytics-api.md), the
relationship-graph engine that resolves objects and propagates a selection across connected
tables. The explorer is the UI; the Analytics API is the engine underneath it.

For the underlying tables, see [The medallion warehouse](../concepts/warehouse.md); for the
relationship graph itself, see [Architecture](../architecture.md).
