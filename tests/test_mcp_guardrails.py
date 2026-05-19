"""Tests for MCP table-level guardrails — anon namespace + activity exclusion."""

import pytest

from app.customer import config as _customer_config
from app.llm.sql_validator import ALLOWED_TABLES
from app.llm.schema_prompt import build_schema_prompt
from app.mcp.guardrails import (
    ACTIVITY_STRIP_RE,
    EXCLUDED_TABLES,
    MCP_ALLOWED_TABLES,
    reject_excluded_tables,
    validate_mcp_sql,
)


@pytest.fixture(autouse=True)
def _isolated_customer_config(tmp_path, monkeypatch):
    """Run every test in this file against a non-existent customer.json so the
    extraction settings on the developer's machine don't change the schema
    prompt out from under us. With no file, app.customer.extraction falls back
    to "everything enabled", matching the assumptions baked into these tests.
    """
    monkeypatch.setattr(_customer_config, "CONFIG_FILE", tmp_path / "nonexistent.json")
    monkeypatch.setattr(_customer_config, "CONFIG_DIR", tmp_path)


class TestExclusionSet:
    def test_activity_tables_absent_from_mcp_whitelist(self):
        # Raw silver activity tables exist in the app whitelist but must not
        # appear in either namespace on the MCP whitelist — they're physically
        # absent from silver_anon too.
        for raw in [
            "silver.fact_activities",
            "silver.bridge_activity_contact",
            "silver.bridge_activity_company",
            "silver.bridge_activity_deal",
        ]:
            assert raw in ALLOWED_TABLES, f"{raw} must exist in app whitelist"
            assert raw not in MCP_ALLOWED_TABLES
            anon = raw.replace("silver.", "silver_anon.")
            assert anon not in MCP_ALLOWED_TABLES, f"{anon} must not be MCP-visible"

    def test_anon_tables_present_on_mcp_whitelist(self):
        # Every non-activity silver/gold table has an anon counterpart exposed
        # to the MCP.
        for t in [
            "silver_anon.dim_deals",
            "silver_anon.dim_contacts",
            "silver_anon.dim_companies",
            "silver_anon.bridge_contact_deal",
            "silver_anon.bridge_lead_contact",
            "silver_anon.fact_stage_history",
            "gold_anon.agg_rep_performance",
            "gold_anon.agg_deal_health",
            "gold_anon.agg_lead_health",
        ]:
            assert t in MCP_ALLOWED_TABLES

    def test_raw_silver_tables_rejected_by_mcp(self):
        # The raw silver/gold namespace is NOT exposed via MCP — the LLM must
        # query the anonymized copies.
        for raw in ["silver.dim_deals", "gold.agg_deal_health"]:
            assert raw not in MCP_ALLOWED_TABLES


class TestValidateMcpSql:
    def test_accepts_silver_anon_query(self):
        ok, err = validate_mcp_sql(
            "SELECT deal_id, dealname FROM silver_anon.dim_deals LIMIT 5"
        )
        assert ok, err

    def test_accepts_gold_anon_query(self):
        ok, err = validate_mcp_sql(
            "SELECT deal_id FROM gold_anon.agg_deal_health LIMIT 5"
        )
        assert ok, err

    def test_rejects_raw_silver(self):
        ok, err = validate_mcp_sql(
            "SELECT deal_id FROM silver.dim_deals LIMIT 5"
        )
        assert not ok
        assert "silver_anon" in err

    def test_rejects_raw_gold(self):
        ok, err = validate_mcp_sql(
            "SELECT * FROM gold.agg_deal_health LIMIT 5"
        )
        assert not ok

    def test_rejects_mutation_keyword_in_select(self):
        # Any mutation keyword (ALTER, DROP, INSERT, ...) appearing inside a
        # SELECT/WITH body is rejected by the forbidden-keyword check.
        ok, err = validate_mcp_sql(
            "SELECT deal_id FROM silver_anon.dim_deals; DROP TABLE x"
        )
        assert not ok
        assert "DROP" in err

    def test_rejects_non_select_prefix(self):
        ok, err = validate_mcp_sql("DROP TABLE silver_anon.dim_deals")
        assert not ok
        assert "SELECT" in err

    def test_rejects_select_star(self):
        ok, err = validate_mcp_sql("SELECT * FROM silver_anon.dim_deals LIMIT 1")
        assert not ok

    def test_rejects_system_tables(self):
        ok, err = validate_mcp_sql("SELECT name FROM system.tables LIMIT 1")
        assert not ok

    def test_rejects_dictget_against_raw_silver(self):
        # Bypass attempt: FROM references an allowed anon table, but dictGet
        # reaches into the raw silver dictionary (unmasked PII). Must be rejected.
        ok, err = validate_mcp_sql(
            "SELECT dictGet('silver.dict_contacts', 'full_name', tuple(contact_id)) AS nm "
            "FROM silver_anon.dim_deals LIMIT 5"
        )
        assert not ok
        assert "silver.dict_contacts" in err or "silver_anon" in err

    def test_rejects_dictget_against_raw_gold(self):
        ok, err = validate_mcp_sql(
            "SELECT dictGet('gold.agg_deal_health', 'dealname', tuple(deal_id)) AS d "
            "FROM silver_anon.dim_deals LIMIT 5"
        )
        assert not ok

    def test_silver_anon_not_caught_by_raw_namespace_check(self):
        # Regression: the \b word boundary must NOT treat silver_anon. as silver.
        ok, err = validate_mcp_sql(
            "SELECT deal_id FROM silver_anon.dim_deals "
            "WHERE dealname != 'silverware' LIMIT 5"
        )
        assert ok, err


class TestRejectExcludedTables:
    def test_fact_activities_rejected(self):
        err = reject_excluded_tables("SELECT activity_id FROM silver.fact_activities LIMIT 5")
        assert err is not None
        assert "silver.fact_activities" in err
        assert "MCP" in err

    def test_bridge_activity_deal_rejected(self):
        err = reject_excluded_tables(
            "SELECT deal_id FROM silver.dim_deals JOIN silver.bridge_activity_deal b ON 1=1"
        )
        assert err is not None
        assert "bridge_activity_deal" in err

    def test_bridge_activity_contact_rejected(self):
        err = reject_excluded_tables(
            "SELECT 1 FROM silver.bridge_activity_contact"
        )
        assert err is not None

    def test_bridge_activity_company_rejected(self):
        err = reject_excluded_tables(
            "SELECT 1 FROM silver.dim_companies c JOIN silver.bridge_activity_company b USING(company_id)"
        )
        assert err is not None

    def test_case_insensitive_match(self):
        err = reject_excluded_tables("select x from silver.FACT_ACTIVITIES")
        assert err is not None

    def test_clean_query_passes(self):
        assert reject_excluded_tables(
            "SELECT deal_id, dealname FROM silver.dim_deals WHERE archived = 0 LIMIT 5"
        ) is None

    def test_similar_named_table_not_rejected(self):
        # A table name containing "activity" as a column/alias shouldn't trigger
        # — only FROM/JOIN references to the blocked fully-qualified names do.
        assert reject_excluded_tables(
            "SELECT activity_type FROM silver.dim_deals LIMIT 5"
        ) is None

    def test_bridge_contact_company_not_rejected(self):
        # legit bridge — substring "bridge_" is NOT enough, must be bridge_activity_
        assert reject_excluded_tables(
            "SELECT 1 FROM silver.dim_contacts JOIN silver.bridge_contact_company USING(contact_id)"
        ) is None

    def test_with_cte_and_multiple_from_clauses(self):
        err = reject_excluded_tables(
            "WITH x AS (SELECT 1 FROM silver.dim_deals) "
            "SELECT * FROM x JOIN silver.bridge_activity_deal ON 1=1"
        )
        assert err is not None


class TestActivityStripRegex:
    def test_strips_fact_activities_table_section(self):
        prompt = build_schema_prompt(None)
        stripped = ACTIVITY_STRIP_RE.sub("", prompt)

        # The fully-qualified blocked names must be gone
        assert "silver.fact_activities" not in stripped
        assert "silver.bridge_activity_contact" not in stripped
        assert "silver.bridge_activity_company" not in stripped
        assert "silver.bridge_activity_deal" not in stripped

    def test_preserves_non_activity_tables(self):
        prompt = build_schema_prompt(None)
        stripped = ACTIVITY_STRIP_RE.sub("", prompt)

        # Legitimate tables and relationships must survive
        assert "silver.dim_deals" in stripped
        assert "silver.dim_contacts" in stripped
        assert "silver.bridge_contact_deal" in stripped
        assert "silver.bridge_lead_contact" in stripped
        assert "silver.fact_stage_history" in stripped
        assert "gold.agg_deal_health" in stripped

    def test_preserves_activity_metric_columns_on_other_tables(self):
        # Derived metadata columns like last_activity_date on dim_deals are NOT
        # PII content — they must survive (only the fact_activities table itself
        # and its bridges are the concern).
        prompt = build_schema_prompt(None)
        stripped = ACTIVITY_STRIP_RE.sub("", prompt)

        assert "last_activity_date" in stripped
        assert "days_since_last_activity" in stripped

    def test_strips_activities_entity_header(self):
        prompt = build_schema_prompt(None)
        stripped = ACTIVITY_STRIP_RE.sub("", prompt)

        # The "ACTIVITIES (silver.fact_activities)" data-model header line must go
        assert "ACTIVITIES (silver.fact_activities)" not in stripped
        # And the bridge relationship lines
        assert "ACTIVITIES ↔" not in stripped
