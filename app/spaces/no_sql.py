"""No-SQL → SQL derivation for the Data Space designer.

The no-SQL UI emits *structured intent* (filter builders + computed presets);
this module derives the raw ClickHouse SQL strings the generator already
consumes. Nothing in `generator.py` changes — we just fill `grain.filter`,
`default_filter`, and `computed[].expr` before the view is generated.

Design notes:
- Filters reuse the battle-tested sqlglot translator in `space_filter`
  (`_build_condition`) — no hand-rolled SQL, no injection surface.
- Grain filters run on the raw `silver.X` subquery → **bare** column names.
  Default filters run on the outer view → **`grain.`-aliased** columns.
- Structured fields are the source of truth: when a `*_builder` / `preset`
  is present we (re)derive; when absent we leave the raw SQL untouched, so
  legacy/raw spaces and the Advanced escape hatch keep working unchanged.
"""

from __future__ import annotations

import re

from sqlglot import exp

from app.spaces.config import ComputedPreset, DataSpaceConfig, FilterCondition
from app.spaces.space_filter import SpaceFilter, _build_condition

# Default age-bucket thresholds (days for date base, raw value for number base).
_DEFAULT_THRESHOLDS = [30, 90, 180]


# ---------------------------------------------------------------------------
# Filter builder → WHERE string
# ---------------------------------------------------------------------------

def build_where(filters: list[FilterCondition], alias: str | None) -> str | None:
    """Combine structured filter conditions into a single ClickHouse WHERE
    expression string (without the leading WHERE), or None if empty.

    `alias=None`   → bare columns (grain filter, runs on `silver.X`).
    `alias="grain"`→ `grain.<col>` columns (default filter, runs on the view).
    """
    conditions: list[exp.Expression] = []
    for fc in filters:
        sf = SpaceFilter(column=fc.column, operator=fc.operator, values=list(fc.values))
        cond = _build_condition(sf, alias)
        if cond is not None:
            conditions.append(cond)

    if not conditions:
        return None

    combined = conditions[0]
    for cond in conditions[1:]:
        combined = exp.And(this=combined, expression=cond)
    return combined.sql(dialect="clickhouse")


# ---------------------------------------------------------------------------
# Computed preset → expression string
# ---------------------------------------------------------------------------

def _slug(value: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower())
    return s.strip("_") or "value"


def _q(value: str) -> str:
    """Single-quote-escape a string literal for ClickHouse."""
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def default_alias(preset: ComputedPreset) -> str:
    """The sensible default output alias for a preset (user-overridable)."""
    p = preset.params or {}
    column = p.get("column", "")
    kind = preset.kind
    if kind == "days_since":
        return f"days_since_{column}"
    if kind == "age_bucket":
        return f"{column}_bucket"
    if kind == "flag_equals":
        label = p.get("label") or (p.get("values") or [""])[0]
        return f"is_{_slug(str(label))}"
    if kind == "quarter":
        return f"{column}_quarter"
    if kind == "month":
        return f"{column}_month"
    return "computed"


def expand_preset(preset: ComputedPreset) -> str:
    """Expand a `{kind, params}` preset into a ClickHouse expression.

    All presets reference grain columns as `grain.<col>` (outer-SELECT scope,
    matching the existing computed-column convention).
    """
    p = preset.params or {}
    column = p.get("column", "")
    if not column:
        raise ValueError(f"Preset '{preset.kind}' requires a 'column' param")
    gcol = f"grain.{column}"

    if preset.kind == "days_since":
        return f"dateDiff('day', {gcol}, today())"

    if preset.kind == "age_bucket":
        base_kind = p.get("base", "date")
        base = f"dateDiff('day', {gcol}, today())" if base_kind == "date" else gcol
        raw_thresholds = p.get("thresholds") or _DEFAULT_THRESHOLDS
        thresholds = [int(t) for t in raw_thresholds]
        if not thresholds:
            thresholds = list(_DEFAULT_THRESHOLDS)
        # Labels: 0–t0, t0–t1, …, t(n-1)+
        branches: list[str] = []
        prev = 0
        for t in thresholds:
            branches.append(f"{base} < {t}, {_q(f'{prev}–{t}')}")
            prev = t
        args = ", ".join(branches)
        return f"multiIf({args}, {_q(f'{prev}+')})"

    if preset.kind == "flag_equals":
        values = p.get("values") or []
        if not values:
            raise ValueError("Preset 'flag_equals' requires at least one value")
        in_list = ", ".join(_q(v) for v in values)
        return f"if({gcol} IN ({in_list}), 1, 0)"

    if preset.kind == "quarter":
        return (
            f"concat(toString(toYear({gcol})), '-Q', "
            f"toString(toQuarter({gcol})))"
        )

    if preset.kind == "month":
        return f"formatDateTime({gcol}, '%Y-%m')"

    raise ValueError(f"Unknown computed preset kind: {preset.kind}")


# ---------------------------------------------------------------------------
# Top-level derivation — mutate config in place before view generation
# ---------------------------------------------------------------------------

def derive_sql(config: DataSpaceConfig) -> DataSpaceConfig:
    """Fill the raw SQL strings the generator consumes from structured intent.

    Mutates and returns `config`. Called at the start of create/update/preview
    so the generator stays oblivious to the no-SQL layer. A `*_builder` of `[]`
    clears the corresponding raw filter; `None` leaves the raw SQL untouched
    (Advanced / legacy spaces).
    """
    # Grain filter — bare columns on the silver subquery.
    if config.grain.filter_builder is not None:
        config.grain.filter = build_where(config.grain.filter_builder, alias=None)

    # Default filter — grain.<col> columns on the outer view.
    if config.default_filter_builder is not None:
        config.default_filter = build_where(config.default_filter_builder, alias="grain")

    # Computed presets → expr.
    for comp in config.computed:
        if comp.preset is not None:
            comp.expr = expand_preset(comp.preset)
            if not comp.alias:
                comp.alias = default_alias(comp.preset)

    return config
