"""Schema prompt builder — generates the LLM system prompt from config + semantic layer.

The prompt is the most critical component for SQL accuracy. It's built from:
1. app/config.py TABLES dict — table structure, columns, types
2. Semantic layer — HubSpot property labels, descriptions, enum options
3. Data model (ERD) — entity relationships from dbt_hubspot patterns
4. Dictionaries — in-memory lookups for ID→name resolution
5. COMPUTED_METRICS — reference SQL patterns
6. Few-shot examples
"""

from app.config import TABLES, GRAPH_EDGES, REFERENCE_JOINS
from app.engine.metrics import COMPUTED_METRICS
from app.engine.sql_builder import _table_ref, _table_final, _archived_condition
from app.semantic.layer import SemanticLayer


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
- Silver tables (silver.*): always append FINAL after the table name. Always filter `archived = 0`.
- Gold tables (gold.*): do NOT use FINAL. No archived column exists. Gold columns are pre-aggregated at their grain (e.g. monthly per rep). When re-aggregating (e.g. yearly from monthly), NEVER alias an aggregate with the same name as the source column — ClickHouse resolves aliases within SELECT and `sum(deals_won) AS deals_won` then `sum(deals_won)` elsewhere becomes `sum(sum(...))` which is illegal. Use distinct aliases like `total_deals_won`.
- DateTime fields with value '1970-01-01 00:00:00' mean "not set" — filter with `> '1970-01-02'` to exclude them.
- String boolean fields (hs_is_closed_won, hs_is_closed) use 'true'/'false' strings, not actual booleans.
- Currency is EUR. Format amounts as numbers, the frontend handles display formatting.
- Always include LIMIT (max 1000 for tables, not needed for single-value aggregates).
- Use ClickHouse functions: countIf(), sumIf(), avgIf(), toDate(), toStartOfMonth(), toStartOfQuarter(), toStartOfYear(), dateDiff().
- For date bucketing use: toDate(), toStartOfWeek(), toStartOfMonth(), toStartOfQuarter(), toStartOfYear().
- When the user says "this quarter", compute the current calendar quarter boundaries.
- Use dictGet() for ID→name lookups instead of JOINs (see DICTIONARIES section).
- Filter out blank/empty names: WHERE owner_name != '' AND owner_name != ' ' (similar for other name fields).
- When the user says "by X" or "per X", the SQL MUST actually GROUP BY that dimension. The explanation must match what the SQL does — never claim a breakdown that isn't in the query."""


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
  ACTIVITIES (silver.fact_activities) — Calls, meetings, emails, notes, tasks.
    activity_type column discriminates type: 'call', 'meeting', 'email', 'note', 'task'.
    "By type" means GROUP BY activity_type or pivot with countIf(activity_type = '...').
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

Gold layer (pre-aggregated, no FINAL needed):
  gold.agg_rep_performance — Monthly per-rep aggregates (hubspot_owner_id, period_start)
  gold.agg_deal_health — Per-deal health indicators (deal_id, hubspot_owner_id, dealstage, pipeline, hs_is_closed, hs_is_closed_won)
  gold.agg_source_attribution — Source/channel attribution metrics
  gold.fact_pipeline_snapshots — Historical pipeline state

IMPORTANT: gold tables store RAW IDs, not human names. Use dictGet() to resolve."""


def _block_dictionaries() -> str:
    return """DICTIONARIES (in-memory lookups — use instead of JOINs for ID→name resolution):
These are ClickHouse dictionaries backed by silver tables. They are fast (in-memory hash lookup, no JOIN overhead).

Available dictionaries and their fields:
  silver.dict_owners(owner_id) → first_name, last_name, email
  silver.dict_pipelines(pipeline_id) → label
  silver.dict_pipeline_stages(stage_id) → label, pipeline_id, is_closed, display_order
  silver.dict_contacts(contact_id) → full_name, email
  silver.dict_companies(company_id) → name, domain, industry
  silver.dict_deals(deal_id) → dealname, amount, owner_name

Syntax — always wrap the key in tuple():
  dictGet('silver.dict_owners', 'first_name', tuple(hubspot_owner_id))
  dictGet('silver.dict_owners', 'last_name', tuple(hubspot_owner_id))
  dictGet('silver.dict_pipelines', 'label', tuple(pipeline))
  dictGet('silver.dict_pipeline_stages', 'label', tuple(dealstage))
  dictGet('silver.dict_contacts', 'full_name', tuple(contact_id))
  dictGet('silver.dict_companies', 'name', tuple(company_id))

Full rep name pattern:
  dictGet('silver.dict_owners', 'first_name', tuple(hubspot_owner_id)) || ' ' || dictGet('silver.dict_owners', 'last_name', tuple(hubspot_owner_id)) AS rep_name

WHEN TO USE:
- Gold tables (agg_rep_performance, agg_deal_health): ALWAYS use dictGet() for hubspot_owner_id, pipeline, dealstage
- Bridge tables: use dictGet() to resolve contact_id, company_id, deal_id to names
- Silver dim_deals: has denormalized owner_name, pipeline_label, stage_label — use those directly, no dictGet needed"""


def _block_tables(semantic_layer: SemanticLayer | None) -> str:
    lines = ["TABLES AND COLUMNS:"]

    for table_name, meta in TABLES.items():
        db = meta.get("database", "silver")
        ref = f"{db}.{table_name}"
        final = _table_final(table_name)
        archived = _archived_condition(table_name)
        pk = meta["primary_key"]
        display = meta["display_name"]

        lines.append(f"\n{ref} — {display}")
        if final:
            lines.append(f"  Use: SELECT ... FROM {ref} FINAL WHERE {archived}")
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
            desc = ""
            options_str = ""
            if sem_table and field_name in sem_table.properties:
                prop = sem_table.properties[field_name]
                if prop.description:
                    desc = f" — {prop.description}"
                if prop.options:
                    vals = ", ".join(o["value"] for o in prop.options[:10])
                    options_str = f" [values: {vals}]"

            lines.append(f"  {field_name} {ch_type} — \"{display_name}\"{desc}{options_str}")

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
            f"  {from_t} <-> {to_t}: JOIN silver.{bridge} FINAL ON {from_key}, {to_key}"
        )

    lines.append("\nFK joins (direct column match — prefer dictGet() over JOIN):")
    for ref in REFERENCE_JOINS:
        lines.append(
            f"  {ref['from']}.{ref['from_col']} -> {ref['to']}.{ref['to_col']}"
        )

    return "\n".join(lines)


def _block_metrics() -> str:
    lines = ["REFERENCE SQL PATTERNS (battle-tested, use these for common metrics):"]
    for name, m in COMPUTED_METRICS.items():
        lines.append(f"  {m['label']}: SELECT {m['sql']} FROM {_table_ref(m['table'])} ...")
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
For gold tables use the pipeline ID: pipeline = 'default'

STAGES (main pipeline, in order):
  "Discovery" → "Scoping" → "Proof of Value" → "Contract & Negotiation" → "Closed Won" (Closed Won) / "Closed Lost" (Closed Lost) / "Disqualified"

OTHER CONTEXT:
- dim_deals has denormalized columns: pipeline_label (human name), stage_label (human name), owner_name (rep full name)
- hs_manual_forecast_category values: COMMIT, BEST_CASE, MOST_LIKELY, PIPELINE, OMIT
- gold.agg_rep_performance: keyed by hubspot_owner_id + period_start. Use dictGet for rep names.
- gold.agg_deal_health: keyed by deal_id, has hubspot_owner_id, dealstage, pipeline (all raw IDs). Use dictGet for names.
  IMPORTANT: agg_deal_health contains ALL deals (open AND closed). When the user asks about "open" deals, stale deals, or at-risk deals, filter: hs_is_closed = 'false'"""


def _block_examples() -> str:
    return """FEW-SHOT EXAMPLES:

Q: "What's our win rate this quarter?"
A: {"sql": "SELECT countIf(hs_is_closed_won = 'true') * 1.0 / nullIf(countIf(hs_is_closed = 'true'), 0) AS win_rate FROM silver.dim_deals FINAL WHERE archived = 0 AND pipeline_label = 'Main Sales Pipeline' AND closedate >= '2026-04-01' AND closedate <= '2026-06-30' AND closedate > '1970-01-02'", "viz": "number", "title": "Win Rate Q2 2026", "explanation": "Win rate for main pipeline deals closed in Q2 2026."}

Q: "Break that down by rep"
A: {"sql": "SELECT owner_name, countIf(hs_is_closed_won = 'true') * 1.0 / nullIf(countIf(hs_is_closed = 'true'), 0) AS win_rate, countIf(hs_is_closed = 'true') AS total_closed FROM silver.dim_deals FINAL WHERE archived = 0 AND pipeline_label = 'Main Sales Pipeline' AND closedate >= '2026-04-01' AND closedate <= '2026-06-30' AND closedate > '1970-01-02' AND owner_name != ' ' GROUP BY owner_name ORDER BY win_rate DESC LIMIT 20", "viz": "bar", "title": "Win Rate by Rep — Q2 2026", "explanation": "Win rate per rep for main pipeline deals closed in Q2 2026."}

Q: "Which deals are at risk?"
A: {"sql": "SELECT dealname, dictGet('silver.dict_owners', 'first_name', tuple(hubspot_owner_id)) || ' ' || dictGet('silver.dict_owners', 'last_name', tuple(hubspot_owner_id)) AS rep, amount, days_in_current_stage, days_since_last_activity, last_activity_type FROM gold.agg_deal_health WHERE hs_is_closed = 'false' AND is_stale = 1 AND pipeline = 'default' AND amount > 0 ORDER BY amount DESC LIMIT 50", "viz": "table", "title": "Stale Deals at Risk", "explanation": "Open stale deals in the main pipeline with no recent activity, sorted by value."}

Q: "Show me monthly closed-won revenue for the last 12 months"
A: {"sql": "SELECT toStartOfMonth(closedate) AS month, sum(amount) AS revenue FROM silver.dim_deals FINAL WHERE archived = 0 AND pipeline_label = 'Main Sales Pipeline' AND hs_is_closed_won = 'true' AND closedate >= toDate(now()) - INTERVAL 12 MONTH AND closedate > '1970-01-02' GROUP BY month ORDER BY month LIMIT 12", "viz": "line", "title": "Monthly Closed-Won Revenue", "explanation": "Monthly closed-won revenue from the main sales pipeline."}

Q: "Pipeline by stage"
A: {"sql": "SELECT stage_label, count() AS deals, sum(amount) AS total_value FROM silver.dim_deals FINAL WHERE archived = 0 AND (hs_is_closed = 'false' OR hs_is_closed = '') AND pipeline_label = 'Main Sales Pipeline' GROUP BY stage_label ORDER BY total_value DESC LIMIT 20", "viz": "bar", "title": "Open Pipeline by Stage", "explanation": "Open deals in the main sales pipeline grouped by stage."}

Q: "Top reps by ARR this month"
A: {"sql": "SELECT dictGet('silver.dict_owners', 'first_name', tuple(hubspot_owner_id)) || ' ' || dictGet('silver.dict_owners', 'last_name', tuple(hubspot_owner_id)) AS rep, deals_won, total_arr_closed, win_rate FROM gold.agg_rep_performance WHERE period_start = toStartOfMonth(today()) ORDER BY total_arr_closed DESC NULLS LAST LIMIT 10", "viz": "bar", "title": "Top Reps by ARR This Month", "explanation": "Rep leaderboard by new ARR closed this month."}

Q: "Compare all pipelines"
A: {"sql": "SELECT pipeline_label, count() AS deals, sum(amount) AS total_value, countIf(hs_is_closed_won = 'true') AS won FROM silver.dim_deals FINAL WHERE archived = 0 GROUP BY pipeline_label ORDER BY total_value DESC LIMIT 10", "viz": "bar", "title": "All Pipelines Comparison", "explanation": "Deal count and total value across all pipelines."}"""


def _block_output_format() -> str:
    return """RESPONSE FORMAT:
Return a JSON object with these fields:
- sql: The ClickHouse SQL query (string)
- viz: Visualization type — one of: "number", "table", "bar", "line", "funnel"
- title: Short chart/table title (max 10 words)
- explanation: One sentence explaining what the query shows
- context: Array of 2-4 contextual KPI queries (optional but encouraged). Each item has:
    - sql: A simple SELECT that returns exactly 1 row, 1 column (a single number)
    - label: Short KPI label (e.g. "Total Deals", "Avg Deal Size", "Win Rate")

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

Choose viz type based on the result shape:
- "number": single aggregate value (one row, one column)
- "table": multi-column detail data (deal lists, breakdowns with many columns)
- "bar": category comparison (GROUP BY with label + value columns)
- "line": time series (GROUP BY date period, ordered chronologically)
- "funnel": ordered stage progression (pipeline stages, lifecycle stages)"""


def _get_pk_type(meta: dict) -> str:
    """Infer PK type — always String in our schema."""
    return "String"
