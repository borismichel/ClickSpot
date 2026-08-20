"""The Sync tab speaks HubSpot, not warehouse: curated names for the objects an
admin recognises, a generic phrase for everything else, and never a raw table
name in the operator-facing message."""

from __future__ import annotations

import pytest

from app.sync_naming import (
    STAGES,
    STAGE_BY_JOB,
    failure_message,
    operator_name,
)


def test_stages_cover_the_four_jobs_in_pipeline_order():
    assert [job for _, job, _ in STAGES] == [
        "bronze_job", "silver_job", "gold_job", "anon_job",
    ]
    assert STAGE_BY_JOB["bronze_job"] == "bronze"
    assert STAGE_BY_JOB["anon_job"] == "anon"


def test_stage_labels_use_operator_language():
    labels = [label for _, _, label in STAGES]
    assert labels == [
        "Fetching from HubSpot",
        "Preparing tables",
        "Building metrics",
        "Refreshing the anonymized copy",
    ]
    # The medallion vocabulary must not leak into what the operator reads.
    # (Whole words — "anonymized" is fine, the layer name "anon" is not.)
    banned = {"bronze", "silver", "gold", "anon", "asset", "op", "job", "sensor"}
    for label in labels:
        assert not banned & set(label.lower().split())


@pytest.mark.parametrize("step_key,expected", [
    ("hs_contacts", "Contacts"),
    ("dim_contacts", "Contacts"),
    ("hs_companies", "Companies"),
    ("dim_deals", "Deals"),
    ("hs_leads", "Leads"),
    ("hs_owners", "Owners"),
    ("dim_lists", "Lists"),
    ("hs_calls", "Activities"),
    ("fact_activities", "Activities"),
    ("fact_form_submissions", "Form submissions"),
    ("dim_pipeline_stages", "Deal pipeline stages"),
    ("dim_lead_pipelines", "Lead pipelines"),
    ("anon_dim_contacts", "Contacts"),  # anon mirrors reuse the silver name
])
def test_curated_names_for_hubspot_objects(step_key, expected):
    assert operator_name(step_key) == expected


@pytest.mark.parametrize("step_key", [
    "bridge_contact_company",     # join structure — not a HubSpot concept
    "hs_assoc_call_contact",
    "fact_stage_history",
    "dq_metrics",
    "agg_rep_performance",
    "anon_bridge_contact_deal",
])
def test_internal_tables_have_no_invented_name(step_key):
    assert operator_name(step_key) is None


def test_failure_names_the_hubspot_object():
    assert failure_message("silver", "dim_contacts") == "Sync failed while preparing Contacts"
    assert failure_message("bronze", "hs_deals") == "Sync failed while fetching Deals from HubSpot"


def test_failure_on_internal_table_falls_back_to_generic_phrase():
    msg = failure_message("silver", "bridge_contact_company")
    assert msg == "Sync failed while preparing internal tables"
    assert "bridge" not in msg  # the raw table name never reaches the operator


def test_failure_with_unknown_step_still_reads_cleanly():
    assert failure_message("bronze", None) == "Sync failed while fetching data from HubSpot"
    assert failure_message("gold", "agg_deal_health") == "Sync failed while building metrics"
    assert failure_message("anon", None) == "Sync failed while refreshing the anonymized copy"


def test_apply_stages_are_the_sync_stages_minus_the_fetch():
    from app.sync_naming import APPLY_STAGES
    assert APPLY_STAGES == STAGES[1:]
    assert [job for _, job, _ in APPLY_STAGES] == ["silver_job", "gold_job", "anon_job"]


def test_apply_failures_reuse_the_same_vocabulary():
    assert (failure_message("silver", "dim_contacts", kind="apply")
            == "Applying changes failed while preparing Contacts")
    assert (failure_message("silver", "bridge_contact_company", kind="apply")
            == "Applying changes failed while preparing internal tables")
    assert (failure_message("anon", None, kind="apply")
            == "Applying changes failed while refreshing the anonymized copy")
