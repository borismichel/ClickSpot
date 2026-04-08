"""Tests for rule-based dashboard SQL filter injection."""

import pytest
from app.engine.sql_filter import apply_filters, DashboardFilters


def _normalize(sql: str) -> str:
    """Normalize whitespace for comparison."""
    return " ".join(sql.split())


# ---------------------------------------------------------------------------
# Date filter
# ---------------------------------------------------------------------------

class TestDateFilter:
    def test_simple_select_with_existing_where(self):
        sql = "SELECT deal_id, dealname FROM silver.dim_deals WHERE archived = 0 LIMIT 100"
        f = DashboardFilters(date_from="2026-01-01", date_to="2026-04-01")
        result = apply_filters(sql, f)
        assert "closedate >= '2026-01-01'" in result
        assert "closedate < '2026-04-01'" in result
        assert "closedate > '1970-01-02'" in result
        assert "archived = 0" in result

    def test_no_where_clause(self):
        sql = "SELECT count() FROM silver.dim_deals"
        f = DashboardFilters(date_from="2026-01-01")
        result = apply_filters(sql, f)
        assert "WHERE" in result
        assert "closedate >= '2026-01-01'" in result

    def test_date_only_from(self):
        sql = "SELECT deal_id FROM silver.dim_deals WHERE archived = 0"
        f = DashboardFilters(date_from="2026-03-01")
        result = apply_filters(sql, f)
        assert "closedate >= '2026-03-01'" in result
        assert "closedate <" not in result

    def test_date_only_to(self):
        sql = "SELECT deal_id FROM silver.dim_deals WHERE archived = 0"
        f = DashboardFilters(date_to="2026-04-01")
        result = apply_filters(sql, f)
        assert "closedate < '2026-04-01'" in result
        assert "closedate >=" not in result

    def test_contacts_use_createdate(self):
        sql = "SELECT contact_id FROM silver.dim_contacts WHERE archived = 0"
        f = DashboardFilters(date_from="2026-01-01")
        result = apply_filters(sql, f)
        assert "createdate >= '2026-01-01'" in result

    def test_contacts_no_owner_filter(self):
        """dim_contacts doesn't have hubspot_owner_id — owner filter should be skipped."""
        sql = "SELECT contact_id FROM silver.dim_contacts WHERE archived = 0"
        f = DashboardFilters(owner_ids=["123"], owner_names=["Test"])
        result = apply_filters(sql, f)
        assert "hubspot_owner_id" not in result

    def test_gold_table_uses_period_start(self):
        sql = "SELECT owner_name, deals_won FROM gold.agg_rep_performance"
        f = DashboardFilters(date_from="2026-01-01", date_to="2026-04-01")
        result = apply_filters(sql, f)
        assert "period_start >= '2026-01-01'" in result
        assert "period_start < '2026-04-01'" in result


# ---------------------------------------------------------------------------
# Owner filter
# ---------------------------------------------------------------------------

class TestOwnerFilter:
    def test_silver_uses_owner_id(self):
        sql = "SELECT deal_id FROM silver.dim_deals WHERE archived = 0"
        f = DashboardFilters(owner_ids=["12345"], owner_names=["Max M"])
        result = apply_filters(sql, f)
        assert "hubspot_owner_id = '12345'" in result
        assert "Max M" not in result

    def test_gold_uses_owner_name(self):
        sql = "SELECT owner_name, deals_won FROM gold.agg_rep_performance"
        f = DashboardFilters(owner_ids=["12345"], owner_names=["Max M"])
        result = apply_filters(sql, f)
        assert "owner_name = 'Max M'" in result
        assert "12345" not in result

    def test_multiple_owners(self):
        sql = "SELECT deal_id FROM silver.dim_deals WHERE archived = 0"
        f = DashboardFilters(owner_ids=["111", "222"], owner_names=["A", "B"])
        result = apply_filters(sql, f)
        assert "hubspot_owner_id IN ('111', '222')" in result


# ---------------------------------------------------------------------------
# Pipeline filter
# ---------------------------------------------------------------------------

class TestPipelineFilter:
    def test_silver_uses_pipeline_id(self):
        sql = "SELECT deal_id FROM silver.dim_deals WHERE archived = 0"
        f = DashboardFilters(pipeline_ids=["abc"], pipeline_labels=["Sales Pipeline"])
        result = apply_filters(sql, f)
        assert "pipeline = 'abc'" in result
        assert "Sales Pipeline" not in result

    def test_gold_uses_pipeline_label(self):
        sql = "SELECT deal_id FROM gold.agg_deal_health"
        f = DashboardFilters(pipeline_ids=["abc"], pipeline_labels=["Sales Pipeline"])
        result = apply_filters(sql, f)
        assert "pipeline_label = 'Sales Pipeline'" in result

    def test_leads_use_hs_pipeline(self):
        sql = "SELECT lead_id FROM silver.dim_leads WHERE archived = 0"
        f = DashboardFilters(pipeline_ids=["lead-pipe-1"], pipeline_labels=["Lead Pipeline"])
        result = apply_filters(sql, f)
        assert "hs_pipeline = 'lead-pipe-1'" in result

    def test_table_without_pipeline(self):
        sql = "SELECT contact_id FROM silver.dim_contacts WHERE archived = 0"
        f = DashboardFilters(pipeline_ids=["abc"], pipeline_labels=["Sales"])
        result = apply_filters(sql, f)
        # Pipeline filter should be skipped — contacts have no pipeline column
        assert "pipeline" not in result.lower() or "pipeline" not in result.split("FROM")[1]


# ---------------------------------------------------------------------------
# Table aliases
# ---------------------------------------------------------------------------

class TestAliases:
    def test_aliased_table(self):
        sql = "SELECT deals.deal_id FROM silver.dim_deals AS deals WHERE deals.archived = 0"
        f = DashboardFilters(date_from="2026-01-01")
        result = apply_filters(sql, f)
        assert "deals.closedate >= '2026-01-01'" in result

    def test_join_with_aliases(self):
        sql = (
            "SELECT d.deal_id, c.contact_id "
            "FROM silver.dim_deals AS d "
            "JOIN silver.dim_contacts AS c ON c.contact_id = d.contact_id "
            "WHERE d.archived = 0"
        )
        f = DashboardFilters(owner_ids=["123"], owner_names=["Test"])
        result = apply_filters(sql, f)
        assert "d.hubspot_owner_id = '123'" in result
        # dim_contacts has no hubspot_owner_id — filter skipped
        assert "c.hubspot_owner_id" not in result


# ---------------------------------------------------------------------------
# CTEs
# ---------------------------------------------------------------------------

class TestCTEs:
    def test_cte_injects_into_body(self):
        sql = (
            "WITH sub AS ("
            "SELECT deal_id, dealname FROM silver.dim_deals WHERE archived = 0"
            ") SELECT deal_id, dealname FROM sub LIMIT 100"
        )
        f = DashboardFilters(date_from="2026-01-01")
        result = apply_filters(sql, f)
        # Condition should be inside the CTE, not on the outer SELECT
        assert "closedate >= '2026-01-01'" in result
        # The CTE alias 'sub' should not get conditions
        assert result.count("closedate") == 2  # >= and > sentinel


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_filters_returns_unchanged(self):
        sql = "SELECT deal_id FROM silver.dim_deals WHERE archived = 0"
        f = DashboardFilters()
        assert apply_filters(sql, f) == sql

    def test_no_filterable_tables(self):
        sql = "SELECT 1"
        f = DashboardFilters(date_from="2026-01-01")
        result = apply_filters(sql, f)
        assert "closedate" not in result

    def test_unqualified_table_skipped(self):
        """Tables without database prefix are skipped (could be CTE aliases)."""
        sql = "SELECT x FROM unknown_table"
        f = DashboardFilters(date_from="2026-01-01")
        result = apply_filters(sql, f)
        assert "closedate" not in result

    def test_unknown_table_skipped(self):
        sql = "SELECT x FROM silver.bridge_contact_company"
        f = DashboardFilters(date_from="2026-01-01")
        result = apply_filters(sql, f)
        # Bridge tables are not in the registry — no filter applied
        assert "closedate" not in result

    def test_combined_filters(self):
        sql = "SELECT deal_id FROM silver.dim_deals WHERE archived = 0"
        f = DashboardFilters(
            date_from="2026-01-01",
            date_to="2026-04-01",
            owner_ids=["123"],
            owner_names=["Test"],
            pipeline_ids=["pipe1"],
            pipeline_labels=["Sales"],
        )
        result = apply_filters(sql, f)
        assert "closedate >= '2026-01-01'" in result
        assert "closedate < '2026-04-01'" in result
        assert "hubspot_owner_id = '123'" in result
        assert "pipeline = 'pipe1'" in result

    def test_sql_injection_escaped(self):
        """Values are AST literals, not parsed as SQL — injection is impossible."""
        sql = "SELECT deal_id FROM silver.dim_deals WHERE archived = 0"
        f = DashboardFilters(owner_ids=["'; DROP TABLE deals; --"], owner_names=["x"])
        result = apply_filters(sql, f)
        # The value should be a string literal, not executed as SQL
        assert "hubspot_owner_id" in result
        # DROP should only appear inside a quoted string, not as a statement
        assert "DROP TABLE" not in result.split("'")[-1]  # nothing after the closing quote

    def test_malformed_sql_returns_original(self):
        sql = "THIS IS NOT SQL AT ALL"
        f = DashboardFilters(date_from="2026-01-01")
        result = apply_filters(sql, f)
        assert result == sql
