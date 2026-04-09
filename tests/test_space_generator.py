"""Tests for data space VIEW SQL generation."""

import pytest
from app.spaces.config import (
    BridgeDimension,
    BridgeStrategy,
    ComputedColumn,
    DataSpaceConfig,
    DictDimension,
    FKDimension,
    GrainConfig,
)
from app.spaces.generator import generate_view_sql, generate_select_sql


def _normalize(sql: str) -> str:
    """Collapse whitespace for comparison."""
    return " ".join(sql.split())


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _grain_leads() -> GrainConfig:
    return GrainConfig(
        entity="dim_leads",
        key="lead_id",
        columns=["hs_lead_name", "createdate", "hubspot_owner_id"],
    )


def _grain_deals() -> GrainConfig:
    return GrainConfig(
        entity="dim_deals",
        key="deal_id",
        columns=["dealname", "amount", "closedate"],
    )


def _bridge_deals_one_to_one() -> BridgeDimension:
    return BridgeDimension(
        entity="dim_deals",
        bridge="bridge_deal_lead",
        bridge_grain_key="lead_id",
        bridge_dim_key="deal_id",
        dim_key="deal_id",
        strategy=BridgeStrategy.one_to_one,
        columns=["dealname", "amount", "hs_is_closed_won"],
        prefix="deal_",
    )


def _bridge_contacts_any() -> BridgeDimension:
    return BridgeDimension(
        entity="dim_contacts",
        bridge="bridge_lead_contact",
        bridge_grain_key="lead_id",
        bridge_dim_key="contact_id",
        dim_key="contact_id",
        strategy=BridgeStrategy.any,
        columns=["full_name", "email"],
        prefix="contact_",
    )


def _bridge_contacts_latest() -> BridgeDimension:
    return BridgeDimension(
        entity="dim_contacts",
        bridge="bridge_lead_contact",
        bridge_grain_key="lead_id",
        bridge_dim_key="contact_id",
        dim_key="contact_id",
        strategy=BridgeStrategy.latest,
        columns=["full_name", "email"],
        prefix="contact_",
        timestamp_col="createdate",
    )


def _bridge_contacts_aggregate() -> BridgeDimension:
    return BridgeDimension(
        entity="dim_contacts",
        bridge="bridge_contact_deal",
        bridge_grain_key="deal_id",
        bridge_dim_key="contact_id",
        dim_key="contact_id",
        strategy=BridgeStrategy.aggregate,
        columns=[],
        prefix="contact_",
        agg_expressions=[
            {"alias": "contact_count", "expr": "count()"},
            {"alias": "emails", "expr": "groupUniqArray(d.email)"},
        ],
    )


def _bridge_contacts_fan_out() -> BridgeDimension:
    return BridgeDimension(
        entity="dim_contacts",
        bridge="bridge_lead_contact",
        bridge_grain_key="lead_id",
        bridge_dim_key="contact_id",
        dim_key="contact_id",
        strategy=BridgeStrategy.fan_out,
        columns=["full_name", "email"],
        prefix="contact_",
    )


def _fk_owners() -> FKDimension:
    return FKDimension(
        entity="dim_owners",
        dim_key="owner_id",
        fk_from="hubspot_owner_id",
        fk_to="owner_id",
        columns=["first_name", "last_name"],
        prefix="owner_",
    )


# ---------------------------------------------------------------------------
# Basic tests
# ---------------------------------------------------------------------------

class TestViewGeneration:
    def test_grain_only(self):
        config = DataSpaceConfig(
            id="leads_basic",
            name="Basic Leads",
            grain=_grain_leads(),
            default_filter="grain.archived = 0",
        )
        sql = generate_view_sql(config)
        assert "CREATE OR REPLACE VIEW gold.ds_leads_basic AS" in sql
        assert "FROM silver.dim_leads AS grain" in sql
        assert "grain.lead_id" in sql
        assert "grain.hs_lead_name" in sql
        assert "WHERE grain.archived = 0" in sql

    def test_generate_select_strips_create(self):
        config = DataSpaceConfig(
            id="leads_basic",
            name="Basic Leads",
            grain=_grain_leads(),
        )
        sql = generate_select_sql(config)
        assert not sql.startswith("CREATE")
        assert sql.startswith("SELECT")

    def test_pk_always_included(self):
        config = DataSpaceConfig(
            id="test",
            name="Test",
            grain=GrainConfig(entity="dim_deals", key="deal_id", columns=["dealname"]),
        )
        sql = generate_view_sql(config)
        assert "grain.deal_id" in sql


# ---------------------------------------------------------------------------
# Bridge strategies
# ---------------------------------------------------------------------------

class TestOneToOneStrategy:
    def test_full_outer_join(self):
        config = DataSpaceConfig(
            id="lead_deals",
            name="Lead→Deal",
            grain=_grain_leads(),
            dimensions=[_bridge_deals_one_to_one()],
        )
        sql = generate_view_sql(config)
        norm = _normalize(sql)
        assert "FULL OUTER JOIN" in sql
        assert "deal_dealname" in sql or "dim0.dealname AS deal_dealname" in sql
        assert "dim0.amount AS deal_amount" in sql
        assert "ON grain.lead_id = dim0.lead_id" in norm


class TestAnyStrategy:
    def test_any_aggregation(self):
        config = DataSpaceConfig(
            id="lead_contacts",
            name="Lead→Contact",
            grain=_grain_leads(),
            dimensions=[_bridge_contacts_any()],
        )
        sql = generate_view_sql(config)
        norm = _normalize(sql)
        assert "any(d.full_name) AS full_name" in norm
        assert "any(d.email) AS email" in norm
        assert "GROUP BY b.lead_id" in sql
        assert "LEFT JOIN" in sql
        assert "contact_full_name" in sql or "dim0.full_name AS contact_full_name" in sql


class TestLatestStrategy:
    def test_argmax(self):
        config = DataSpaceConfig(
            id="lead_latest_contact",
            name="Lead→Latest Contact",
            grain=_grain_leads(),
            dimensions=[_bridge_contacts_latest()],
        )
        sql = generate_view_sql(config)
        norm = _normalize(sql)
        assert "argMax(d.full_name, d.createdate)" in norm
        assert "GROUP BY b.lead_id" in sql
        assert "LEFT JOIN" in sql


class TestAggregateStrategy:
    def test_aggregate_expressions(self):
        config = DataSpaceConfig(
            id="deal_contacts_agg",
            name="Deal→Contact Counts",
            grain=_grain_deals(),
            dimensions=[_bridge_contacts_aggregate()],
        )
        sql = generate_view_sql(config)
        norm = _normalize(sql)
        assert "count() AS contact_count" in norm
        assert "groupUniqArray(d.email) AS emails" in norm
        assert "contact_contact_count" in sql or "dim0.contact_count AS contact_contact_count" in sql


class TestFanOutStrategy:
    def test_plain_left_join(self):
        config = DataSpaceConfig(
            id="lead_all_contacts",
            name="Lead→All Contacts",
            grain=_grain_leads(),
            dimensions=[_bridge_contacts_fan_out()],
        )
        sql = generate_view_sql(config)
        norm = _normalize(sql)
        assert "LEFT JOIN silver.bridge_lead_contact" in norm
        assert "LEFT JOIN silver.dim_contacts" in norm
        assert "contact_full_name" in sql


# ---------------------------------------------------------------------------
# FK joins
# ---------------------------------------------------------------------------

class TestFKJoin:
    def test_fk_left_join(self):
        config = DataSpaceConfig(
            id="leads_with_owners",
            name="Leads + Owners",
            grain=_grain_leads(),
            dimensions=[_fk_owners()],
        )
        sql = generate_view_sql(config)
        norm = _normalize(sql)
        assert "LEFT JOIN silver.dim_owners AS fk0" in norm
        assert "grain.hubspot_owner_id = fk0.owner_id" in norm
        assert "owner_first_name" in sql
        assert "owner_last_name" in sql


# ---------------------------------------------------------------------------
# Dict lookups
# ---------------------------------------------------------------------------

class TestDictLookup:
    def test_dictget_no_join(self):
        config = DataSpaceConfig(
            id="leads_dict_owners",
            name="Leads + Dict Owners",
            grain=_grain_leads(),
            dimensions=[
                DictDimension(
                    entity="dim_owners",
                    dict_name="dict_owners",
                    key_expr="grain.hubspot_owner_id",
                    columns=["first_name", "last_name"],
                    prefix="owner_",
                ),
            ],
        )
        sql = generate_view_sql(config)
        norm = _normalize(sql)
        # Should use dictGet, not JOIN
        assert "dictGet('silver.dict_owners', 'first_name', grain.hubspot_owner_id) AS owner_first_name" in norm
        assert "dictGet('silver.dict_owners', 'last_name', grain.hubspot_owner_id) AS owner_last_name" in norm
        assert "LEFT JOIN" not in sql
        assert "JOIN" not in norm or "FULL OUTER JOIN" not in norm

    def test_dict_mixed_with_bridge(self):
        """Dict and bridge dimensions can coexist."""
        config = DataSpaceConfig(
            id="leads_mixed",
            name="Leads Mixed",
            grain=_grain_leads(),
            dimensions=[
                _bridge_deals_one_to_one(),
                DictDimension(
                    entity="dim_owners",
                    dict_name="dict_owners",
                    key_expr="grain.hubspot_owner_id",
                    columns=["first_name"],
                    prefix="owner_",
                ),
            ],
        )
        sql = generate_view_sql(config)
        # Bridge produces a JOIN
        assert "FULL OUTER JOIN" in sql
        # Dict produces no extra JOIN
        assert "dictGet('silver.dict_owners', 'first_name', grain.hubspot_owner_id) AS owner_first_name" in sql


# ---------------------------------------------------------------------------
# Computed columns
# ---------------------------------------------------------------------------

class TestComputedColumns:
    def test_computed_expression(self):
        config = DataSpaceConfig(
            id="leads_computed",
            name="Leads Computed",
            grain=_grain_leads(),
            computed=[
                ComputedColumn(alias="days_since_creation", expr="dateDiff('day', grain.createdate, today())"),
            ],
        )
        sql = generate_view_sql(config)
        assert "dateDiff('day', grain.createdate, today()) AS days_since_creation" in sql


# ---------------------------------------------------------------------------
# Combined: full data space
# ---------------------------------------------------------------------------

class TestFullDataSpace:
    def test_lead_pipeline_analysis(self):
        config = DataSpaceConfig(
            id="lead_pipeline",
            name="Lead Pipeline Analysis",
            grain=_grain_leads(),
            dimensions=[
                _bridge_deals_one_to_one(),
                _bridge_contacts_any(),
                _fk_owners(),
            ],
            computed=[
                ComputedColumn(
                    alias="has_deal",
                    expr="if(dim0.deal_id IS NOT NULL, 1, 0)",
                ),
            ],
            default_filter="grain.archived = 0",
        )
        sql = generate_view_sql(config)
        norm = _normalize(sql)

        # View name
        assert "gold.ds_lead_pipeline" in sql

        # Grain
        assert "FROM silver.dim_leads AS grain" in sql

        # One-to-one bridge
        assert "FULL OUTER JOIN" in sql
        assert "deal_dealname" in sql

        # Any bridge
        assert "any(d.full_name)" in norm

        # FK
        assert "LEFT JOIN silver.dim_owners" in norm

        # Computed
        assert "has_deal" in sql

        # Default filter
        assert "WHERE grain.archived = 0" in sql


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestConfigValidation:
    def test_latest_requires_timestamp(self):
        with pytest.raises(ValueError, match="timestamp_col"):
            BridgeDimension(
                entity="dim_contacts",
                bridge="bridge_lead_contact",
                bridge_grain_key="lead_id",
                bridge_dim_key="contact_id",
                dim_key="contact_id",
                strategy=BridgeStrategy.latest,
                columns=["full_name"],
                prefix="contact_",
                # timestamp_col missing
            )

    def test_aggregate_requires_expressions(self):
        with pytest.raises(ValueError, match="agg_expressions"):
            BridgeDimension(
                entity="dim_contacts",
                bridge="bridge_contact_deal",
                bridge_grain_key="deal_id",
                bridge_dim_key="contact_id",
                dim_key="contact_id",
                strategy=BridgeStrategy.aggregate,
                columns=[],
                prefix="contact_",
                # agg_expressions missing
            )
