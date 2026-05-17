"""ClickHouse-native PII masking expressions for the anon silver/gold layer.

Emits SQL snippets that transform a column value into a fixed-width masked
form. Fixed-width `***` per token (not one asterisk per character) so the
reader cannot guess the original length from the mask width.

Semantics:
- text:  `"Alice Anderson"` -> `"A*** A***"`   (per-word first char + `***`)
- email: `"alice.anderson@example.com"` -> `"a***.a***@e***.com"` (per segment, TLD kept)
- phone: `"+33 6 12 34 56 78"` -> `"+*** *** *** *** *** ***"` (digit runs -> `***`)

Empty/NULL inputs round-trip unchanged.
"""

from __future__ import annotations

MASK_TOKEN = "'***'"


def _mask_text_sql(col: str) -> str:
    return (
        "arrayStringConcat("
        f"arrayMap(w -> concat(substring(w, 1, 1), {MASK_TOKEN}), "
        f"splitByChar(' ', trim({col}))), ' ')"
    )


def _mask_email_sql(col: str) -> str:
    # Split local and domain; if no '@', fall back to text masking.
    local = f"splitByChar('@', {col})[1]"
    domain = f"splitByChar('@', {col})[2]"
    domain_parts = f"splitByChar('.', {domain})"
    # Mask every local-part segment (dot-split) and every domain segment except
    # the last one (the TLD), which is preserved verbatim.
    masked_local = (
        "arrayStringConcat("
        f"arrayMap(p -> concat(substring(p, 1, 1), {MASK_TOKEN}), "
        f"splitByChar('.', {local})), '.')"
    )
    masked_domain_head = (
        "arrayStringConcat("
        f"arrayMap(p -> concat(substring(p, 1, 1), {MASK_TOKEN}), "
        f"arraySlice({domain_parts}, 1, length({domain_parts}) - 1)), '.')"
    )
    tld = f"arrayElement({domain_parts}, -1)"
    email_expr = (
        "concat("
        f"{masked_local}, '@', "
        f"if(length({domain_parts}) > 1, concat({masked_domain_head}, '.', {tld}), "
        f"concat(substring({domain}, 1, 1), {MASK_TOKEN}))"
        ")"
    )
    # If the column has no '@', there's only one segment → mask as text.
    return f"if(position({col}, '@') = 0, {_mask_text_sql(col)}, {email_expr})"


def _mask_phone_sql(col: str) -> str:
    # Collapse each run of digits into a single '***' so digit-count isn't leaked.
    return f"replaceRegexpAll({col}, '[0-9]+', '***')"


_KIND_TO_BUILDER = {
    "text":  _mask_text_sql,
    "email": _mask_email_sql,
    "phone": _mask_phone_sql,
}


def mask_column(col: str, kind: str) -> str:
    """Return a ClickHouse SQL expression that masks `col` according to `kind`.

    Wraps the mask in `if(empty(col), col, <mask>)` so NULL/empty inputs round
    trip untouched (nullability of the source column is preserved).
    """
    if kind not in _KIND_TO_BUILDER:
        raise ValueError(f"Unknown mask kind: {kind!r} (want one of {sorted(_KIND_TO_BUILDER)})")
    mask_expr = _KIND_TO_BUILDER[kind](col)
    return f"if(empty({col}), {col}, {mask_expr})"
