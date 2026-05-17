"""Tests for the per-portal customer config layer."""

import json
from unittest.mock import MagicMock, patch

from app.customer import config as cc


def test_load_returns_defaults_when_no_file(tmp_path):
    with patch.object(cc, "CONFIG_FILE", tmp_path / "nonexistent.json"):
        cfg = cc.load()
    assert cfg == cc.DEFAULTS
    assert cfg["main_pipeline"] is None
    assert cfg["canonical_amount_col"] == "amount"


def test_load_merges_user_values_over_defaults(tmp_path):
    cfgfile = tmp_path / "customer.json"
    cfgfile.write_text(json.dumps({"company_name": "Acme Inc", "main_pipeline": "Sales"}))
    with patch.object(cc, "CONFIG_FILE", cfgfile):
        cfg = cc.load()
    assert cfg["company_name"] == "Acme Inc"
    assert cfg["main_pipeline"] == "Sales"
    # Defaults preserved for unset keys
    assert cfg["canonical_amount_col"] == "amount"


def test_load_falls_back_to_defaults_on_corrupt_file(tmp_path):
    cfgfile = tmp_path / "customer.json"
    cfgfile.write_text("{ not valid json")
    with patch.object(cc, "CONFIG_FILE", cfgfile):
        cfg = cc.load()
    assert cfg == cc.DEFAULTS


def test_save_writes_0600_perms(tmp_path):
    cfgfile = tmp_path / "customer.json"
    with patch.object(cc, "CONFIG_DIR", tmp_path), patch.object(cc, "CONFIG_FILE", cfgfile):
        cc.save({"company_name": "Test", "main_pipeline": "P1"})
    assert cfgfile.exists()
    assert cfgfile.stat().st_mode & 0o777 == 0o600
    loaded = json.loads(cfgfile.read_text())
    assert loaded["company_name"] == "Test"


def test_merge_defaults_only_fills_defaults_not_user_choices():
    current = dict(cc.DEFAULTS)
    current["main_pipeline"] = "Operator's Choice"  # user-set, must not be overwritten
    discovered = {
        "main_pipeline": "Auto-discovered (wrong)",  # this should NOT win
        "currency": "EUR",                            # current is DEFAULT (USD), this SHOULD win
        "all_pipelines": [{"label": "X"}],            # current is DEFAULT ([]), this SHOULD win
    }
    merged = cc.merge_defaults_only(current, discovered)
    assert merged["main_pipeline"] == "Operator's Choice"
    assert merged["currency"] == "EUR"
    assert merged["all_pipelines"] == [{"label": "X"}]


def test_auto_discover_pulls_pipelines_and_stages():
    """auto_discover queries silver and returns a partial dict."""
    client = MagicMock()

    def query(sql, parameters=None):
        result = MagicMock()
        if "FROM silver.dim_pipelines" in sql:
            result.result_rows = [("Main",), ("Legacy",)]
        elif "topK(1)(deal_currency_code)" in sql:
            result.result_rows = [(["EUR"],)]
        elif "FROM silver.dim_deals" in sql and "GROUP BY pipeline_id" in sql:
            result.result_rows = [("pipe-id-123", 500)]
        elif "FROM silver.dim_pipeline_stages" in sql:
            result.result_rows = [
                ("Discovery", 0, 1),
                ("Negotiation", 0, 2),
                ("Closed Won", 1, 3),
                ("Closed Lost", 1, 4),
            ]
        else:
            result.result_rows = []
        return result

    client.query = query
    out = cc.auto_discover(client)

    assert out["all_pipelines"] == [{"label": "Main", "note": ""}, {"label": "Legacy", "note": ""}]
    assert out["currency"] == "EUR"
    assert out["currency_symbol"] == "EUR"
    assert out["stages"] == ["Discovery", "Negotiation", "Closed Won", "Closed Lost"]
    assert out["early_stage"] == "Discovery"
    assert out["late_stage"] == "Negotiation"
    assert out["closed_won_stage"] == "Closed Won"
    assert out["closed_lost_stage"] == "Closed Lost"


def test_auto_discover_returns_empty_on_failure():
    client = MagicMock()
    client.query.side_effect = RuntimeError("connection refused")
    out = cc.auto_discover(client)
    assert out == {}


def test_schema_prompt_uses_customer_config(tmp_path):
    """End-to-end: schema_prompt renders the configured pipeline name into examples."""
    from app.llm import schema_prompt as sp
    cfgfile = tmp_path / "customer.json"
    cfgfile.write_text(json.dumps({
        "company_name": "Acme Inc",
        "currency": "USD",
        "main_pipeline": "Acme Main Sales",
        "all_pipelines": [{"label": "Acme Main Sales", "note": "Primary"}],
        "stages": ["Discovery", "Negotiation", "Won"],
        "forecast_categories": [],
    }))
    with patch.object(cc, "CONFIG_FILE", cfgfile):
        prompt = sp.build_schema_prompt()
    assert "Acme Inc" in prompt
    assert "Acme Main Sales" in prompt
    # Sanity: customer.json's business context overrides any other portal's strings.
    # (Per-portal silver_config_custom.py may still inject extra column names into the
    # TABLES block — that's a separate per-install file, covered by test_silver_assets.py.)
