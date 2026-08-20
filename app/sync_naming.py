"""Operator-facing language for the Sync tab.

The audience is a HubSpot admin, not a warehouse engineer: stages are described
by what they do ("Fetching from HubSpot"), and a failure names the HubSpot
object it hit ("Sync failed while preparing Contacts"). Two rules govern the
mapping:

  - never invent a HubSpot concept that does not exist, and
  - never show a raw table name in the operator-facing message.

Tables with no fair HubSpot name — association bridges, stage history, quality
metrics, the gold aggregates — fall back to a generic phrase. The raw step key
still travels alongside the message for whoever follows the details link.
"""

from __future__ import annotations

# Correlation tags stamped on the run that starts a sync and propagated by the
# chaining sensors (see sensors.py). SYNC_MARKER_* is constant so the latest
# sync is findable with one tag-filtered query; SYNC_ID_TAG separates syncs.
SYNC_MARKER_TAG = "clickspot/sync"
SYNC_MARKER_VALUE = "ui"
SYNC_ID_TAG = "clickspot/sync_id"

# Distinguishes the two operations sharing the sync surface: a full "sync"
# (bronze onward, fetches HubSpot) and an "apply" of settings changes (silver
# onward, rebuilds from data already stored). Absent on pre-existing runs,
# which are all syncs.
SYNC_KIND_TAG = "clickspot/kind"

# The four stages of a sync, in pipeline order: (stage key, job name, label).
STAGES: list[tuple[str, str, str]] = [
    ("bronze", "bronze_job", "Fetching from HubSpot"),
    ("silver", "silver_job", "Preparing tables"),
    ("gold", "gold_job", "Building metrics"),
    ("anon", "anon_job", "Refreshing the anonymized copy"),
]

# An apply skips the HubSpot fetch — same stages, same labels, minus bronze.
APPLY_STAGES: list[tuple[str, str, str]] = STAGES[1:]

STAGE_BY_JOB = {job: stage for stage, job, _ in STAGES}

# The four jobs that make up a sync, in order — the single place they are
# enumerated (dagster_client takes job names as arguments).
SYNC_JOBS = tuple(STAGE_BY_JOB)

# Step key → the HubSpot thing an admin recognises. Anything absent here has no
# fair HubSpot name and gets the stage's generic phrase instead.
_OPERATOR_NAMES: dict[str, str] = {
    # bronze
    "hs_contacts": "Contacts",
    "hs_companies": "Companies",
    "hs_deals": "Deals",
    "hs_leads": "Leads",
    "hs_owners": "Owners",
    "hs_lists": "Lists",
    "hs_calls": "Activities",
    "hs_meetings": "Activities",
    "hs_engagement_emails": "Activities",
    "hs_notes": "Activities",
    "hs_tasks": "Activities",
    "hs_campaigns": "Campaigns",
    "hs_forms": "Forms",
    "hs_form_submissions": "Form submissions",
    "hs_pipelines": "Deal pipelines",
    "hs_lead_pipelines": "Lead pipelines",
    # silver
    "dim_contacts": "Contacts",
    "dim_companies": "Companies",
    "dim_deals": "Deals",
    "dim_leads": "Leads",
    "dim_owners": "Owners",
    "dim_lists": "Lists",
    "dim_pipelines": "Deal pipelines",
    "dim_pipeline_stages": "Deal pipeline stages",
    "dim_lead_pipelines": "Lead pipelines",
    "dim_lead_pipeline_stages": "Lead pipeline stages",
    "fact_activities": "Activities",
    "fact_form_submissions": "Form submissions",
}


def operator_name(step_key: str) -> str | None:
    """The HubSpot-facing name for a step key, or None if no fair name exists."""
    if step_key.startswith("anon_"):
        # Anon assets mirror silver/gold tables under an anon_ prefix.
        return operator_name(step_key[len("anon_"):])
    return _OPERATOR_NAMES.get(step_key)


# How each operation names itself in a failure sentence.
_FAILURE_SUBJECT = {"sync": "Sync", "apply": "Applying changes"}


def failure_message(stage: str, step_key: str | None, kind: str = "sync") -> str:
    """One sentence naming what broke, in the operator's language."""
    subject = _FAILURE_SUBJECT.get(kind, "Sync")
    name = operator_name(step_key) if step_key else None
    if stage == "bronze":
        if name:
            return f"{subject} failed while fetching {name} from HubSpot"
        return f"{subject} failed while fetching data from HubSpot"
    if stage == "silver":
        if name:
            return f"{subject} failed while preparing {name}"
        return f"{subject} failed while preparing internal tables"
    if stage == "gold":
        return f"{subject} failed while building metrics"
    if stage == "anon":
        if name:
            return f"{subject} failed while refreshing the anonymized copy of {name}"
        return f"{subject} failed while refreshing the anonymized copy"
    return f"{subject} failed"
