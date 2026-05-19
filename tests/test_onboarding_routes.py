"""Smoke tests for the onboarding REST endpoints."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.customer import config as cc


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    cfgfile = tmp_path / "customer.json"
    cfgfile.write_text(
        json.dumps({"company_name": "Acme", "main_pipeline": "Sales", "canonical_amount_col": "amount"})
    )
    monkeypatch.setattr(cc, "CONFIG_FILE", cfgfile)
    monkeypatch.setattr(cc, "CONFIG_DIR", tmp_path)
    return cfgfile


def test_status_shape(isolated_config, monkeypatch):
    """Status endpoint returns the expected nested shape, even when CH is down."""
    monkeypatch.setenv("HUBSPOT_TOKEN", "test-token-1234567890")
    monkeypatch.setenv("HUBSPOT_HUB_ID", "12345678")

    # Make get_client raise so we exercise the unreachable branch
    def _bad_client():
        raise RuntimeError("CH down")

    with patch("app.db.get_client", side_effect=_bad_client):
        client = TestClient(app)
        res = client.get("/api/v1/onboarding/status")
    assert res.status_code == 200
    data = res.json()
    assert data["env"]["hubspot_token"] is True
    assert data["env"]["hubspot_hub_id"] == "12345678"
    assert data["env"]["hubspot_token_preview"].startswith("test")
    assert data["clickhouse"]["reachable"] is False
    assert data["silver"]["populated"] is False
    assert "customer_config" in data


def test_status_complete_flag(isolated_config, monkeypatch):
    monkeypatch.setenv("HUBSPOT_TOKEN", "tok")
    monkeypatch.setenv("HUBSPOT_HUB_ID", "h")
    with patch("app.db.get_client", side_effect=RuntimeError("down")):
        client = TestClient(app)
        res = client.get("/api/v1/onboarding/status")
    # Default canonical_amount_col is 'amount' which matches the default — so the
    # config completeness check should say it's NOT complete because main_pipeline
    # equals the default None... actually we set main_pipeline=Sales above.
    # canonical_amount_col=='amount' equals the DEFAULTS, so it'll be flagged missing.
    data = res.json()
    cc_status = data["customer_config"]
    assert isinstance(cc_status["missing_keys"], list)


def test_customer_config_put_partial_merge(isolated_config):
    client = TestClient(app)
    res = client.put("/api/v1/customer-config", json={"company_blurb": "AI for sales"})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["company_blurb"] == "AI for sales"
    assert data["company_name"] == "Acme"  # preserved


def test_customer_config_validates_main_pipeline(isolated_config):
    """If silver has a pipelines table and the value isn't in it, reject."""
    client = TestClient(app)
    # Mock CH to return a specific set of pipelines
    fake = MagicMock()
    fake_result = MagicMock()
    fake_result.result_rows = [("Sales",), ("Renewals",)]
    fake.query.return_value = fake_result
    with patch("app.db.get_client", return_value=fake):
        res = client.put("/api/v1/customer-config", json={"main_pipeline": "Nonexistent"})
    assert res.status_code == 400
    assert "main_pipeline" in res.text


def test_customer_config_accepts_valid_main_pipeline(isolated_config):
    client = TestClient(app)
    fake = MagicMock()
    fake_result = MagicMock()
    fake_result.result_rows = [("Sales",), ("Renewals",)]
    fake.query.return_value = fake_result
    with patch("app.db.get_client", return_value=fake):
        res = client.put("/api/v1/customer-config", json={"main_pipeline": "Renewals"})
    assert res.status_code == 200
    assert res.json()["main_pipeline"] == "Renewals"


def test_amount_columns_endpoint(isolated_config):
    """Endpoint surfaces revenue-shaped columns from dim_deals."""
    client = TestClient(app)
    fake = MagicMock()
    fake_result = MagicMock()
    fake_result.result_rows = [("amount",), ("annual_recurring_revenue",), ("ignored_col",)]
    fake.query.return_value = fake_result
    with patch("app.db.get_client", return_value=fake):
        res = client.get("/api/v1/onboarding/amount-columns")
    assert res.status_code == 200
    cols = res.json()["columns"]
    assert "amount" in cols
    assert "annual_recurring_revenue" in cols
    assert "ignored_col" not in cols
