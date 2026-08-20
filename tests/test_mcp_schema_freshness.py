"""The MCP server is a separate long-running process: a settings change made
live through "Apply changes" must reach its schema surface without restarting
it. The server re-derives the table catalog from the current customer config
on each schema request, so this pins exactly that."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("mcp")

from app.mcp import server  # noqa: E402


def _write_config_with_custom_column(cfgfile):
    cfgfile.write_text(json.dumps({
        "company_name": "Test",
        "extraction": {
            "objects": {},
            "silver_properties": {
                "dim_deals": {
                    "extra": [{"column": "custom_arr",
                               "property": "annual_recurring_revenue",
                               "type": "Nullable(Float64)"}],
                    "removed": [],
                },
            },
        },
    }))


def test_applied_column_change_reaches_get_schema_without_restart(isolated_config):
    assert "custom_arr" not in server.get_schema()

    _write_config_with_custom_column(isolated_config)

    assert "custom_arr" in server.get_schema()


def test_applied_column_change_reaches_the_tables_resource(isolated_config):
    _write_config_with_custom_column(isolated_config)

    catalog = json.loads(server.schema_tables())
    assert "custom_arr" in catalog["dim_deals"]["fields"]
