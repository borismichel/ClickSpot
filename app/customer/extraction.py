"""Per-portal extraction settings — which HubSpot objects extract into bronze,
and which silver columns those objects fan out into.

Single source of truth used by:
  - definitions.py (filter the assets list at startup)
  - assets/silver.py, assets/gold.py, assets/silver_anon.py, assets/gold_anon.py
    (filter their `all_*_assets` lists)
  - silver_config.py (compute extra silver columns + filter dictionary/bridge maps)
  - app/llm/schema_prompt.py (filter entity blocks so the LLM stops suggesting
    SQL against tables that no longer exist)

Stored in ~/.clickspot/customer.json alongside the portal onboarding keys,
under the "extraction" key. Missing block → everything enabled (current behavior),
so existing installs see zero change until they open the Settings UI.
"""

from __future__ import annotations

import copy
import logging
import uuid
from typing import Any

from app.customer import config as customer_config
from app.customer.extraction_rules import apply_cascade

log = logging.getLogger("app.customer.extraction")


# All HubSpot object toggles, with their full-tree default (everything enabled).
DEFAULT_OBJECTS: dict[str, Any] = {
    "contacts": True,
    "companies": True,
    "deals": True,
    "leads": True,
    "owners": True,
    "deal_pipelines": True,
    "lead_pipelines": True,
    "activities": {
        "calls": True,
        "meetings": True,
        "emails": True,
        "notes": True,
        "tasks": True,
    },
    "campaigns": True,
    "forms": True,
    "form_submissions": True,
    "lists": True,
}


# Bronze tables produced per object — used to derive the filtered asset list
# in definitions.py without per-asset string-matching boilerplate.
BRONZE_TABLES: dict[str, list[str]] = {
    "contacts": ["hs_contacts"],
    "companies": ["hs_companies"],
    "deals": ["hs_deals"],
    "leads": ["hs_leads"],
    "owners": ["hs_owners"],
    "deal_pipelines": ["hs_pipelines"],
    "lead_pipelines": ["hs_lead_pipelines"],
    "campaigns": ["hs_campaigns"],
    "forms": ["hs_forms"],
    "form_submissions": ["hs_form_submissions"],
    "lists": ["hs_lists"],
    # activity sub-toggles
    "calls": ["hs_calls"],
    "meetings": ["hs_meetings"],
    "emails": ["hs_engagement_emails"],
    "notes": ["hs_notes"],
    "tasks": ["hs_tasks"],
}


# Bronze association tables per pair. Both endpoints must be enabled for the
# bronze association asset to load.
ASSOC_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "hs_assoc_contact_company": ("contacts", "companies"),
    "hs_assoc_contact_deal":    ("contacts", "deals"),
    "hs_assoc_deal_company":    ("deals", "companies"),
    "hs_assoc_lead_contact":    ("leads", "contacts"),
    "hs_assoc_deal_lead":       ("deals", "leads"),
    "hs_assoc_lead_company":    ("leads", "companies"),
    "hs_assoc_call_contact":    ("calls", "contacts"),
    "hs_assoc_meeting_contact": ("meetings", "contacts"),
    "hs_assoc_email_contact":   ("emails", "contacts"),
    "hs_assoc_note_contact":    ("notes", "contacts"),
    "hs_assoc_task_contact":    ("tasks", "contacts"),
    "hs_assoc_call_company":    ("calls", "companies"),
    "hs_assoc_meeting_company": ("meetings", "companies"),
    "hs_assoc_email_company":   ("emails", "companies"),
    "hs_assoc_note_company":    ("notes", "companies"),
    "hs_assoc_task_company":    ("tasks", "companies"),
    "hs_assoc_call_deal":       ("calls", "deals"),
    "hs_assoc_meeting_deal":    ("meetings", "deals"),
    "hs_assoc_email_deal":      ("emails", "deals"),
    "hs_assoc_note_deal":       ("notes", "deals"),
    "hs_assoc_task_deal":       ("tasks", "deals"),
    "hs_assoc_list_contact":    ("lists", "contacts"),
    "hs_assoc_list_company":    ("lists", "companies"),
    "hs_assoc_list_deal":       ("lists", "deals"),
    "hs_assoc_list_lead":       ("lists", "leads"),
}


# Silver-table dependency map (silver table name → set of required object keys).
# When ALL listed objects are enabled the silver table is built. If any are
# disabled the silver table is skipped — and downstream gold/anon tables that
# depend on it are also skipped.
SILVER_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "dim_contacts":               ("contacts",),
    "dim_companies":              ("companies",),
    "dim_deals":                  ("deals",),
    "dim_leads":                  ("leads",),
    "dim_owners":                 ("owners",),
    "dim_pipelines":              ("deal_pipelines",),
    "dim_pipeline_stages":        ("deal_pipelines",),
    "dim_lead_pipelines":         ("lead_pipelines",),
    "dim_lead_pipeline_stages":   ("lead_pipelines",),
    "fact_activities":            (),   # built from ANY enabled activity type
    "fact_form_submissions":      ("form_submissions",),
    "fact_stage_history":         (),   # built if at least one of leads/deals/contacts enabled
    "bridge_contact_company":     ("contacts", "companies"),
    "bridge_contact_deal":        ("contacts", "deals"),
    "bridge_deal_company":        ("deals", "companies"),
    "bridge_lead_contact":        ("leads", "contacts"),
    "bridge_deal_lead":           ("deals", "leads"),
    "bridge_lead_company":        ("leads", "companies"),
    "bridge_activity_contact":    ("contacts",),
    "bridge_activity_company":    ("companies",),
    "bridge_activity_deal":       ("deals",),
    "dim_lists":                  ("lists",),
    "bridge_list_contact":        ("lists", "contacts"),
    "bridge_list_company":        ("lists", "companies"),
    "bridge_list_deal":           ("lists", "deals"),
    "bridge_list_lead":           ("lists", "leads"),
}


# Gold-table dependency map (gold table → silver tables it reads). A gold
# aggregate is enabled only if ALL its silver dependencies are enabled.
GOLD_REQUIREMENTS: dict[str, tuple[str, ...]] = {
    "agg_deal_stage_funnel":   ("dim_deals", "dim_pipeline_stages"),
    "agg_deal_health":         ("dim_deals", "bridge_activity_deal", "fact_activities"),
    "agg_rep_performance":     ("dim_deals", "fact_activities", "dim_owners"),
    "agg_source_attribution":  ("dim_contacts", "bridge_contact_deal", "dim_deals"),
    "agg_lead_health":         ("dim_leads", "dim_owners", "dim_lead_pipelines", "dim_lead_pipeline_stages"),
    "agg_deal_cohorts":        ("dim_deals",),
    "fact_pipeline_snapshots": ("dim_deals", "dim_pipeline_stages"),
}


# ---------------------------------------------------------------------------
# Accessors (read from customer.json)
# ---------------------------------------------------------------------------

def _raw_extraction() -> dict[str, Any]:
    """Return the `extraction` block from customer.json, or the all-enabled default."""
    cfg = customer_config.load()
    raw = cfg.get("extraction") or {}
    objects = copy.deepcopy(DEFAULT_OBJECTS)
    objects = _deep_merge(objects, raw.get("objects") or {})
    silver_properties = raw.get("silver_properties") or {}
    # Run the cascade so downstream code reads a normalized, consistent view.
    objects = apply_cascade(objects)
    return {"objects": objects, "silver_properties": silver_properties}


def _deep_merge(base: dict, override: dict) -> dict:
    """Merge override into base in place (for the activities sub-dict)."""
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def load() -> dict[str, Any]:
    """Return the full normalized extraction block (cascade-resolved)."""
    return _raw_extraction()


def save(block: dict[str, Any]) -> dict[str, Any]:
    """Persist the extraction block into customer.json, re-applying the cascade.

    Returns the normalized block actually written so the caller can show it back
    to the user.
    """
    cfg = customer_config.load()
    incoming_objects = copy.deepcopy(DEFAULT_OBJECTS)
    incoming_objects = _deep_merge(incoming_objects, block.get("objects") or {})
    normalized_objects = apply_cascade(incoming_objects)
    normalized = {
        "objects": normalized_objects,
        "silver_properties": block.get("silver_properties") or {},
    }
    cfg["extraction"] = normalized
    customer_config.save(cfg)
    return normalized


# ---------------------------------------------------------------------------
# Pending-apply flag — "saved but not live yet"
# ---------------------------------------------------------------------------
# A settings save takes effect only after the operator applies it (reload the
# Dagster definitions + rebuild silver onward). The flag records that gap so
# the UI can show it; it holds a fresh token per save rather than a boolean so
# a completed apply clears only the pending state it was started for — a save
# landing mid-apply keeps the banner up.

PENDING_APPLY_KEY = "extraction_pending_apply"


def pending_apply_token() -> str | None:
    """The current pending-apply token, or None if nothing is pending."""
    token = customer_config.load().get(PENDING_APPLY_KEY)
    return str(token) if token else None


def mark_pending_apply() -> str:
    """Record that the saved configuration is not live yet; returns the token."""
    token = uuid.uuid4().hex[:12]
    cfg = customer_config.load()
    cfg[PENDING_APPLY_KEY] = token
    customer_config.save(cfg)
    return token


def clear_pending_apply(token: str) -> bool:
    """Clear the pending flag iff it still carries `token`. Returns True if cleared."""
    cfg = customer_config.load()
    if not token or cfg.get(PENDING_APPLY_KEY) != token:
        return False
    del cfg[PENDING_APPLY_KEY]
    customer_config.save(cfg)
    return True


def is_object_enabled(name: str) -> bool:
    """True if the given object key is enabled. Handles activity sub-toggles."""
    ext = _raw_extraction()
    objs = ext["objects"]
    if name in ("calls", "meetings", "emails", "notes", "tasks"):
        return bool((objs.get("activities") or {}).get(name, True))
    return bool(objs.get(name, True))


def get_enabled_objects() -> set[str]:
    """Flat set of enabled object keys (activity sub-toggles flattened)."""
    ext = _raw_extraction()
    objs = ext["objects"]
    enabled: set[str] = set()
    for key, val in objs.items():
        if key == "activities" and isinstance(val, dict):
            for act, on in val.items():
                if on:
                    enabled.add(act)
        elif val is True:
            enabled.add(key)
    return enabled


def get_enabled_bronze_tables() -> set[str]:
    """All bronze table names that should be materialized."""
    enabled = get_enabled_objects()
    tables: set[str] = set()
    for key, ts in BRONZE_TABLES.items():
        if key in enabled:
            tables.update(ts)
    return tables


def get_enabled_assoc_tables() -> set[str]:
    """All bronze association table names that should be materialized.

    An association loads only if both endpoint objects are enabled.
    """
    enabled = get_enabled_objects()
    return {
        table
        for table, requires in ASSOC_REQUIREMENTS.items()
        if all(r in enabled for r in requires)
    }


def get_enabled_silver_tables() -> set[str]:
    """Silver table names that should be built."""
    enabled = get_enabled_objects()
    tables: set[str] = set()
    for table, requires in SILVER_REQUIREMENTS.items():
        if not requires:
            # Special-case the cross-cutting facts
            if table == "fact_activities":
                if any(a in enabled for a in ("calls", "meetings", "emails", "notes", "tasks")):
                    tables.add(table)
            elif table == "fact_stage_history":
                if any(o in enabled for o in ("leads", "deals", "contacts")):
                    tables.add(table)
            continue
        if all(r in enabled for r in requires):
            tables.add(table)
    return tables


def get_enabled_gold_tables() -> set[str]:
    """Gold aggregate names that should be built."""
    silver_enabled = get_enabled_silver_tables()
    return {
        table
        for table, requires in GOLD_REQUIREMENTS.items()
        if all(r in silver_enabled for r in requires)
    }


def get_enabled_anon_silver_tables() -> set[str]:
    """Anon silver-mirror table names. Subset of silver tables; activity facts
    are intentionally excluded from anon (free text can't be safely masked)."""
    silver = get_enabled_silver_tables()
    excluded = {"fact_activities", "bridge_activity_contact", "bridge_activity_company", "bridge_activity_deal", "dq_metrics"}
    return silver - excluded


def get_enabled_anon_gold_tables() -> set[str]:
    """Anon gold-mirror table names."""
    return get_enabled_gold_tables()


def get_silver_column_overrides(dim_name: str) -> tuple[list[tuple[str, str, str]], list[str]]:
    """Return (extra_columns, removed_column_names) for the given silver dim.

    `extra_columns` is a list of (column, property, type) tuples ready to splice
    into the dim's "columns" list. `removed` is a list of column names to drop.
    Missing block → ([], []).
    """
    ext = _raw_extraction()
    props = (ext.get("silver_properties") or {}).get(dim_name) or {}
    extra_raw = props.get("extra") or []
    removed = list(props.get("removed") or [])
    extras: list[tuple[str, str, str]] = []
    for row in extra_raw:
        try:
            extras.append((str(row["column"]), str(row["property"]), str(row["type"])))
        except (KeyError, TypeError):
            log.warning("Skipping malformed silver_properties extra row: %r", row)
    return extras, removed


def summary() -> str:
    """One-line human summary for startup logging."""
    enabled = get_enabled_objects()
    return f"extraction: {len(enabled)} objects enabled — {', '.join(sorted(enabled))}"
