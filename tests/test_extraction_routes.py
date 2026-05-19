"""Smoke tests for the extraction REST endpoints."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.customer import config as cc


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    cfgfile = tmp_path / "customer.json"
    cfgfile.write_text(json.dumps({"company_name": "Test"}))
    monkeypatch.setattr(cc, "CONFIG_FILE", cfgfile)
    monkeypatch.setattr(cc, "CONFIG_DIR", tmp_path)
    return cfgfile


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
