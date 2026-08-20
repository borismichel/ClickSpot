"""The MCP server is a separate long-running process: a settings change made
live through "Apply changes" must reach its schema surface without restarting
it — but no sooner. The server re-derives the table catalog from the customer
config on each schema request, gated on the pending-apply flag, so it follows
the *applied* configuration: a save that has not been applied (or whose apply
failed) leaves the served schema exactly as it was."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("mcp")

from app.mcp import server  # noqa: E402


def _write_config(cfgfile, *, silver_properties, pending=False):
    cfg = {
        "company_name": "Test",
        "extraction": {"objects": {}, "silver_properties": silver_properties},
    }
    if pending:
        cfg["extraction_pending_apply"] = "tok123"
    cfgfile.write_text(json.dumps(cfg))


EXTRA_ARR = {
    "dim_deals": {
        "extra": [{"column": "custom_arr", "property": "annual_recurring_revenue",
                   "type": "Nullable(Float64)"}],
        "removed": [],
    },
}

# A dim_deals column that is not locked, so operators may remove it.
REMOVABLE_DEAL_COLUMN = "hs_v2_date_entered_decisionmakerboughtin"


def test_applied_column_change_reaches_get_schema_without_restart(isolated_config):
    assert "custom_arr" not in server.get_schema()

    # Applied = saved with no pending flag left (the apply cleared it).
    _write_config(isolated_config, silver_properties=EXTRA_ARR)

    assert "custom_arr" in server.get_schema()


def test_applied_removal_disappears_from_get_schema(isolated_config):
    assert REMOVABLE_DEAL_COLUMN in server.get_schema()

    _write_config(isolated_config, silver_properties={
        "dim_deals": {"extra": [], "removed": [REMOVABLE_DEAL_COLUMN]},
    })

    assert REMOVABLE_DEAL_COLUMN not in server.get_schema()


def test_saved_but_unapplied_change_stays_invisible(isolated_config):
    """While the pending-apply flag is set the warehouse doesn't hold the new
    column yet — the MCP schema must keep describing what actually exists."""
    assert "custom_arr" not in server.get_schema()

    _write_config(isolated_config, silver_properties=EXTRA_ARR, pending=True)
    assert "custom_arr" not in server.get_schema()

    # The apply lands (flag cleared) → the next request picks it up.
    _write_config(isolated_config, silver_properties=EXTRA_ARR)
    assert "custom_arr" in server.get_schema()


def test_applied_column_change_reaches_the_tables_resource(isolated_config):
    _write_config(isolated_config, silver_properties=EXTRA_ARR)

    catalog = json.loads(server.schema_tables())
    assert "custom_arr" in catalog["dim_deals"]["fields"]
