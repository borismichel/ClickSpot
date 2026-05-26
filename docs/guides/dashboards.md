# Dashboards

Dashboards turn one-off chat answers into something persistent. Save a chat result to the
object library, pin it to a dashboard, and it stays there, refreshing against live data
every time you open it.

<figure markdown>
  ![Deals dashboard: deal count and amount by stage with year-to-date KPIs](../assets/screenshots/dashboard-deals.png){ .shot }
  <figcaption>A deals dashboard. Pinned cards with year-to-date KPIs and breakdowns by stage.</figcaption>
</figure>

## 1. Create a dashboard

From the **Dashboards** page, create a new dashboard and give it a name (a deal name like
"Pipeline health" or "EMEA revenue" beats "Dashboard 1" when you have a few). It opens
empty, ready for cards.

## 2. Pin cards to it

Cards come from saved chat answers, so the flow starts in [chat](chat.md):

1. Ask a question and click **Save** to put the answer in the object library.
2. On the dashboard, add a card and pick that saved object from the library.
3. Drag it on the grid to size and position it.

Repeat for each metric you want side by side. A card holds the query, not a snapshot, so
every card re-runs against current data on load.

## 3. Filter the whole board at once

Each dashboard has a global filter bar across the top with three controls: **date range**,
**owner**, and **pipeline**. Set a filter and every card updates together, so you can read a
KPI tile and its supporting breakdowns through the same lens.

There's no AI at query time. Filters are applied by rewriting the SQL of each card directly:

```
Dashboard filter state
    -> sqlglot AST parse (ClickHouse dialect)
    -> Identify table references from a static registry
    -> Inject WHERE conditions (silver uses IDs, gold uses names)
    -> Re-execute all card queries
```

Because filtering is rule-based SQL rewriting and not a fresh LLM call, it's fast and
deterministic: the same filter state always produces the same query. Clear the filters to
return every card to its unfiltered view.

!!! tip "Filters live in the URL"
    The active filter state is encoded in the dashboard URL, so a filtered view is
    shareable and bookmarkable. Send someone "Q2, EMEA pipeline" and they land on exactly
    that, no setup required.

## 4. Edit and rearrange

Dashboards aren't fixed once built. Rearrange the grid by dragging cards, resize them to
give the important number more room, and remove a card you no longer need. The layout is
saved per dashboard, so the arrangement you set is the one everyone sees.

## Where to go next

- Scope a dashboard (and its filters) to one team or pipeline with a
  [Data Space](../concepts/data-spaces.md).
- Build the underlying answers in [chat](chat.md).
