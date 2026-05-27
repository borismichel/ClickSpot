"""Client-safe ClickHouse error messages for the user query path.

Every interactive query path (chat, SQL editor, Data Spaces, MCP) runs through
``safe_clickhouse_error`` before showing a failure to the user. Two jobs:

1. **Sanitize.** Raw clickhouse_connect exceptions embed the server version,
   file paths, host:port and internal table names. We surface only the numeric
   ``Code: N`` and the error class (e.g. ``UNKNOWN_TABLE``) — never the full
   message. The full text still goes to the server log.
2. **Translate.** A few classes get a friendly, actionable message instead of a
   bare code, because a RevOps user can act on them (CLI-124). Memory and
   timeout limits are guardrails (``max_memory_usage`` 2 GB,
   ``max_execution_time``); the fix is to scan less data, not to retry.

ClickHouse error messages look like:
    "Code: 60. DB::Exception: Received from localhost:9000. DB::Exception:
     Table silver.dim_foo doesn't exist. (UNKNOWN_TABLE) (version 26.2.5.45)"
"""

import re

_CH_ERROR_CODE_RE = re.compile(r"Code:\s*(\d+)")
_CH_ERROR_CLASS_RE = re.compile(r"\(([A-Z_][A-Z0-9_]*)\)")

# Friendly, actionable text for the guardrail failures a user can actually fix.
# Keyed by both numeric code and class name so a match on either is enough — the
# code is the most robust signal, the class name is the backstop.
_MEMORY_LIMIT_MSG = (
    "This query needs more memory than the per-query limit allows. Try "
    "narrowing the date range, adding filters, or summarising with GROUP BY "
    "so it scans less data."
)
_TIMEOUT_MSG = (
    "This query ran longer than the time limit and was stopped. Try narrowing "
    "the date range or adding filters so it scans less data."
)

_FRIENDLY_BY_CODE = {
    "241": _MEMORY_LIMIT_MSG,  # MEMORY_LIMIT_EXCEEDED
    "159": _TIMEOUT_MSG,       # TIMEOUT_EXCEEDED
}
_FRIENDLY_BY_CLASS = {
    "MEMORY_LIMIT_EXCEEDED": _MEMORY_LIMIT_MSG,
    "TIMEOUT_EXCEEDED": _TIMEOUT_MSG,
}


def safe_clickhouse_error(exc: Exception) -> str:
    """Convert a clickhouse_connect exception into a short client-safe message.

    Returns a friendly sentence for the guardrail failures users can act on
    (out-of-memory, timeout), an ``ClickHouse error <code>: <class>`` summary
    for everything else, and a generic fallback when nothing useful can be
    extracted. Never returns the raw exception text — full details stay in the
    server-side log.
    """
    msg = str(exc)
    code = _CH_ERROR_CODE_RE.search(msg)
    klass = _CH_ERROR_CLASS_RE.search(msg)
    code_s = code.group(1) if code else None
    klass_s = klass.group(1) if klass else None

    if code_s and code_s in _FRIENDLY_BY_CODE:
        return _FRIENDLY_BY_CODE[code_s]
    if klass_s and klass_s in _FRIENDLY_BY_CLASS:
        return _FRIENDLY_BY_CLASS[klass_s]

    if code_s and klass_s:
        return f"ClickHouse error {code_s}: {klass_s}"
    if klass_s:
        return f"ClickHouse error: {klass_s}"
    return "Query execution failed"
