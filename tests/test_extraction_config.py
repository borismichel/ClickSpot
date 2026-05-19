"""Tests for app/customer/extraction.py — cascade rules, enabled-table accessors,
backward compatibility with missing `extraction` block."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.customer import config as cc
from app.customer import extraction as ext
from app.customer.extraction_rules import apply_cascade


# ---------------------------------------------------------------------------
# Backward compatibility — missing block = everything enabled
# ---------------------------------------------------------------------------


def test_missing_extraction_block_means_all_enabled(tmp_path):
    cfgfile = tmp_path / "customer.json"
    cfgfile.write_text(json.dumps({"company_name": "Acme"}))  # no `extraction`
    with patch.object(cc, "CONFIG_FILE", cfgfile):
        enabled = ext.get_enabled_objects()
        assert "leads" in enabled
        assert "calls" in enabled
        assert "forms" in enabled


def test_empty_extraction_block_means_all_enabled(tmp_path):
    cfgfile = tmp_path / "customer.json"
    cfgfile.write_text(json.dumps({"extraction": {}}))
    with patch.object(cc, "CONFIG_FILE", cfgfile):
        enabled = ext.get_enabled_objects()
        assert "leads" in enabled


# ---------------------------------------------------------------------------
# Cascade rules — leads off → lead_pipelines off; forms off → form_submissions off
# ---------------------------------------------------------------------------


def test_cascade_leads_off_forces_lead_pipelines_off():
    toggles = dict(ext.DEFAULT_OBJECTS)
    toggles["leads"] = False
    out = apply_cascade(toggles)
    assert out["leads"] is False
    assert out["lead_pipelines"] is False


def test_cascade_forms_off_forces_form_submissions_off():
    toggles = dict(ext.DEFAULT_OBJECTS)
    toggles["forms"] = False
    out = apply_cascade(toggles)
    assert out["forms"] is False
    assert out["form_submissions"] is False


def test_cascade_idempotent():
    """Running the cascade twice should produce the same result."""
    toggles = dict(ext.DEFAULT_OBJECTS)
    toggles["leads"] = False
    toggles["forms"] = False
    first = apply_cascade(toggles)
    second = apply_cascade(first)
    assert first == second


def test_cascade_lead_pipelines_alone_does_not_disable_leads():
    """Disabling lead_pipelines must NOT force leads off (one-way dependency)."""
    toggles = dict(ext.DEFAULT_OBJECTS)
    toggles["lead_pipelines"] = False
    out = apply_cascade(toggles)
    assert out["leads"] is True
    assert out["lead_pipelines"] is False


# ---------------------------------------------------------------------------
# Enabled-table accessors
# ---------------------------------------------------------------------------


def _with_extraction(tmp_path, block):
    cfgfile = tmp_path / "customer.json"
    cfgfile.write_text(json.dumps({"extraction": block}))
    return patch.object(cc, "CONFIG_FILE", cfgfile)


def test_disabling_leads_removes_lead_bronze_silver_gold(tmp_path):
    block = {
        "objects": {**ext.DEFAULT_OBJECTS, "leads": False},
    }
    with _with_extraction(tmp_path, block):
        bronze = ext.get_enabled_bronze_tables()
        assoc = ext.get_enabled_assoc_tables()
        silver = ext.get_enabled_silver_tables()
        gold = ext.get_enabled_gold_tables()

    # Bronze: lead-related tables gone
    assert "hs_leads" not in bronze
    assert "hs_lead_pipelines" not in bronze
    # But other bronze tables still there
    assert "hs_contacts" in bronze
    assert "hs_deals" in bronze

    # Assoc: lead-involving associations gone
    assert "hs_assoc_lead_contact" not in assoc
    assert "hs_assoc_deal_lead" not in assoc
    assert "hs_assoc_lead_company" not in assoc
    # Non-lead associations still there
    assert "hs_assoc_contact_company" in assoc

    # Silver: lead dims/bridges gone
    assert "dim_leads" not in silver
    assert "dim_lead_pipelines" not in silver
    assert "dim_lead_pipeline_stages" not in silver
    assert "bridge_lead_contact" not in silver
    assert "bridge_deal_lead" not in silver
    assert "bridge_lead_company" not in silver
    # Non-lead silver still there
    assert "dim_deals" in silver
    assert "bridge_contact_company" in silver

    # Gold: lead aggregates gone
    assert "agg_lead_health" not in gold
    # Non-lead gold still there
    assert "agg_deal_health" in gold
    assert "agg_deal_cohorts" in gold


def test_disabling_deals_cascades_to_gold(tmp_path):
    block = {"objects": {**ext.DEFAULT_OBJECTS, "deals": False}}
    with _with_extraction(tmp_path, block):
        silver = ext.get_enabled_silver_tables()
        gold = ext.get_enabled_gold_tables()
    assert "dim_deals" not in silver
    assert "bridge_contact_deal" not in silver
    # Every deal-dependent gold aggregate gone
    for name in (
        "agg_deal_health",
        "agg_deal_stage_funnel",
        "agg_rep_performance",
        "agg_source_attribution",
        "agg_deal_cohorts",
        "fact_pipeline_snapshots",
    ):
        assert name not in gold


def test_disabling_one_activity_keeps_fact_activities(tmp_path):
    """If at least one activity type is enabled, fact_activities still builds."""
    activities = {**ext.DEFAULT_OBJECTS["activities"], "tasks": False}
    block = {"objects": {**ext.DEFAULT_OBJECTS, "activities": activities}}
    with _with_extraction(tmp_path, block):
        bronze = ext.get_enabled_bronze_tables()
        silver = ext.get_enabled_silver_tables()
        assoc = ext.get_enabled_assoc_tables()
    assert "hs_tasks" not in bronze
    assert "hs_assoc_task_contact" not in assoc
    # fact_activities still built because calls/meetings/emails/notes remain
    assert "fact_activities" in silver


def test_disabling_all_activities_removes_fact_activities(tmp_path):
    activities = {k: False for k in ("calls", "meetings", "emails", "notes", "tasks")}
    block = {"objects": {**ext.DEFAULT_OBJECTS, "activities": activities}}
    with _with_extraction(tmp_path, block):
        silver = ext.get_enabled_silver_tables()
    assert "fact_activities" not in silver


def test_disabling_forms_cascades_to_submissions(tmp_path):
    block = {"objects": {**ext.DEFAULT_OBJECTS, "forms": False}}
    with _with_extraction(tmp_path, block):
        bronze = ext.get_enabled_bronze_tables()
        silver = ext.get_enabled_silver_tables()
    assert "hs_forms" not in bronze
    assert "hs_form_submissions" not in bronze
    assert "fact_form_submissions" not in silver


# ---------------------------------------------------------------------------
# Save round-trip (verifies cascade re-applied on persist)
# ---------------------------------------------------------------------------


def test_save_reapplies_cascade(tmp_path):
    """User PUTs `leads=False, lead_pipelines=True` — the save MUST force lead_pipelines off."""
    cfgfile = tmp_path / "customer.json"
    cfgfile.write_text(json.dumps({"company_name": "Acme"}))
    bad_block = {
        "objects": {
            **ext.DEFAULT_OBJECTS,
            "leads": False,
            "lead_pipelines": True,  # operator (or buggy client) tried to keep this on
        },
        "silver_properties": {},
    }
    with patch.object(cc, "CONFIG_FILE", cfgfile), patch.object(cc, "CONFIG_DIR", tmp_path):
        out = ext.save(bad_block)
    assert out["objects"]["lead_pipelines"] is False  # forced off by cascade


# ---------------------------------------------------------------------------
# Silver column overrides
# ---------------------------------------------------------------------------


def test_silver_column_overrides_extras_and_removed(tmp_path):
    block = {
        "objects": ext.DEFAULT_OBJECTS,
        "silver_properties": {
            "dim_deals": {
                "extra": [
                    {"column": "my_arr", "property": "annual_recurring_revenue", "type": "Nullable(Float64)"},
                ],
                "removed": ["hs_v2_date_entered_decisionmakerboughtin"],
            },
        },
    }
    with _with_extraction(tmp_path, block):
        extras, removed = ext.get_silver_column_overrides("dim_deals")
    assert extras == [("my_arr", "annual_recurring_revenue", "Nullable(Float64)")]
    assert removed == ["hs_v2_date_entered_decisionmakerboughtin"]


def test_silver_column_overrides_default_empty(tmp_path):
    """Missing silver_properties → empty extras, empty removed."""
    cfgfile = tmp_path / "customer.json"
    cfgfile.write_text(json.dumps({}))
    with patch.object(cc, "CONFIG_FILE", cfgfile):
        extras, removed = ext.get_silver_column_overrides("dim_deals")
    assert extras == []
    assert removed == []
