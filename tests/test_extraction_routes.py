"""Smoke tests for the extraction REST endpoints."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.customer import config as cc


@pytest.fixture
def isolated_config(tmp_path):
    cfgfile = tmp_path / "customer.json"
    cfgfile.write_text(json.dumps({"company_name": "Test"}))
    with patch.object(cc, "CONFIG_FILE", cfgfile), patch.object(cc, "CONFIG_DIR", tmp_path):
        yield cfgfile
    # A save now refreshes the process-wide table catalog, which outlives this
    # test. Rebuild once the patches are off so the catalog matches the real
    # config again instead of leaking a warehouse schema invented here.
    from app.config import rebuild_tables
    rebuild_tables()


def test_get_extraction_returns_resolved_view(isolated_config):
    client = TestClient(app)
    res = client.get("/api/v1/extraction")
    assert res.status_code == 200
    data = res.json()
    assert "config" in data
    assert "groups" in data
    assert "cascade" in data
    assert "enabled_bronze_tables" in data
    assert "hs_leads" in data["enabled_bronze_tables"]  # default = everything on


def test_put_extraction_persists_cascade(isolated_config):
    client = TestClient(app)
    body = {
        "objects": {
            "contacts": True,
            "companies": True,
            "deals": True,
            "leads": False,
            "owners": True,
            "deal_pipelines": True,
            "lead_pipelines": True,  # backend MUST force this to false
            "activities": {"calls": True, "meetings": True, "emails": True, "notes": True, "tasks": True},
            "campaigns": True,
            "forms": True,
            "form_submissions": True,
        },
        "silver_properties": {},
    }
    res = client.put("/api/v1/extraction", json=body)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["config"]["objects"]["leads"] is False
    assert data["config"]["objects"]["lead_pipelines"] is False  # cascade
    assert "hs_leads" not in data["enabled_bronze_tables"]
    assert "dim_leads" not in data["enabled_silver_tables"]
    assert "agg_lead_health" not in data["enabled_gold_tables"]


def test_put_extraction_rejects_locked_column_removal(isolated_config):
    client = TestClient(app)
    body = {
        "objects": {
            "contacts": True, "companies": True, "deals": True, "leads": True,
            "owners": True, "deal_pipelines": True, "lead_pipelines": True,
            "activities": {"calls": True, "meetings": True, "emails": True, "notes": True, "tasks": True},
            "campaigns": True, "forms": True, "form_submissions": True,
        },
        "silver_properties": {
            "dim_deals": {"extra": [], "removed": ["dealname"]},  # locked column
        },
    }
    res = client.put("/api/v1/extraction", json=body)
    assert res.status_code == 400
    assert "locked" in res.text.lower() or "dealname" in res.text


def test_locked_columns_endpoint(isolated_config):
    client = TestClient(app)
    res = client.get("/api/v1/extraction/locked-columns")
    assert res.status_code == 200
    data = res.json()
    assert "dim_deals" in data
    assert "dealname" in data["dim_deals"]
    assert "amount" in data["dim_deals"]


# ---------------------------------------------------------------------------
# Schema freshness — a save must reach the schema this process serves, with no
# restart in between. The regression these guard is the one an operator saw as
# "Settings said it saved, chat still doesn't know about my column".
# ---------------------------------------------------------------------------

ALL_OBJECTS_ON = {
    "contacts": True, "companies": True, "deals": True, "leads": True,
    "owners": True, "deal_pipelines": True, "lead_pipelines": True,
    "activities": {"calls": True, "meetings": True, "emails": True, "notes": True, "tasks": True},
    "campaigns": True, "forms": True, "form_submissions": True,
}

# A dim_deals column that is not in LOCKED_CORE_COLUMNS, so it can be removed.
REMOVABLE_DEAL_COLUMN = "hs_v2_date_entered_decisionmakerboughtin"


def _save(client, silver_properties: dict):
    return client.put(
        "/api/v1/extraction",
        json={"objects": ALL_OBJECTS_ON, "silver_properties": silver_properties},
    )


def _deal_fields(client) -> dict:
    res = client.get("/api/v1/schema")
    assert res.status_code == 200, res.text
    return res.json()["tables"]["dim_deals"]["fields"]


def test_saved_extra_column_appears_in_served_schema(isolated_config):
    client = TestClient(app)
    assert "custom_arr" not in _deal_fields(client)

    res = _save(client, {
        "dim_deals": {
            "extra": [{"column": "custom_arr", "property": "annual_recurring_revenue",
                       "type": "Nullable(Float64)"}],
            "removed": [],
        },
    })
    assert res.status_code == 200, res.text

    fields = _deal_fields(client)
    assert "custom_arr" in fields
    assert fields["custom_arr"]["type"] == "Nullable(Float64)"


def test_saved_removal_drops_column_from_served_schema(isolated_config):
    client = TestClient(app)
    assert REMOVABLE_DEAL_COLUMN in _deal_fields(client)

    res = _save(client, {"dim_deals": {"extra": [], "removed": [REMOVABLE_DEAL_COLUMN]}})
    assert res.status_code == 200, res.text

    assert REMOVABLE_DEAL_COLUMN not in _deal_fields(client)


def test_saved_extra_column_is_dropped_again_when_removed(isolated_config):
    """Refresh works in both directions within one process — adding then taking
    the column away leaves no residue from the first save."""
    client = TestClient(app)
    _save(client, {
        "dim_deals": {
            "extra": [{"column": "custom_arr", "property": "annual_recurring_revenue",
                       "type": "Nullable(Float64)"}],
            "removed": [],
        },
    })
    assert "custom_arr" in _deal_fields(client)

    _save(client, {})
    assert "custom_arr" not in _deal_fields(client)


def test_rejected_locked_removal_leaves_served_schema_untouched(isolated_config):
    """The locked-column guard runs before anything is saved or refreshed, so a
    rejected save cannot half-apply."""
    client = TestClient(app)
    before = dict(_deal_fields(client))

    res = _save(client, {"dim_deals": {"extra": [], "removed": ["dealname"]}})
    assert res.status_code == 400

    assert _deal_fields(client) == before
    assert "dealname" in _deal_fields(client)


def test_malformed_property_entry_is_skipped(isolated_config):
    """A hand-edited or older customer.json can hold an incomplete extra row.
    The override reader tolerates it; the property picker must not propagate it."""
    isolated_config.write_text(json.dumps({
        "company_name": "Test",
        "extraction": {
            "objects": {},
            "silver_properties": {
                "dim_deals": {
                    "extra": [
                        {"column": "good_col", "property": "good_prop", "type": "String"},
                        {"column": "bad_col", "property": "bad_prop"},  # no type
                    ],
                    "removed": [],
                },
            },
        },
    }))
    client = TestClient(app)
    res = client.get("/api/v1/extraction/properties/deals")
    assert res.status_code == 200, res.text
    by_property = {row["property"]: row for row in res.json()["properties"]}

    assert by_property["good_prop"]["source"] == "extra"
    assert "bad_prop" not in by_property
