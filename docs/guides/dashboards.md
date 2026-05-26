# Dashboards

Dashboards turn one-off chat answers into something persistent. Save a chat result to the
object library, pin it to a dashboard, and it stays there — refreshing against live data
every time you open it.

<figure markdown>
  ![Deals dashboard — deal count and amount by stage with year-to-date KPIs](../assets/screenshots/dashboard-deals.png){ .shot }
  <figcaption>A deals dashboard — pinned cards with year-to-date KPIs and breakdowns by stage.</figcaption>
</figure>

## Pinning a result

1. Ask a question in [chat](chat.md).
2. Save the result to the object library.
3. Pin it to a dashboard and arrange the cards on the grid.

## Global filters

Each dashboard has global filters — **date range, owner, and pipeline** — that apply to
every card at once. There's no AI at query time: filters are applied by rewriting the SQL
directly.

```
Dashboard filter state
    -> sqlglot AST parse (ClickHouse dialect)
    -> Identify table references from a static registry
    -> Inject WHERE conditions (silver uses IDs, gold uses names)
    -> Re-execute all card queries
```

Because filtering is rule-based SQL rewriting rather than a fresh LLM call, it's fast and
deterministic — the same filter state always produces the same query.

<!-- UXDesigner (CLI-118 follow-up): expand into a walkthrough — creating a dashboard,
arranging the grid, setting each global filter and seeing every card update, and editing a
card. Add screenshots of the filter bar and the grid edit mode. Run the humanify skill. -->
