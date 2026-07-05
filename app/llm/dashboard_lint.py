"""Deterministic post-plan composition lint for the One Shot Dashboard (CLI-161 / plan C2).

After the planner returns a dashboard (CLI-155 / C1 gave every widget a ``role``)
and each widget's SQL has been validated and executed, we check the *composition*
in code — not vibes — against the same grammar the prompt asks for:

  * viz/role coherence  — a ``kpi`` widget must render as a ``number``, a ``trend``
                          as a ``line``, etc. (:func:`viz_role_warning`)
  * cardinality         — a ``bar`` with > 12 categories is unreadable; a ``number``
                          that returns != 1 row is not a stat tile. We already pay
                          for the validation run, so the row count is free
                          (:func:`cardinality_repair_instruction` / :func:`cardinality_violation`)
  * duplicate analysis  — two widgets grouping by the same column(s) on the same
                          measure add no perspective (:func:`find_duplicate_analyses`)
  * composition counts  — a KPI band (2–4), 2–4 breakdowns, <= 1 detail table,
                          <= 1 flow, a single lead trend (:func:`composition_warnings`)

Cardinality violations feed the existing bounded self-repair loop (see
``dashboard_spec._finalize_widget``); anything still wrong after that — plus the
structural checks a SQL rewrite can't fix — surfaces as a widget/board *warning*,
so the board never renders a silently-bad chart.

Every function here is a pure, deterministic data transform with no I/O, so the
checks are trivially unit-testable through the existing fake-provider/fake-runner
seams.
"""

from __future__ import annotations

import re
from collections import Counter

# A bar chart beyond this many categories is unreadable — rewrite to top-N or demote
# to a table (the per-viz SQL shape contract in the C1 prompt asks for LIMIT 12).
MAX_BAR_ROWS = 12

# A headline KPI band is 2–4 stat tiles (matches the C1 composition grammar).
KPI_BAND_MIN = 2
KPI_BAND_MAX = 4

# The board should carry 2–4 breakdowns ("Include 2–4 breakdowns." in the C1
# composition grammar) — a board with none has no analysis, one with many is noise.
BREAKDOWN_MIN = 2
BREAKDOWN_MAX = 4

# The viz type(s) each role may legitimately render as. ``breakdown`` allows a table
# as the many-category fallback the grammar sanctions (and the cardinality demotion
# below produces one). Roles absent here are unknown — the WidgetPlan schema already
# rejects those, so no coherence warning is emitted for them.
_ROLE_VIZ: dict[str, tuple[str, ...]] = {
    "kpi": ("number",),
    "trend": ("line",),
    "breakdown": ("bar", "table"),
    "flow": ("funnel",),
    "detail": ("table",),
}


def viz_role_warning(role: str, viz_type: str) -> str | None:
    """Return a warning if ``viz_type`` is incoherent with ``role``, else ``None``."""
    allowed = _ROLE_VIZ.get(role)
    if allowed is None or viz_type in allowed:
        return None
    expected = " or ".join(f"'{v}'" for v in allowed)
    return f"Role '{role}' should render as {expected}, not '{viz_type}'."


def cardinality_repair_instruction(viz_type: str, row_count: int | None) -> str | None:
    """A steering instruction for the self-repair loop when a result's shape is wrong
    for its viz, or ``None`` when the cardinality is fine (or unknown).

    Only the two deterministic, high-signal cases from the C2 spec: an over-wide bar
    and a multi-row ``number``.
    """
    if row_count is None:
        return None
    if viz_type == "bar" and row_count > MAX_BAR_ROWS:
        return (
            f"This bar chart returned {row_count} categories, which is unreadable. "
            f"Rewrite it to the top {MAX_BAR_ROWS} by the measure "
            f"(`ORDER BY <measure> DESC LIMIT {MAX_BAR_ROWS}`); fold the long tail "
            "into an 'Other' bucket if it makes sense."
        )
    if viz_type == "number" and row_count != 1:
        return (
            f"This is a single-value KPI but the query returned {row_count} rows. "
            "Rewrite it to return EXACTLY ONE ROW with a single aggregate value and "
            "no GROUP BY."
        )
    return None


def cardinality_violation(viz_type: str, row_count: int | None) -> str | None:
    """The same predicate as :func:`cardinality_repair_instruction`, phrased as a
    short residual *warning* fragment for when repair could not fix the shape."""
    if row_count is None:
        return None
    if viz_type == "bar" and row_count > MAX_BAR_ROWS:
        return f"returned {row_count} categories (a bar is unreadable beyond {MAX_BAR_ROWS})"
    if viz_type == "number" and row_count != 1:
        return f"returned {row_count} rows (a KPI needs exactly 1)"
    return None


# ---------------------------------------------------------------------------
# Duplicate-analysis detection
# ---------------------------------------------------------------------------

# Aggregate functions that mark a column as a *measure* rather than a dimension.
_AGG_RE = re.compile(
    r"\b(?:count|sum|avg|min|max|median|any|anyLast|argMin|argMax|"
    r"uniq\w*|countDistinct|quantile\w*|stddev\w*|var\w*|corr|covar\w*)\s*\([^()]*\)",
    re.IGNORECASE,
)
_SELECT_RE = re.compile(r"\bselect\b(.*?)\bfrom\b", re.IGNORECASE | re.DOTALL)
_GROUP_BY_RE = re.compile(
    r"\bgroup\s+by\b(.*?)(?:\border\s+by\b|\bhaving\b|\blimit\b|\bsettings\b|$)",
    re.IGNORECASE | re.DOTALL,
)


def _norm(expr: str) -> str:
    """Normalise a SQL fragment for equality: lowercase, whitespace-collapsed."""
    return re.sub(r"\s+", "", expr).lower()


def analysis_signature(sql: str) -> tuple[frozenset[str], frozenset[str]] | None:
    """A ``(group-by columns, measures)`` fingerprint of a grouped analysis.

    Returns ``None`` for queries with no ``GROUP BY`` (e.g. single-value KPIs), which
    are never counted as duplicates. Deterministic and heuristic — good enough to
    catch "same breakdown twice", not a full SQL parser.
    """
    gb_match = _GROUP_BY_RE.search(sql)
    if not gb_match:
        return None
    group_cols = frozenset(
        _norm(c) for c in gb_match.group(1).split(",") if _norm(c)
    )
    if not group_cols:
        return None
    select_body = _SELECT_RE.search(sql)
    scope = select_body.group(1) if select_body else sql
    measures = frozenset(_norm(m.group(0)) for m in _AGG_RE.finditer(scope))
    return group_cols, measures


def find_duplicate_analyses(sqls: list[str]) -> list[list[int]]:
    """Group indices of widgets that share an identical grouped-analysis signature.

    Returns one list of indices per duplicated signature (each list has >= 2 entries,
    in ascending index order); widgets with no ``GROUP BY`` are ignored.
    """
    by_sig: dict[tuple[frozenset[str], frozenset[str]], list[int]] = {}
    for i, sql in enumerate(sqls):
        sig = analysis_signature(sql)
        if sig is None:
            continue
        by_sig.setdefault(sig, []).append(i)
    return [idxs for idxs in by_sig.values() if len(idxs) > 1]


# ---------------------------------------------------------------------------
# Board-level composition counts
# ---------------------------------------------------------------------------

def composition_warnings(roles: list[str]) -> list[str]:
    """Board-level warnings when role counts violate the composition grammar."""
    counts = Counter(roles)
    out: list[str] = []

    kpi = counts.get("kpi", 0)
    if kpi == 0:
        out.append(
            f"No KPI band: lead with {KPI_BAND_MIN}–{KPI_BAND_MAX} headline 'number' widgets."
        )
    elif kpi < KPI_BAND_MIN:
        out.append(
            f"Only {kpi} KPI widget: a headline band should be {KPI_BAND_MIN}–{KPI_BAND_MAX}."
        )
    elif kpi > KPI_BAND_MAX:
        out.append(
            f"{kpi} KPI widgets: a headline band should be {KPI_BAND_MIN}–{KPI_BAND_MAX}."
        )

    breakdown = counts.get("breakdown", 0)
    if breakdown == 0:
        out.append(
            f"No breakdowns: add {BREAKDOWN_MIN}–{BREAKDOWN_MAX} category breakdowns "
            "so the board explains the KPIs."
        )
    elif breakdown < BREAKDOWN_MIN:
        out.append(
            f"Only {breakdown} breakdown: aim for {BREAKDOWN_MIN}–{BREAKDOWN_MAX} to cover the drivers."
        )
    elif breakdown > BREAKDOWN_MAX:
        out.append(
            f"{breakdown} breakdowns: trim to {BREAKDOWN_MIN}–{BREAKDOWN_MAX} so the board stays focused."
        )

    detail = counts.get("detail", 0)
    if detail > 1:
        out.append(f"{detail} detail tables: keep at most one full-width table, placed last.")

    flow = counts.get("flow", 0)
    if flow > 1:
        out.append(f"{flow} funnels: at most one staged-process funnel.")

    trend = counts.get("trend", 0)
    if trend > 1:
        out.append(f"{trend} trend lines: lead with a single primary time trend.")

    return out
