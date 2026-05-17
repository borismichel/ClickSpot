"""Safety regression tests for app/engine/sql_builder.

Confirms that the user-controlled inputs going into f-string SQL builders
(column, group_by, date_column, measure_column, agg, granularity, selection
filter keys) are all validated against the TABLES whitelist or a fixed
allowlist before reaching the SQL string.

These tests would have caught the Critical findings #1 (condition injection)
and #2 (unvalidated column names) from SECURITY_AUDIT.md 2026-04-06.
"""

import pytest

from app.engine import sql_builder as sb


# ---------------------------------------------------------------------------
# Column validation (#2)
# ---------------------------------------------------------------------------

class TestValidateColumn:
    def test_known_column_passes(self):
        assert sb._validate_column("dim_deals", "amount") == "amount"

    def test_primary_key_passes(self):
        # PKs are allowed even when not in fields
        assert sb._validate_column("dim_deals", "deal_id") == "deal_id"

    def test_unknown_column_raises(self):
        with pytest.raises(ValueError, match="Unknown column"):
            sb._validate_column("dim_deals", "definitely_not_a_column")

    def test_sql_injection_attempt_raises(self):
        with pytest.raises(ValueError, match="Unknown column"):
            sb._validate_column("dim_deals", "amount) FROM system.one; DROP TABLE silver.dim_deals --")

    def test_unknown_table_raises(self):
        with pytest.raises(ValueError, match="Unknown table"):
            sb._validate_column("not_a_table", "amount")


class TestValidateGranularity:
    def test_known_granularity_passes(self):
        assert sb._validate_granularity("month") == "month"

    def test_unknown_granularity_raises(self):
        with pytest.raises(ValueError, match="Unknown granularity"):
            sb._validate_granularity("microsecond")


# ---------------------------------------------------------------------------
# Builder entry-point validation
# ---------------------------------------------------------------------------

class TestBuildersReject:
    def test_build_measure_query_rejects_unknown_column(self):
        with pytest.raises(ValueError, match="Unknown column"):
            sb.build_measure_query("dim_deals", "evil_col", "sum", "deal_id")

    def test_build_measure_query_rejects_unknown_agg(self):
        with pytest.raises(ValueError, match="Disallowed aggregation"):
            sb.build_measure_query("dim_deals", "amount", "DROP_TABLE", "deal_id")

    def test_build_field_values_query_rejects_unknown_column(self):
        with pytest.raises(ValueError, match="Unknown column"):
            sb.build_field_values_query("dim_deals", "evil_col", "deal_id")

    def test_build_grouped_measure_rejects_unknown_column(self):
        with pytest.raises(ValueError, match="Unknown column"):
            sb.build_grouped_measure_query("dim_deals", "evil_col", "sum", ["owner_name"], "deal_id")

    def test_build_grouped_measure_rejects_unknown_group_by(self):
        with pytest.raises(ValueError, match="Unknown column"):
            sb.build_grouped_measure_query("dim_deals", "amount", "sum", ["evil_col"], "deal_id")

    def test_build_time_series_rejects_unknown_measure_col(self):
        with pytest.raises(ValueError, match="Unknown column"):
            sb.build_time_series_query("dim_deals", "evil_col", "sum", "closedate", "month", "deal_id")

    def test_build_time_series_rejects_unknown_date_col(self):
        with pytest.raises(ValueError, match="Unknown column"):
            sb.build_time_series_query("dim_deals", "amount", "sum", "evil_col", "month", "deal_id")

    def test_build_time_series_rejects_unknown_granularity(self):
        with pytest.raises(ValueError, match="Unknown granularity"):
            sb.build_time_series_query("dim_deals", "amount", "sum", "closedate", "century", "deal_id")


# ---------------------------------------------------------------------------
# Selection filter validation (#9)
# ---------------------------------------------------------------------------

class TestWhereClauseRejects:
    def test_where_clause_rejects_unknown_filter_column(self):
        with pytest.raises(ValueError, match="Unknown column"):
            sb.build_where_clause("dim_deals", {"evil_col": ["x"]})

    def test_where_clause_rejects_sql_injection_in_column_key(self):
        with pytest.raises(ValueError, match="Unknown column"):
            sb.build_where_clause(
                "dim_deals",
                {"amount = 1 OR 1=1 --": ["x"]},
            )


# ---------------------------------------------------------------------------
# Confirm the dropped condition-injection vector is gone
# ---------------------------------------------------------------------------

class TestConditionInjectionRemoved:
    def test_no_build_conditional_measure_query_export(self):
        """The function that interpolated raw SQL `condition` has been removed."""
        assert not hasattr(sb, "build_conditional_measure_query")

    def test_measure_request_has_no_condition_field(self):
        """MeasureRequest's `condition` field has been removed."""
        from app.api.models import MeasureRequest
        assert "condition" not in MeasureRequest.model_fields
