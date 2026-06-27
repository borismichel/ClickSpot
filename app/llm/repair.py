"""SQL self-repair loop + EXPLAIN dry-run helpers (CLI-144).

When the NL->SQL query fails static validation, the ``EXPLAIN`` dry-run, or real
execution, today the request 422s straight to the user with no retry. This module
holds the small, deterministic pieces of the repair path:

- feature flags for the EXPLAIN dry-run and the repair round-trip, and
- the prompt that feeds a failing query + its error back to the provider so it
  can return a corrected query.

The orchestration (validate -> explain -> execute, then one repair attempt) lives
in :mod:`app.api.chat_routes`; keeping the prompt + flags here makes them unit
testable without standing up the route.
"""

import os

# Stages at which a query can fail, in pipeline order. Carried on SqlPipelineError
# and surfaced to Langfuse so we can see *where* repairs are triggered.
STAGE_VALIDATION = "validation"
STAGE_EXPLAIN = "explain"
STAGE_EXECUTION = "execution"


def _flag(name: str, default: bool) -> bool:
    """Read a boolean env flag. Unset -> default; otherwise 1/true/yes/on = True."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def explain_enabled() -> bool:
    """Whether to run the EXPLAIN dry-run before real execution. Default on.

    Gate via ``CLICKSPOT_SQL_EXPLAIN_DRYRUN=0`` to skip the always-on ~few-ms
    EXPLAIN round-trip on the happy path.
    """
    return _flag("CLICKSPOT_SQL_EXPLAIN_DRYRUN", True)


def repair_enabled() -> bool:
    """Whether to attempt one LLM repair round-trip on failure. Default on.

    Gate via ``CLICKSPOT_SQL_REPAIR=0`` to restore the old fail-fast behaviour.
    """
    return _flag("CLICKSPOT_SQL_REPAIR", True)


def build_repair_message(failed_sql: str, error: str, stage: str) -> dict:
    """Build the synthetic user turn that asks the provider to fix a failed query.

    Appended to the existing conversation so the model keeps full question +
    schema context (the schema lives in the system prompt). The ClickHouse/
    validator error is SQL/schema-level — it never contains CRM row data — so it
    is safe to send to the provider alongside the failing SQL.
    """
    stage_hint = {
        STAGE_VALIDATION: "failed SQL validation",
        STAGE_EXPLAIN: "failed a ClickHouse EXPLAIN dry-run",
        STAGE_EXECUTION: "failed when executed on ClickHouse",
    }.get(stage, "failed")
    content = (
        f"The SQL you generated for the question above {stage_hint}. "
        "Return a corrected ClickHouse query that fixes the error, using only the "
        "tables and columns from the schema. Keep the same analytical intent.\n\n"
        f"Failing SQL:\n{failed_sql}\n\n"
        f"Error:\n{error}"
    )
    return {"role": "user", "content": content}
