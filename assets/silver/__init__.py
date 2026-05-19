"""Silver layer assets — split out of the old assets/silver.py monolith.

External callers see the same names they used to import from assets.silver:
the per-asset symbols, the SQL helpers tests use, and `all_silver_assets`.
"""

from app.customer import extraction as _ext

# SQL helpers — re-exported so tests/test_silver_assets.py keeps working.
from .sql import _cast_expr, _build_ddl, _build_insert, _swap_table  # noqa: F401

# Asset symbols, by layer.
from .dims import (
    dim_contacts,
    dim_companies,
    dim_leads,
    dim_owners,
    dim_pipelines,
    dim_lead_pipelines,
    dim_deals,
    dim_pipeline_stages,
    dim_lead_pipeline_stages,
)
from .facts import fact_activities, fact_form_submissions, fact_stage_history
from .bridges import (
    bridge_contact_company,
    bridge_contact_deal,
    bridge_deal_company,
    bridge_lead_contact,
    bridge_deal_lead,
    bridge_lead_company,
    bridge_activity_contact,
    bridge_activity_company,
    bridge_activity_deal,
)
from .dq import dq_metrics


_ALL_SILVER_ASSET_MAP = {
    "dim_contacts": dim_contacts,
    "dim_companies": dim_companies,
    "dim_deals": dim_deals,
    "dim_leads": dim_leads,
    "dim_owners": dim_owners,
    "dim_pipelines": dim_pipelines,
    "dim_pipeline_stages": dim_pipeline_stages,
    "dim_lead_pipelines": dim_lead_pipelines,
    "dim_lead_pipeline_stages": dim_lead_pipeline_stages,
    "fact_activities": fact_activities,
    "fact_form_submissions": fact_form_submissions,
    "fact_stage_history": fact_stage_history,
    "bridge_contact_company": bridge_contact_company,
    "bridge_contact_deal": bridge_contact_deal,
    "bridge_deal_company": bridge_deal_company,
    "bridge_lead_contact": bridge_lead_contact,
    "bridge_deal_lead": bridge_deal_lead,
    "bridge_lead_company": bridge_lead_company,
    "bridge_activity_contact": bridge_activity_contact,
    "bridge_activity_company": bridge_activity_company,
    "bridge_activity_deal": bridge_activity_deal,
}


def _build_silver_assets():
    enabled = _ext.get_enabled_silver_tables()
    out = [a for name, a in _ALL_SILVER_ASSET_MAP.items() if name in enabled]
    # dq_metrics always runs — it tolerates missing tables gracefully via try/except
    out.append(dq_metrics)
    return out


all_silver_assets = _build_silver_assets()
