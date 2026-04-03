"""Tests for silver layer SQL generation and config structure."""

from assets.silver import _cast_expr, _build_ddl, _build_insert
from silver_config import (
    DIM_CONTACTS, DIM_COMPANIES, DIM_DEALS, DIM_LEADS,
    DIM_OWNERS, DIM_PIPELINES, DIM_PIPELINE_STAGES,
    FACT_ACTIVITIES, BRIDGE_TABLES, BRIDGE_ACTIVITY_CONTACT,
)


# ---------------------------------------------------------------------------
# _cast_expr
# ---------------------------------------------------------------------------

class TestCastExpr:
    def test_string_from_properties(self):
        assert _cast_expr("email", "String") == "properties['email']"

    def test_string_from_json(self):
        assert _cast_expr("email", "String", "json") == "JSONExtractString(_raw, 'email')"

    def test_datetime_from_properties(self):
        assert _cast_expr("createdate", "DateTime") == "parseDateTimeBestEffortOrZero(properties['createdate'])"

    def test_datetime_from_json(self):
        assert _cast_expr("createdAt", "DateTime", "json") == "parseDateTimeBestEffortOrZero(JSONExtractString(_raw, 'createdAt'))"

    def test_nullable_float64(self):
        assert _cast_expr("amount", "Nullable(Float64)") == "toFloat64OrNull(properties['amount'])"

    def test_uint32(self):
        assert _cast_expr("displayOrder", "UInt32", "json") == "toUInt32OrZero(JSONExtractString(_raw, 'displayOrder'))"

    def test_nullable_int64(self):
        assert _cast_expr("count", "Nullable(Int64)") == "toInt64OrNull(properties['count'])"


# ---------------------------------------------------------------------------
# _build_ddl
# ---------------------------------------------------------------------------

class TestBuildDdl:
    def test_basic_dim_ddl(self):
        ddl = _build_ddl("dim_contacts", "contact_id", DIM_CONTACTS["columns"])
        assert "CREATE TABLE silver.dim_contacts" in ddl
        assert "contact_id String" in ddl
        assert "email String" in ddl
        assert "archived UInt8" in ddl
        assert "_silver_loaded_at DateTime DEFAULT now()" in ddl
        assert "ReplacingMergeTree(_silver_loaded_at)" in ddl
        assert "ORDER BY (contact_id)" in ddl

    def test_nested_stages_ddl(self):
        ddl = _build_ddl("dim_pipeline_stages", "stage_id", DIM_PIPELINE_STAGES["columns"], "nested_stages")
        assert "stage_id String" in ddl
        assert "pipeline_id String" in ddl
        assert "probability Nullable(Float64)" in ddl

    def test_json_source_ddl(self):
        ddl = _build_ddl("dim_owners", "owner_id", DIM_OWNERS["columns"], "json")
        assert "owner_id String" in ddl
        assert "first_name String" in ddl
        assert "created_at DateTime" in ddl


# ---------------------------------------------------------------------------
# _build_insert
# ---------------------------------------------------------------------------

class TestBuildInsert:
    def test_properties_source_insert(self):
        sql = _build_insert("dim_contacts", "contact_id", DIM_CONTACTS)
        assert "INSERT INTO silver.dim_contacts" in sql
        assert "_record_id AS contact_id" in sql
        assert "properties['email']" in sql
        assert "parseDateTimeBestEffortOrZero(properties['hs_v2_date_entered_salesqualifiedlead'])" in sql
        assert "FROM bronze.hs_contacts FINAL" in sql
        assert "JSONExtractBool(_raw, 'archived')" in sql

    def test_json_source_insert(self):
        sql = _build_insert("dim_owners", "owner_id", DIM_OWNERS)
        assert "INSERT INTO silver.dim_owners" in sql
        assert "JSONExtractString(_raw, 'email')" in sql
        assert "JSONExtractString(_raw, 'firstName')" in sql
        assert "parseDateTimeBestEffortOrZero(JSONExtractString(_raw, 'createdAt'))" in sql
        assert "FROM bronze.hs_owners FINAL" in sql

    def test_nullable_float_casting(self):
        sql = _build_insert("dim_deals", "deal_id", DIM_DEALS)
        assert "toFloat64OrNull(properties['amount'])" in sql

    def test_uint32_casting(self):
        sql = _build_insert("dim_pipelines", "pipeline_id", DIM_PIPELINES)
        assert "toUInt32OrZero(JSONExtractString(_raw, 'displayOrder'))" in sql


# ---------------------------------------------------------------------------
# Config structure validation
# ---------------------------------------------------------------------------

class TestConfigStructure:
    """Verify all configs have required keys and consistent column tuples."""

    def test_dim_configs_have_required_keys(self):
        for name, config in [
            ("contacts", DIM_CONTACTS), ("companies", DIM_COMPANIES),
            ("deals", DIM_DEALS), ("leads", DIM_LEADS),
            ("owners", DIM_OWNERS), ("pipelines", DIM_PIPELINES),
        ]:
            assert "bronze_table" in config, f"{name} missing bronze_table"
            assert "primary_key" in config, f"{name} missing primary_key"
            assert "columns" in config, f"{name} missing columns"
            assert len(config["columns"]) > 0, f"{name} has empty columns"

    def test_dim_columns_are_3_tuples(self):
        for name, config in [
            ("contacts", DIM_CONTACTS), ("companies", DIM_COMPANIES),
            ("deals", DIM_DEALS), ("leads", DIM_LEADS),
            ("owners", DIM_OWNERS), ("pipelines", DIM_PIPELINES),
        ]:
            for col in config["columns"]:
                assert len(col) == 3, f"{name} column {col} is not a 3-tuple"

    def test_pipeline_stages_columns_are_2_tuples(self):
        for col in DIM_PIPELINE_STAGES["columns"]:
            assert len(col) == 2, f"pipeline_stages column {col} is not a 2-tuple"

    def test_fact_activities_all_have_required_keys(self):
        for act_type, mapping in FACT_ACTIVITIES.items():
            assert "subject" in mapping, f"{act_type} missing subject"
            assert "disposition" in mapping, f"{act_type} missing disposition"
            assert "duration" in mapping, f"{act_type} missing duration"

    def test_bridge_tables_are_4_tuples(self):
        for bridge in BRIDGE_TABLES:
            assert len(bridge) == 4, f"Bridge {bridge} is not a 4-tuple"

    def test_bridge_activity_contact_are_2_tuples(self):
        for entry in BRIDGE_ACTIVITY_CONTACT:
            assert len(entry) == 2, f"Activity bridge {entry} is not a 2-tuple"

    def test_valid_clickhouse_types(self):
        valid_types = {"String", "DateTime", "Nullable(Float64)", "Nullable(Int64)", "UInt32", "UInt8"}
        for name, config in [
            ("contacts", DIM_CONTACTS), ("companies", DIM_COMPANIES),
            ("deals", DIM_DEALS), ("leads", DIM_LEADS),
            ("owners", DIM_OWNERS), ("pipelines", DIM_PIPELINES),
        ]:
            for col_name, _prop, col_type in config["columns"]:
                assert col_type in valid_types, f"{name}.{col_name} has unknown type: {col_type}"
