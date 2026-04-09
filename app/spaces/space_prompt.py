"""Focused LLM schema prompt for a single data space VIEW.

Self-contained prompt that only references columns available in the VIEW.
Does NOT reuse _block_business_context or _block_dictionaries since those
reference columns that may not exist in the VIEW, causing the LLM to
generate invalid SQL (e.g. using `createdate` when only `deal_createdate` exists).
"""

from app.config import TABLES
from app.llm.schema_prompt import (
    _block_output_format,
)
from app.spaces.config import DataSpaceConfig


def _block_space_rules(config: DataSpaceConfig) -> str:
    """Rules scoped to a data space VIEW — no references to other tables."""
    view = config.view_name
    return f"""You are a ClickHouse SQL expert. Given a natural language question, generate a ClickHouse SQL query against the data space VIEW: {view}

CRITICAL RULES:
- You may ONLY query: {view}
- You may ONLY reference columns listed in the COLUMNS section below. If a column is not listed, it DOES NOT EXIST.
- Do NOT reference any other tables (silver.*, gold.*, etc.) — this VIEW has everything pre-joined.
- Do NOT use dictGet() — all labels are already resolved in the VIEW.
- Generate ONLY SELECT queries. Never INSERT, UPDATE, DELETE, DROP, CREATE, ALTER.
- No FINAL needed — the VIEW has no duplicates.
- DateTime fields with value '1970-01-01 00:00:00' mean "not set" — filter with `> '1970-01-02'` to exclude them.
- String boolean fields (hs_is_closed_won, hs_is_closed, etc.) use 'true'/'false' strings, not actual booleans.
- Currency is EUR. Format amounts as numbers.
- Always include LIMIT (max 1000 for tables, not needed for single-value aggregates).
- Use ClickHouse functions: countIf(), sumIf(), avgIf(), toDate(), toStartOfMonth(), toStartOfQuarter(), toStartOfYear(), dateDiff().
- ALWAYS use relative date expressions (today(), toStartOfMonth(today()), etc.) — NEVER hardcode dates.
- NEVER wrap columns in functions inside WHERE — use range predicates:
    GOOD: WHERE col >= toStartOfYear(today()) AND col < today() + 1
    BAD:  WHERE toYear(col) = 2026
- Filter out blank/empty names: WHERE col != '' AND col != ' '
- NEVER use SELECT * — always enumerate columns explicitly.
- Use uniq() instead of COUNT(DISTINCT ...).
- SUBQUERY ALIASES ARE REQUIRED: FROM (SELECT ...) AS sub
- Table aliases: NEVER use single-letter aliases."""


def _block_space_columns(config: DataSpaceConfig) -> str:
    """Document ALL and ONLY the columns available in the VIEW."""
    view = config.view_name
    lines = [
        f"COLUMNS IN {view}:",
        f"  Query as: SELECT ... FROM {view}",
        f"  Primary key: {config.grain.key}",
        "",
    ]

    # Collect all column names for the reminder
    all_cols: list[str] = [config.grain.key]

    # Grain columns
    grain_meta = TABLES.get(config.grain.entity, {})
    grain_fields = grain_meta.get("fields", {})

    lines.append(f"  {config.grain.key} String (PK)")

    for col in config.grain.columns:
        fm = grain_fields.get(col, {})
        ch_type = fm.get("type", "String")
        display = fm.get("display", col)
        lines.append(f"  {col} {ch_type} — \"{display}\"")
        all_cols.append(col)

    # Dimension columns (prefixed)
    for dim in config.dimensions:
        dim_meta = TABLES.get(dim.entity, {})
        dim_fields = dim_meta.get("fields", {})
        for col in dim.columns:
            fm = dim_fields.get(col, {})
            ch_type = fm.get("type", "String")
            display = fm.get("display", col)
            prefixed = f"{dim.prefix}{col}"
            lines.append(f"  {prefixed} {ch_type} — \"{display} ({dim.prefix.rstrip('_')})\"")
            all_cols.append(prefixed)

    # Computed columns
    for comp in config.computed:
        lines.append(f"  {comp.alias} computed — \"{comp.alias}\"")
        all_cols.append(comp.alias)

    if config.default_filter:
        lines.append(f"\n  NOTE: This VIEW has a built-in filter: {config.default_filter}")
        lines.append("  You do NOT need to add this filter in your queries.")

    lines.append("")
    lines.append(f"THESE ARE THE ONLY COLUMNS THAT EXIST: {', '.join(all_cols)}")
    lines.append("If a column name is not in this list, DO NOT use it. The query WILL fail.")

    return "\n".join(lines)


def build_space_prompt(config: DataSpaceConfig) -> str:
    """Build a focused schema prompt for a single data space."""
    blocks = [
        _block_space_rules(config),
        _block_space_columns(config),
        _block_output_format(),
    ]
    return "\n\n".join(blocks)
