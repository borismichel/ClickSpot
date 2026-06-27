# Dashboards

Dashboards turn one-off questions into something persistent — a set of cards that stay put
and refresh against live data every time you open them. Generate a whole board from a single
prompt, or build one by hand from chat answers you've saved; either way the cards hold queries,
not snapshots, so the numbers stay current.

<figure markdown>
  ![Deals dashboard: deal count and amount by stage with year-to-date KPIs](../assets/screenshots/dashboard-deals.png){ .shot }
  <figcaption>A deals dashboard. Pinned cards with year-to-date KPIs and breakdowns by stage.</figcaption>
</figure>

There are two ways to build one: describe it in a prompt and let ClickSpot generate the whole
board, or assemble it card by card from answers you've saved.

## Generate a dashboard from a prompt

The fast path: describe the dashboard you want in one prompt and ClickSpot builds the whole
thing — a set of complementary widgets, laid out and ready — instead of you pinning cards one
at a time.

Open **Generate** in the top navigation (the :material-lightning-bolt: icon), then:

1. Pick the **Data Space** the dashboard should read from.
2. Describe your analysis case and the dashboard you want, in plain English — for example
   *"Sales pipeline health overview — headline KPIs, value by stage, trend over time, and top
   deals."* The more you say about the angle you care about, the closer the layout lands.
3. Click **Generate dashboard**.

**Watch it build.** There's no blank spinner — generation streams its progress. A bar reports
each stage as it happens: planning the dashboard, then generating and validating each widget
in turn (*"Generating widget 3 of 6…"*), so you can see the board taking shape.

**Preview before you commit.** The result lands as a **Draft** (a blue *Draft* tag sits in the
header) — a full preview grid of live widgets, with nothing saved yet. It behaves like a real
dashboard: drag and resize tiles, edit a widget's SQL, drop one you don't want, and apply the
same global filter bar (date, owner, pipeline) covered below.

**Save or discard.**

- **Save** names the dashboard and promotes the whole draft into your Data Space in one step —
  every widget's SQL, chart type, and position carried over — then drops you on the saved
  board, where it's a first-class dashboard like any other.
- **Discard** throws the draft away. Because nothing was ever persisted, there's nothing to
  clean up — you land back at an empty prompt. (You're asked to confirm first, so a stray
  click can't lose a draft you meant to keep.)

!!! note "Generation is bounded"
    A generated dashboard is capped at a handful of widgets (you'll see a note if it hits the
    ceiling), and every widget's SQL goes through the same guardrails as [chat](chat.md):
    read-only, whitelisted tables, validated and dry-run before it renders, with one automatic
    repair attempt if a query fails. A draft is safe to generate and free to throw away.

<figure markdown>
  ![One Shot Dashboard: a single prompt has generated a preview grid of pipeline widgets — KPI tiles, value by stage, and a trend chart — shown in a transient Draft state with Save and Discard actions](../assets/screenshots/one-shot-dashboard.png){ .shot }
  <figcaption>One Shot Dashboard. A single prompt generates a full preview grid; keep it with <strong>Save</strong> or throw the draft away with <strong>Discard</strong>.</figcaption>
</figure>

## Build a dashboard by hand

Prefer to assemble a board yourself — or grow one a card at a time from questions you've
already asked? Build it manually.

### Create a dashboard

From the **Dashboards** page, create a new dashboard and give it a name (a deal name like
"Pipeline health" or "EMEA revenue" beats "Dashboard 1" when you have a few). It opens
empty, ready for cards.

### Pin cards to it

Cards come from saved chat answers, so the flow starts in [chat](chat.md):

1. Ask a question and click **Save** to put the answer in the object library.
2. On the dashboard, add a card and pick that saved object from the library.
3. Drag it on the grid to size and position it.

Repeat for each metric you want side by side. A card holds the query, not a snapshot, so
every card re-runs against current data on load.

## Filter the whole board at once

Each dashboard has a global filter bar across the top with three controls: **date range**,
**owner**, and **pipeline**. Set a filter and every card updates together, so you can read a
KPI tile and its supporting breakdowns through the same lens.

<figure markdown>
  ![A dashboard with the global filter bar expanded and engaged: a date range, an owner (Sarah Chen), and a pipeline (Sales Pipeline) applied; the KPI tiles and bar charts below reflect the filtered slice](../assets/screenshots/dashboard-filters.png){ .shot }
  <figcaption>The filter bar in use — date, owner, and pipeline applied at once. Every card re-runs through the same lens.</figcaption>
</figure>

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

## Edit and rearrange

Dashboards aren't fixed once built. Rearrange the grid by dragging cards, resize them to
give the important number more room, and remove a card you no longer need. The layout is
saved per dashboard, so the arrangement you set is the one everyone sees.

## Where to go next

- Scope a dashboard (and its filters) to one team or pipeline with a
  [Data Space](../concepts/data-spaces.md).
- Build the underlying answers in [chat](chat.md).
