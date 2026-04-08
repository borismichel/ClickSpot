"""Schema prompt builder — generates the LLM system prompt from config + semantic layer.

The prompt is the most critical component for SQL accuracy. It's built from:
1. app/config.py TABLES dict — table structure, columns, types
2. Semantic layer — HubSpot property labels, descriptions, enum options
3. Data model (ERD) — entity relationships from dbt_hubspot patterns
4. Dictionaries — in-memory lookups for ID→name resolution
5. COMPUTED_METRICS — reference SQL patterns
6. Few-shot examples
"""

from app.config import TABLES, GRAPH_EDGES
from app.engine.metrics import COMPUTED_METRICS
from app.engine.sql_builder import _table_ref, _archived_condition
from app.semantic.layer import SemanticLayer
from silver_config import DICT_CONFIGS


def build_schema_prompt(semantic_layer: SemanticLayer | None = None) -> str:
    """Build the full system prompt for SQL generation."""
    blocks = [
        _block_rules(),
        _block_data_model(),
        _block_dictionaries(),
        _block_tables(semantic_layer),
        _block_relationships(),
        _block_metrics(),
        _block_business_context(),
        _block_examples(),
        _block_output_format(),
    ]
    return "\n\n".join(blocks)


def _block_rules() -> str:
    return """You are a ClickHouse SQL expert. Given a natural language question about HubSpot CRM data, generate a ClickHouse SQL query.

RULES:
- Generate ONLY valid ClickHouse SQL. Never use INSERT, UPDATE, DELETE, DROP, CREATE, ALTER.
- Silver tables (silver.*): do NOT use FINAL — tables are fully rebuilt each run via atomic swap, so no duplicates exist. Always filter `archived = 0`.
- Gold tables (gold.*): do NOT use FINAL. No archived column exists. Gold columns are pre-aggregated at their grain (e.g. monthly per rep). When re-aggregating (e.g. yearly from monthly), NEVER alias an aggregate with the same name as the source column — ClickHouse resolves aliases within SELECT and `sum(deals_won) AS deals_won` then `sum(deals_won)` elsewhere becomes `sum(sum(...))` which is illegal. Use distinct aliases like `total_deals_won`.
- DateTime fields with value '1970-01-01 00:00:00' mean "not set" — filter with `> '1970-01-02'` to exclude them.
- String boolean fields (hs_is_closed_won, hs_is_closed) use 'true'/'false' strings, not actual booleans.
- Currency is EUR. Format amounts as numbers, the frontend handles display formatting.
- Always include LIMIT (max 1000 for tables, not needed for single-value aggregates).
- Use ClickHouse functions: countIf(), sumIf(), avgIf(), toDate(), toStartOfMonth(), toStartOfQuarter(), toStartOfYear(), dateDiff().
- For date bucketing in SELECT/GROUP BY: toDate(), toStartOfWeek(), toStartOfMonth(), toStartOfQuarter(), toStartOfYear().
- ALWAYS use relative date expressions instead of hardcoded dates so queries stay valid over time when saved to dashboards:
    "today" / "yesterday"       → today(), today() - 1
    "this week"                 → toStartOfWeek(today(), 1)  (Monday start)
    "last week"                 → toStartOfWeek(today() - 7, 1) ... toStartOfWeek(today(), 1)
    "this month"                → toStartOfMonth(today()) ... today() + 1
    "last month"                → toStartOfMonth(today() - INTERVAL 1 MONTH) ... toStartOfMonth(today())
    "this quarter"              → toStartOfQuarter(today()) ... today() + 1
    "last quarter"              → toStartOfQuarter(today() - INTERVAL 3 MONTH) ... toStartOfQuarter(today())
    "this year"                 → toStartOfYear(today()) ... today() + 1
    "last 30/60/90 days"        → today() - 30 ... today() + 1
    "last N months"             → today() - INTERVAL N MONTH ... today() + 1
  NEVER hardcode absolute dates like '2026-04-01' — always derive from today().
- NEVER wrap columns in functions inside WHERE — it prevents ClickHouse from using ORDER BY index pruning. Use range predicates instead:
    BAD:  WHERE toYear(createdate) = 2026
    GOOD: WHERE createdate >= '2026-01-01' AND createdate < '2027-01-01'
    BAD:  WHERE toMonth(closedate) = 4
    GOOD: WHERE closedate >= '2026-04-01' AND closedate < '2026-05-01'
    BAD:  WHERE toDate(createdate) = today()
    GOOD: WHERE createdate >= today() AND createdate < today() + 1
  Function calls in SELECT expressions and GROUP BY are fine (e.g. toStartOfMonth(closedate) AS month).
- Use dictGet() for ID→name lookups instead of JOINs (see DICTIONARIES section).
- Filter out blank/empty names: WHERE owner_name != '' AND owner_name != ' ' (similar for other name fields).
- When the user says "by X" or "per X", the SQL MUST actually GROUP BY that dimension. The explanation must match what the SQL does — never claim a breakdown that isn't in the query.
- Table aliases: NEVER use single-letter aliases (l, d, a, etc.) — ClickHouse can misparse them. Use descriptive aliases: leads, deals, acts, contacts, etc.
- NEVER use SELECT * — always enumerate columns explicitly. ClickHouse is columnar; SELECT * reads every column from disk.
- Use uniq() instead of COUNT(DISTINCT ...) — HyperLogLog approximation, orders of magnitude faster, accurate to ~2%.
- Use argMax(value, timestamp) / argMin(value, timestamp) for "latest/earliest X per group" patterns — avoids correlated subqueries.
- Use any() for non-aggregated columns functionally dependent on the GROUP BY key (e.g. any(dealname) when grouping by deal_id).
- Always use NULLS LAST in ORDER BY when sorting by Nullable columns or computed expressions that can be NULL — prevents NULL rows from appearing first in DESC sorts.
- When a name column appears in the SELECT, ALWAYS include the corresponding ID column as well — the frontend needs it to generate clickable HubSpot links. Put the ID column immediately before its name column. Use these exact aliases (not generic "name"): dealname→deal_id, company_name→company_id, hs_lead_name→lead_id, firstname/contact_name/full_name→contact_id. When only an ID column is selected (no name), it will also be linked automatically.
- SUBQUERY ALIASES ARE REQUIRED — ClickHouse cannot resolve column names from unaliased subqueries. Always alias: `FROM (SELECT ...) AS sub WHERE sub.col ...`. Without the alias, the outer SELECT gets "Unknown identifier" errors.
- BRIDGE TABLE JOINS ARE N:M — joining through a bridge table WILL multiply rows if an entity has multiple associations. To avoid duplicates:
  - For detail queries: use LIMIT 1 BY primary_key, or wrap the bridge join in a subquery with argMax/any() to pick one associated record.
  - For aggregate queries: aggregate BEFORE joining, or use uniq() to count distinct IDs.
  - Prefer gold tables when available — they have pre-joined, deduplicated data (e.g. gold.agg_lead_health instead of dim_leads + bridge + dim_contacts)."""


def _block_data_model() -> str:
    return """DATA MODEL (HubSpot CRM → ClickHouse):
This follows the standard HubSpot entity model (see dbt_hubspot).

Entities:
  DEALS (silver.dim_deals) — Sales opportunities. Central entity.
    Has denormalized: owner_name, pipeline_label, stage_label (human-readable, use directly).
    Also has raw IDs: hubspot_owner_id, pipeline, dealstage.
  CONTACTS (silver.dim_contacts) — People (leads, customers).
  COMPANIES (silver.dim_companies) — Organizations.
  LEADS (silver.dim_leads) — Lead objects (separate from contacts).
    Has raw IDs: hubspot_owner_id, hs_pipeline (lead pipeline ID), hs_lead_status (lead stage ID).
    Use dictGet to resolve: owner via dict_owners, pipeline via dict_lead_pipelines, stage via dict_lead_pipeline_stages (composite key: pipeline + stage).
  ACTIVITIES (silver.fact_activities) — Calls, meetings, emails, notes, tasks.
    activity_type column discriminates type: 'call', 'meeting', 'email', 'note', 'task'.
    "By type" means GROUP BY activity_type or pivot with countIf(activity_type = '...').
  FORM SUBMISSIONS (silver.fact_form_submissions) — HubSpot form submissions.
    Each row = one form submission. Has form_id, form_name, submitted_at (DateTime), page_url, and submitter fields (email, firstname, lastname, company, jobtitle, phone).
    submitted_at is epoch-converted to DateTime. Use toStartOfMonth(submitted_at) etc. for time series.
  OWNERS (silver.dim_owners) — Sales reps / users.
  PIPELINES (silver.dim_pipelines) — Deal pipeline definitions.
  PIPELINE_STAGES (silver.dim_pipeline_stages) — Stages within pipelines.

Relationships (all N:M via bridge tables):
  CONTACTS ↔ DEALS      via silver.bridge_contact_deal (contact_id, deal_id)
  CONTACTS ↔ COMPANIES  via silver.bridge_contact_company (contact_id, company_id)
  DEALS ↔ COMPANIES     via silver.bridge_deal_company (deal_id, company_id)
  LEADS ↔ CONTACTS      via silver.bridge_lead_contact (lead_id, contact_id)
  LEADS ↔ DEALS         via silver.bridge_deal_lead (lead_id, deal_id)
  LEADS ↔ COMPANIES     via silver.bridge_lead_company (lead_id, company_id)
  ACTIVITIES ↔ CONTACTS via silver.bridge_activity_contact (activity_id, contact_id)
  ACTIVITIES ↔ COMPANIES via silver.bridge_activity_company (activity_id, company_id)
  ACTIVITIES ↔ DEALS    via silver.bridge_activity_deal (activity_id, deal_id)

Foreign keys (direct, no bridge):
  dim_deals.hubspot_owner_id → dim_owners.owner_id
  dim_deals.pipeline → dim_pipelines.pipeline_id
  dim_deals.dealstage → dim_pipeline_stages.stage_id

Gold layer (pre-aggregated, has denormalized labels — use directly, no dictGet needed):
  gold.agg_rep_performance — Monthly per-rep aggregates. Has owner_name (use directly).
  gold.agg_deal_health — Per-deal health indicators. Has owner_name, pipeline_label, stage_label (use directly).
  gold.agg_source_attribution — Source/channel attribution metrics
  gold.agg_deal_stage_funnel — Deals per pipeline stage with values and weighted values. Has stage_label.
  gold.agg_lead_health — Per-lead health indicators. Has owner_name, pipeline_label, stage_label (use directly).
  gold.agg_deal_cohorts — Creation-month cohort analysis (win/loss/open by cohort)
  gold.fact_pipeline_snapshots — Historical daily pipeline state (append-only)

IMPORTANT: Gold tables have pre-denormalized human-readable labels (owner_name, pipeline_label, stage_label). Use these columns directly — do NOT use dictGet() on gold tables."""


def _block_dictionaries() -> str:
    """Auto-generate dictionary documentation from DICT_CONFIGS.

    For each dictionary, emits:
    - Key signature and available value fields
    - Per-table column mappings (which columns in which tables map to which keys)
    - Ready-to-use dictGet() examples
    - Composite-key patterns where applicable
    """
    lines = [
        "DICTIONARIES (in-memory hash lookups — use dictGet() instead of JOINs for ID→label resolution):",
        "Always wrap keys in tuple(). Composite-key dicts need tuple(key1, key2).",
        "",
    ]

    for table_name, cfg in DICT_CONFIGS.items():
        dict_name = "dict_" + table_name.removeprefix("dim_")
        fq = f"silver.{dict_name}"
        key_names = [k[0] for k in cfg["keys"]]
        value_names = [v[0] for v in cfg["values"]]
        value_descs = [f"{v[0]} ({v[2]})" for v in cfg["values"]]
        is_composite = len(key_names) > 1

        # Header
        key_sig = ", ".join(key_names)
        lines.append(f"  {fq}({key_sig}) — {cfg['description']}")
        lines.append(f"    Returns: {', '.join(value_descs)}")

        # Custom patterns (e.g. full_name concat)
        patterns = cfg.get("patterns", {})

        # Per-table usage — tells the LLM exactly which columns to pass
        used_by = cfg.get("used_by", {})
        if used_by:
            lines.append(f"    Used in:")
            for target_table, col_map in used_by.items():
                # col_map: {dict_key: table_column}
                if is_composite:
                    tuple_args = ", ".join(f"{target_table}.{col_map[k]}" for k in key_names)
                    keys_expr = f"tuple({tuple_args})"
                else:
                    table_col = list(col_map.values())[0]
                    keys_expr = f"tuple({target_table}.{table_col})"

                # Primary value example
                primary_value = value_names[0]
                example = f"dictGet('{fq}', '{primary_value}', {keys_expr})"

                # Use pattern if available (e.g. full_name concat)
                for pat_name, pat_template in patterns.items():
                    example = f"{pat_template.format(dict=fq, keys=keys_expr)} AS {pat_name}"
                    break  # show first pattern

                db = "gold" if target_table.startswith("agg_") or target_table.startswith("fact_pipeline") else "silver"
                lines.append(f"      {db}.{target_table}: {example}")

        lines.append("")

    # Denormalized shortcut note
    lines.append("  NOTE: silver.dim_deals has pre-denormalized owner_name, pipeline_label, stage_label — use those directly, no dictGet needed.")

    return "\n".join(lines)


def _block_tables(semantic_layer: SemanticLayer | None) -> str:
    lines = ["TABLES AND COLUMNS:"]

    for table_name, meta in TABLES.items():
        db = meta.get("database", "silver")
        ref = f"{db}.{table_name}"
        archived = _archived_condition(table_name)
        pk = meta["primary_key"]
        display = meta["display_name"]

        lines.append(f"\n{ref} — {display}")
        if archived:
            lines.append(f"  Use: SELECT ... FROM {ref} WHERE {archived}")
        else:
            lines.append(f"  Use: SELECT ... FROM {ref}")
        lines.append(f"  Primary key: {pk}")

        # Get semantic metadata if available
        sem_table = None
        if semantic_layer:
            sem_table = semantic_layer.tables.get(table_name)

        # Primary key column
        pk_type = _get_pk_type(meta)
        lines.append(f"  {pk} {pk_type} (PK)")

        # All fields
        for field_name, field_meta in meta["fields"].items():
            ch_type = field_meta["type"]
            display_name = field_meta["display"]

            # Enrich with semantic layer if available
            label = display_name
            desc = ""
            options_str = ""
            if sem_table and field_name in sem_table.properties:
                prop = sem_table.properties[field_name]
                # Prefer HubSpot label when it exists and is more descriptive
                if prop.label and prop.label != field_name:
                    label = prop.label
                if prop.description:
                    desc = f" — {prop.description}"
                if prop.options:
                    vals = ", ".join(o["value"] for o in prop.options[:10])
                    options_str = f" [values: {vals}]"

            lines.append(f"  {field_name} {ch_type} — \"{label}\"{desc}{options_str}")

    return "\n".join(lines)


def _block_relationships() -> str:
    lines = ["RELATIONSHIPS (for JOINs):"]

    lines.append("\nBridge tables (N:M associations — use JOIN through bridge):")
    for edge in GRAPH_EDGES:
        from_t = edge["from"]
        to_t = edge["to"]
        bridge = edge["bridge"]
        from_key = edge["from_key"]
        to_key = edge["to_key"]
        lines.append(
            f"  {from_t} <-> {to_t}: JOIN silver.{bridge} ON {from_key}, {to_key}"
        )

    lines.append("\nFK lookups: use dictGet() — see DICTIONARIES section above for exact syntax per table.")

    return "\n".join(lines)


def _block_metrics() -> str:
    lines = ["REFERENCE SQL PATTERNS (battle-tested, use these for common metrics):"]
    for name, m in COMPUTED_METRICS.items():
        ref = _table_ref(m['table'])
        archived = _archived_condition(m['table'])
        where = f" WHERE {archived}" if archived else ""
        lines.append(f"  {m['label']}: SELECT {m['sql']} FROM {ref}{where}")
    return "\n".join(lines)


def _block_business_context() -> str:
    return """BUSINESS CONTEXT:
- Company: Acme Software GmbH, a German B2B software company
- Currency: EUR (all monetary values are in Euros)
- Team: AE-led, quota-carrying reps
- Revenue model: mix of new business (new_logo field) and renewals (renewal field)
- Key ARR metric: annual_recurring_revenue column in dim_deals

PIPELINES — CRITICAL:
  "Main Sales Pipeline" — THE main sales pipeline. All AE deals live here.
  "Legacy Leads" — Old pre-qualification pipeline, mostly historical junk. 2700 deals, inflates metrics.
  "Partner Endcustomers" — Partner-sourced end-customer deals (small, 21 deals).
  "New Partners" — Partner recruitment pipeline (no revenue, just tracking).
  "Event Tracking" — Event/promo tracking, not real deals.

DEFAULT PIPELINE RULE: Unless the user explicitly asks about "all pipelines", "legacy", "partner", or a specific pipeline by name, ALWAYS filter to the main pipeline:
  pipeline_label = 'Main Sales Pipeline'
If the user asks to "compare pipelines" or "break down by pipeline", include all. Otherwise, default to main.
Gold tables also have pipeline_label — use pipeline_label = 'Main Sales Pipeline' there too (NOT pipeline = 'default').

STAGES (main pipeline, in order):
  "Discovery" → "Scoping" → "Proof of Value" → "Contract & Negotiation" → "Closed Won" (Closed Won) / "Closed Lost" (Closed Lost) / "Disqualified"

OTHER CONTEXT:
- dim_deals has denormalized columns: pipeline_label (human name), stage_label (human name), owner_name (rep full name)
- hs_manual_forecast_category values: COMMIT, BEST_CASE, MOST_LIKELY, PIPELINE, OMIT
- gold.agg_rep_performance: has owner_name column — use directly, no dictGet needed.
- gold.agg_deal_health: has owner_name, pipeline_label, stage_label columns — use directly, no dictGet needed.
  IMPORTANT: agg_deal_health contains ALL deals (open AND closed). When the user asks about "open" deals, stale deals, or at-risk deals, filter: hs_is_closed = 'false'
- NEVER use dictGet() on gold tables — they have all labels pre-computed."""


def _block_examples() -> str:
    return """FEW-SHOT EXAMPLES:

Q: "What's our win rate this quarter?"
A: {"sql": "SELECT countIf(hs_is_closed_won = 'true') * 1.0 / nullIf(countIf(hs_is_closed = 'true'), 0) AS win_rate FROM silver.dim_deals WHERE archived = 0 AND pipeline_label = 'Main Sales Pipeline' AND closedate >= '2026-04-01' AND closedate <= '2026-06-30' AND closedate > '1970-01-02'", "viz": "number", "title": "Win Rate Q2 2026", "explanation": "Win rate for main pipeline deals closed in Q2 2026."}

Q: "Break that down by rep"
A: {"sql": "SELECT owner_name, countIf(hs_is_closed_won = 'true') * 1.0 / nullIf(countIf(hs_is_closed = 'true'), 0) AS win_rate, countIf(hs_is_closed = 'true') AS total_closed FROM silver.dim_deals WHERE archived = 0 AND pipeline_label = 'Main Sales Pipeline' AND closedate >= '2026-04-01' AND closedate <= '2026-06-30' AND closedate > '1970-01-02' AND owner_name != ' ' GROUP BY owner_name ORDER BY win_rate DESC LIMIT 20", "viz": "bar", "title": "Win Rate by Rep — Q2 2026", "explanation": "Win rate per rep for main pipeline deals closed in Q2 2026."}

Q: "Which deals are at risk?"
A: {"sql": "SELECT dealname, owner_name, stage_label, amount, days_in_current_stage, days_since_last_activity, last_activity_type FROM gold.agg_deal_health WHERE hs_is_closed = 'false' AND is_stale = 1 AND pipeline_label = 'Main Sales Pipeline' AND amount > 0 ORDER BY amount DESC LIMIT 50", "viz": "table", "title": "Stale Deals at Risk", "explanation": "Open stale deals in the main pipeline with no recent activity, sorted by value."}

Q: "Show me monthly closed-won revenue for the last 12 months"
A: {"sql": "SELECT toStartOfMonth(closedate) AS month, sum(amount) AS revenue FROM silver.dim_deals WHERE archived = 0 AND pipeline_label = 'Main Sales Pipeline' AND hs_is_closed_won = 'true' AND closedate >= toDate(now()) - INTERVAL 12 MONTH AND closedate > '1970-01-02' GROUP BY month ORDER BY month LIMIT 12", "viz": "line", "title": "Monthly Closed-Won Revenue", "explanation": "Monthly closed-won revenue from the main sales pipeline."}

Q: "Pipeline by stage"
A: {"sql": "SELECT stage_label, count() AS deals, sum(amount) AS total_value FROM silver.dim_deals WHERE archived = 0 AND (hs_is_closed = 'false' OR hs_is_closed = '') AND pipeline_label = 'Main Sales Pipeline' GROUP BY stage_label ORDER BY total_value DESC LIMIT 20", "viz": "bar", "title": "Open Pipeline by Stage", "explanation": "Open deals in the main sales pipeline grouped by stage."}

Q: "Top reps by ARR this month"
A: {"sql": "SELECT owner_name, deals_won, total_arr_closed, win_rate FROM gold.agg_rep_performance WHERE period_start = toStartOfMonth(today()) AND owner_name != '' ORDER BY total_arr_closed DESC NULLS LAST LIMIT 10", "viz": "bar", "title": "Top Reps by ARR This Month", "explanation": "Rep leaderboard by new ARR closed this month."}

Q: "Compare all pipelines"
A: {"sql": "SELECT pipeline_label, count() AS deals, sum(amount) AS total_value, countIf(hs_is_closed_won = 'true') AS won FROM silver.dim_deals WHERE archived = 0 GROUP BY pipeline_label ORDER BY total_value DESC LIMIT 10", "viz": "bar", "title": "All Pipelines Comparison", "explanation": "Deal count and total value across all pipelines."}

Q: "How did our pipeline develop this month?"
A: {"sql": "SELECT 1", "viz": "comparison", "title": "Pipeline Development This Month", "explanation": "Key pipeline metrics this month compared to last month.", "context": [{"sql": "SELECT count() FROM silver.dim_deals WHERE archived = 0 AND createdate >= toStartOfMonth(today()) AND createdate < today() + 1", "label": "Deals Created", "previous_sql": "SELECT count() FROM silver.dim_deals WHERE archived = 0 AND createdate >= toStartOfMonth(today() - INTERVAL 1 MONTH) AND createdate < toStartOfMonth(today())"}, {"sql": "SELECT countIf(hs_is_closed_won = 'true') FROM silver.dim_deals WHERE archived = 0 AND closedate >= toStartOfMonth(today()) AND closedate < today() + 1", "label": "Deals Won", "previous_sql": "SELECT countIf(hs_is_closed_won = 'true') FROM silver.dim_deals WHERE archived = 0 AND closedate >= toStartOfMonth(today() - INTERVAL 1 MONTH) AND closedate < toStartOfMonth(today())"}, {"sql": "SELECT sum(amount) FROM silver.dim_deals WHERE archived = 0 AND hs_is_closed_won = 'true' AND closedate >= toStartOfMonth(today()) AND closedate < today() + 1", "label": "Revenue Won", "previous_sql": "SELECT sum(amount) FROM silver.dim_deals WHERE archived = 0 AND hs_is_closed_won = 'true' AND closedate >= toStartOfMonth(today() - INTERVAL 1 MONTH) AND closedate < toStartOfMonth(today())"}, {"sql": "SELECT avg(amount) FROM silver.dim_deals WHERE archived = 0 AND createdate >= toStartOfMonth(today()) AND createdate < today() + 1 AND amount > 0", "label": "Avg Deal Size", "previous_sql": "SELECT avg(amount) FROM silver.dim_deals WHERE archived = 0 AND createdate >= toStartOfMonth(today() - INTERVAL 1 MONTH) AND createdate < toStartOfMonth(today()) AND amount > 0"}]}

Q: "Show me leads from paid channels that are stuck"
A: {"sql": "WITH paid_lead_ids AS (SELECT DISTINCT bridge.lead_id FROM silver.bridge_lead_contact AS bridge JOIN silver.dim_contacts AS contacts ON contacts.contact_id = bridge.contact_id WHERE contacts.archived = 0 AND contacts.hs_analytics_source IN ('PAID_SEARCH', 'PAID_SOCIAL')) SELECT leads.hs_lead_name AS lead_name, concat(dictGet('silver.dict_owners', 'first_name', tuple(leads.hubspot_owner_id)), ' ', dictGet('silver.dict_owners', 'last_name', tuple(leads.hubspot_owner_id))) AS owner, dictGet('silver.dict_lead_pipeline_stages', 'label', tuple(leads.hs_pipeline, leads.hs_pipeline_stage)) AS current_stage, if(leads.last_activity_date > '1970-01-02', dateDiff('day', toDate(leads.last_activity_date), today()), NULL) AS days_since_last_activity, toDate(leads.createdate) AS created_date FROM silver.dim_leads AS leads JOIN paid_lead_ids ON paid_lead_ids.lead_id = leads.lead_id WHERE leads.archived = 0 AND leads.createdate >= '2026-01-01' AND leads.createdate < '2027-01-01' AND dictGet('silver.dict_lead_pipeline_stages', 'is_closed', tuple(leads.hs_pipeline, leads.hs_pipeline_stage)) = 'false' ORDER BY days_since_last_activity DESC NULLS LAST LIMIT 200", "viz": "table", "title": "Stuck Paid Leads 2026", "explanation": "Open leads from paid search/social channels in 2026, sorted by days without activity."}"""


def _block_output_format() -> str:
    return """RESPONSE FORMAT:
Return a JSON object with these fields:
- sql: The ClickHouse SQL query (string)
- viz: Visualization type — one of: "number", "table", "bar", "line", "funnel", "comparison"
- title: Short chart/table title (max 10 words)
- explanation: One sentence explaining what the query shows
- context: Array of 2-4 contextual KPI queries (optional but encouraged). Each item has:
    - sql: A simple SELECT that returns exactly 1 row, 1 column (a single number)
    - label: Short KPI label (e.g. "Total Deals", "Avg Deal Size", "Win Rate")
    - previous_sql: (optional) SQL for the equivalent metric in the previous period. Same shape — 1 row, 1 column. Used to compute period-over-period delta.

Context KPIs provide supporting metrics that help interpret the main result. Examples:
- Main query is "pipeline by stage" → context: total pipeline value, total open deals, avg deal size, win rate
- Main query is "activities per rep" → context: total activities, total calls, total meetings, total emails
- Main query is "monthly revenue" → context: total YTD revenue, avg monthly revenue, deals closed
- Main query is "deals at risk" → context: total stale deals, total at-risk value, avg days stale

Rules for context KPIs:
- Each must return exactly 1 row and 1 column
- Apply the same filters as the main query (same pipeline, same date range)
- Keep them fast: simple aggregates, no GROUP BY, no JOIN
- Omit context for "number" viz type (the main result IS a single KPI)

PERIOD-OVER-PERIOD COMPARISONS:
When the user's query involves a relative time period (this month, this quarter, last 30 days, etc.), include previous_sql on each context KPI to enable trend indicators. The previous_sql should query the equivalent prior period:
- "this month" → previous_sql queries last month
- "this quarter" → previous_sql queries last quarter
- "last 30 days" → previous_sql queries the 30 days before that
- "this year" → previous_sql queries last year
The frontend will show a colored delta (green ↑ / red ↓) next to each KPI.

COMPARISON VIZ TYPE:
Use viz: "comparison" when the user explicitly asks for period-over-period analysis ("how did X develop?", "compare this month to last month", "pipeline trend this quarter"). For comparison viz:
- The main sql can be a simple SELECT 1 (it is not displayed — the context KPIs ARE the visualization)
- Provide 3-6 context KPIs, each with previous_sql, covering the key metrics for the topic
- Each KPI becomes a prominent comparison card showing current value, previous value, and delta %
- Choose metrics that tell a complete story (e.g. for pipeline: deals created, deals won, win rate, total revenue, avg deal size, avg cycle time)

Choose viz type based on the result shape:
- "number": single aggregate value (one row, one column)
- "table": multi-column detail data (deal lists, breakdowns with many columns)
- "bar": category comparison (GROUP BY with label + value columns)
- "line": time series (GROUP BY date period, ordered chronologically)
- "funnel": ordered stage progression (pipeline stages, lifecycle stages)
- "comparison": period-over-period analysis with multiple metrics showing deltas (use context KPIs with previous_sql)"""


def _get_pk_type(meta: dict) -> str:
    """Infer PK type — always String in our schema."""
    return "String"
