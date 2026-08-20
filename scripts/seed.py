"""Demo-data seed loader — CSV → ClickHouse, no HubSpot portal required.

Maps the flat HubSpot-export CSV in ``demo-data/clickspot-demo-data.csv`` into
the bronze layer (``properties`` Map + ``_raw`` JSON, keyed on ``_record_id``),
exactly as the live HubSpot extraction would, then materializes the
silver → gold → anon medallion layers via Dagster so the whole warehouse comes
up offline.

This is the keystone that lets a fresh checkout run with **no ``HUBSPOT_TOKEN``**:
the synthetic CRM is loaded straight into ClickHouse, the medallion pipeline
transforms it, and chat / dashboards / the data explorer work against real data.

Usage::

    python scripts/seed.py                 # full load: bronze + silver + gold + anon
    python scripts/seed.py --bronze-only   # only load bronze (skip transforms)
    python scripts/seed.py --csv PATH      # use a different export CSV
    python scripts/seed.py --skip-init     # assume bronze tables already exist

Reads ``CLICKHOUSE_HOST/PORT/USER/PASSWORD`` from ``.env``. Idempotent: synthetic
IDs are assigned deterministically in CSV order, and every bronze table is a
``ReplacingMergeTree`` keyed on the record id, so re-running replaces rather than
duplicates.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Make the repo root importable when run as `python scripts/seed.py`.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from resources.clickhouse import ClickHouseResource  # noqa: E402

load_dotenv()

DEFAULT_CSV = _REPO_ROOT / "demo-data" / "clickspot-demo-data.csv"

# Synthetic portal config — surfaced in click-through URLs etc. Arbitrary.
DEMO_OWNER_EMAIL_DOMAIN = "clickspot-demo.com"

# Sales pipeline definition. Maps the CSV's human stage labels to canonical
# HubSpot deal-stage slugs (so the `hs_v2_date_entered_<slug>` properties that
# gold's funnel reads line up), with display order + win/loss metadata.
PIPELINE_ID = "sales_pipeline"
PIPELINE_LABEL = "Sales Pipeline"
# (label, slug, display_order, is_closed, probability)
STAGE_DEFS = [
    ("Appointment scheduled",     "appointmentscheduled",   0, False, 0.2),
    ("Qualified to buy",          "qualifiedtobuy",         1, False, 0.4),
    ("Presentation scheduled",    "presentationscheduled",  2, False, 0.6),
    ("Decision maker bought-in",  "decisionmakerboughtin",  3, False, 0.8),
    ("Closed won",                "closedwon",              4, True,  1.0),
    ("Closed lost",               "closedlost",             5, True,  0.0),
]
STAGE_LABEL_TO_SLUG = {label: slug for label, slug, *_ in STAGE_DEFS}

LIFECYCLE_LABEL_TO_SLUG = {
    "Customer":               "customer",
    "Sales Qualified Lead":   "salesqualifiedlead",
    "Opportunity":            "opportunity",
    "Marketing Qualified Lead": "marketingqualifiedlead",
}
# Ordered so we can backfill the lifecycle-stage entry dates gold reads.
LIFECYCLE_ORDER = ["marketingqualifiedlead", "salesqualifiedlead", "opportunity", "customer"]


# ---------------------------------------------------------------------------
# Value coercion helpers
# ---------------------------------------------------------------------------

def _iso_date(value: str) -> str:
    """MM/DD/YYYY -> YYYY-MM-DD. Returns '' for blanks/unparseable input.

    HubSpot exports American-format dates; ClickHouse's parseDateTimeBestEffort
    is ambiguous on DD vs MM, so we normalise to ISO before storing.
    """
    value = (value or "").strip()
    if not value:
        return ""
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", value)
    if not m:
        return value  # already ISO or some other recognizable shape
    mm, dd, yyyy = m.groups()
    return f"{yyyy}-{int(mm):02d}-{int(dd):02d}"


def _iso_datetime(value: str) -> str:
    """MM/DD/YYYY HH:MM -> YYYY-MM-DD HH:MM:00. Returns '' for blanks."""
    value = (value or "").strip()
    if not value:
        return ""
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})$", value)
    if not m:
        return _iso_date(value)
    mm, dd, yyyy, hh, mi = m.groups()
    return f"{yyyy}-{int(mm):02d}-{int(dd):02d} {int(hh):02d}:{mi}:00"


def _duration_ms(start_iso: str, end_iso: str) -> str:
    """Milliseconds between two ISO datetimes, as a string. '' if not computable."""
    try:
        s = datetime.fromisoformat(start_iso)
        e = datetime.fromisoformat(end_iso)
        delta = int((e - s).total_seconds() * 1000)
        return str(delta) if delta >= 0 else ""
    except Exception:
        return ""


def _clean(value) -> str:
    return (value or "").strip()


# ---------------------------------------------------------------------------
# ID minting — deterministic per-type counters, assigned in first-seen order.
# Distinct numeric ranges per type keep IDs readable and collision-free.
# ---------------------------------------------------------------------------

class IdMinter:
    _BASES = {
        "owner":   100_000,
        "company": 2_000_000,
        "contact": 3_000_000,
        "deal":    4_000_000,
        "call":    5_000_000,
        "meeting": 6_000_000,
        "email":   7_000_000,
        "note":    8_000_000,
        "task":    9_000_000,
    }

    def __init__(self):
        self._counters = {k: 0 for k in self._BASES}
        self._registry: dict[tuple[str, str], str] = {}

    def get(self, kind: str, natural_key: str) -> str:
        """Return a stable id for (kind, natural_key), minting one on first sight."""
        rk = (kind, natural_key)
        if rk not in self._registry:
            self._counters[kind] += 1
            self._registry[rk] = str(self._BASES[kind] + self._counters[kind])
        return self._registry[rk]

    def seen(self, kind: str, natural_key: str) -> bool:
        return (kind, natural_key) in self._registry


# ---------------------------------------------------------------------------
# Record accumulators
# ---------------------------------------------------------------------------

class SeedBuilder:
    """Builds bronze object + association rows from CSV rows."""

    def __init__(self):
        self.ids = IdMinter()
        self.now = datetime.utcnow()

        # _record_id -> properties dict (we serialise to Map + _raw at insert time)
        self.owners: dict[str, dict] = {}
        self.companies: dict[str, dict] = {}
        self.contacts: dict[str, dict] = {}
        self.deals: dict[str, dict] = {}
        self.activities: dict[str, dict[str, dict]] = {
            "call": {}, "meeting": {}, "email": {}, "note": {}, "task": {}
        }
        # association table -> set of (from_id, to_id)
        self.assoc: dict[str, set[tuple[str, str]]] = {}

    # -- associations ------------------------------------------------------

    def _assoc(self, table: str, from_id: str, to_id: str):
        if not from_id or not to_id:
            return
        self.assoc.setdefault(table, set()).add((from_id, to_id))

    # -- owners ------------------------------------------------------------

    def owner_id(self, name: str) -> str:
        name = _clean(name)
        if not name:
            return ""
        oid = self.ids.get("owner", name)
        if oid not in self.owners:
            parts = name.split()
            first = parts[0]
            last = " ".join(parts[1:]) if len(parts) > 1 else ""
            slug = re.sub(r"[^a-z0-9]+", ".", name.lower()).strip(".")
            self.owners[oid] = {
                "id": oid,
                "firstName": first,
                "lastName": last,
                "email": f"{slug}@{DEMO_OWNER_EMAIL_DOMAIN}",
                "type": "PERSON",
                "userId": oid,
                "userIdIncludingInactive": oid,
                "archived": False,
                "createdAt": "2025-01-01T00:00:00Z",
                "updatedAt": "2025-01-01T00:00:00Z",
            }
        return oid

    # -- companies ---------------------------------------------------------

    def company_id(self, row: dict, owner_id: str, createdate: str) -> str:
        domain = _clean(row.get("Company domain Name"))
        name = _clean(row.get("Company Name"))
        natural = domain or name
        if not natural:
            return ""
        cid = self.ids.get("company", natural)
        rec = self.companies.get(cid)
        if rec is None:
            rec = {
                "hs_object_id": cid,
                "name": name,
                "domain": domain,
                "industry": _clean(row.get("Industry")),
                "numberofemployees": _clean(row.get("Number of Employees")),
                "country": _clean(row.get("Country")),
                "hubspot_owner_id": owner_id,
                "createdate": createdate,
            }
            self.companies[cid] = rec
        else:
            # Keep the earliest non-empty createdate we've seen.
            if createdate and (not rec["createdate"] or createdate < rec["createdate"]):
                rec["createdate"] = createdate
        return cid

    # -- deals -------------------------------------------------------------

    def deal_id(self, row: dict, owner_id: str, company_id: str, company_name: str) -> str:
        name = _clean(row.get("Deal Name"))
        if not name:
            return ""
        did = self.ids.get("deal", name)
        if did not in self.deals:
            stage_label = _clean(row.get("Deal Stage"))
            stage_slug = STAGE_LABEL_TO_SLUG.get(stage_label, "")
            createdate = _iso_date(row.get("Deal Create Date"))
            closedate = _iso_date(row.get("Deal Close Date"))
            is_won = stage_slug == "closedwon"
            is_closed = stage_slug in ("closedwon", "closedlost")
            stage_meta = next((s for s in STAGE_DEFS if s[1] == stage_slug), None)
            probability = stage_meta[4] if stage_meta else None

            props = {
                "hs_object_id": did,
                "dealname": name,
                "dealstage": stage_slug,
                "pipeline": PIPELINE_ID,
                "amount": _clean(row.get("Deal Amount")),
                "deal_currency_code": "USD",
                "company_name": company_name,
                "hubspot_owner_id": owner_id,
                "createdate": createdate,
                "closedate": closedate,
                "hs_is_closed_won": "true" if is_won else "false",
                "hs_is_closed": "true" if is_closed else "false",
            }
            if probability is not None:
                props["hs_deal_stage_probability"] = str(probability)
            # Record the stage-entry date gold's funnel reads. We only know the
            # *current* stage from a flat export, so stamp that one: open stages
            # at create time, closed stages at close time.
            if stage_slug:
                entry = closedate if is_closed else createdate
                if entry:
                    props[f"hs_v2_date_entered_{stage_slug}"] = entry
            self.deals[did] = props
        return did

    # -- contacts ----------------------------------------------------------

    def contact_id(self, row: dict, owner_id: str, createdate: str) -> str:
        email = _clean(row.get("Email")).lower()
        natural = email or f"{_clean(row.get('First Name'))} {_clean(row.get('Last Name'))}"
        if not natural.strip():
            return ""
        cid = self.ids.get("contact", natural)
        if cid not in self.contacts:
            first = _clean(row.get("First Name"))
            last = _clean(row.get("Last Name"))
            lifecycle = LIFECYCLE_LABEL_TO_SLUG.get(_clean(row.get("Lifecycle Stage")), "")
            props = {
                "hs_object_id": cid,
                "firstname": first,
                "lastname": last,
                "full_name": (first + " " + last).strip(),
                "email": _clean(row.get("Email")),
                "jobtitle": _clean(row.get("Job Title")),
                "lifecyclestage": lifecycle,
                "hs_analytics_source": _clean(row.get("Original Source")),
                "hs_analytics_source_data_1": _clean(row.get("Original Source Drill-Down 1")),
                "hubspot_owner_id": owner_id,
                "createdate": createdate,
            }
            # Backfill lifecycle entry dates up to the contact's current stage so
            # gold's MQL/SQL funnels have something to count.
            if lifecycle in LIFECYCLE_ORDER and createdate:
                reached = LIFECYCLE_ORDER[: LIFECYCLE_ORDER.index(lifecycle) + 1]
                for stage in reached:
                    props[f"hs_v2_date_entered_{stage}"] = createdate
            self.contacts[cid] = props
        return cid

    # -- activities --------------------------------------------------------

    def _activity(self, kind: str, natural_key: str, props: dict):
        if not natural_key:
            return None
        aid = self.ids.get(kind, natural_key)
        if aid not in self.activities[kind]:
            props["hs_object_id"] = aid
            self.activities[kind][aid] = props
        return aid

    def build_activities(self, row: dict, owner_id: str, contact_id: str,
                         company_id: str, deal_id: str):
        """Create the row's call/email/meeting/note/task and link them."""
        def link(kind_table: str, activity_id: str):
            if not activity_id:
                return
            self._assoc(f"hs_assoc_{kind_table}_contact", activity_id, contact_id)
            self._assoc(f"hs_assoc_{kind_table}_company", activity_id, company_id)
            self._assoc(f"hs_assoc_{kind_table}_deal", activity_id, deal_id)

        contact_key = contact_id  # one of each activity type per contact row

        # Call
        title = _clean(row.get("Call title"))
        ts = _iso_date(row.get("Call Activity Date"))
        if title or _clean(row.get("Call notes")):
            aid = self._activity("call", f"{contact_key}:call", {
                "hs_timestamp": ts,
                "hs_call_title": title,
                "hs_body_preview": _clean(row.get("Call notes")),
                "hs_call_disposition": _clean(row.get("Call direction")),
                "hubspot_owner_id": owner_id,
                "hs_createdate": ts,
                "hs_lastmodifieddate": ts,
            })
            link("call", aid)

        # Email
        subject = _clean(row.get("Email subject"))
        ts = _iso_date(row.get("Email Activity Date"))
        if subject or _clean(row.get("Email body")):
            aid = self._activity("email", f"{contact_key}:email", {
                "hs_timestamp": ts,
                "hs_email_subject": subject,
                "hs_email_direction": _clean(row.get("Email direction")),
                "hs_body_preview": _clean(row.get("Email body")),
                "hubspot_owner_id": owner_id,
                "hs_createdate": ts,
                "hs_lastmodifieddate": ts,
            })
            link("email", aid)

        # Meeting
        mname = _clean(row.get("Meeting Name"))
        start = _iso_datetime(row.get("Meeting Start time"))
        end = _iso_datetime(row.get("Meeting end time"))
        if mname or _clean(row.get("Meeting Description")):
            aid = self._activity("meeting", f"{contact_key}:meeting", {
                "hs_timestamp": start,
                "hs_meeting_title": mname,
                "hs_body_preview": _clean(row.get("Meeting Description")),
                "hs_meeting_start_time": start,
                "hs_meeting_end_time": end,
                "hs_meeting_duration": _duration_ms(start, end),
                "hubspot_owner_id": owner_id,
                "hs_createdate": start,
                "hs_lastmodifieddate": start,
            })
            link("meeting", aid)

        # Note
        note = _clean(row.get("Note body"))
        ts = _iso_date(row.get("Note Activity Date"))
        if note:
            aid = self._activity("note", f"{contact_key}:note", {
                "hs_timestamp": ts,
                "hs_body_preview": note,
                "hubspot_owner_id": owner_id,
                "hs_createdate": ts,
                "hs_lastmodifieddate": ts,
            })
            link("note", aid)

        # Task
        ttitle = _clean(row.get("Task title"))
        ts = _iso_date(row.get("Due date"))
        if ttitle:
            aid = self._activity("task", f"{contact_key}:task", {
                "hs_timestamp": ts,
                "hs_task_subject": ttitle,
                "hs_task_status": "NOT_STARTED",
                "hubspot_owner_id": owner_id,
                "hs_createdate": ts,
                "hs_lastmodifieddate": ts,
            })
            link("task", aid)

    # -- row driver --------------------------------------------------------

    def add_row(self, row: dict):
        contact_owner = self.owner_id(row.get("Contact Owner"))
        deal_owner = self.owner_id(row.get("Deal Owner")) or contact_owner

        createdate = _iso_date(row.get("Deal Create Date"))
        company_name = _clean(row.get("Company Name"))

        company_id = self.company_id(row, deal_owner, createdate)
        deal_id = self.deal_id(row, deal_owner, company_id, company_name)
        contact_id = self.contact_id(row, contact_owner, createdate)

        self._assoc("hs_assoc_contact_company", contact_id, company_id)
        self._assoc("hs_assoc_contact_deal", contact_id, deal_id)
        self._assoc("hs_assoc_deal_company", deal_id, company_id)

        self.build_activities(row, contact_owner, contact_id, company_id, deal_id)

    # -- pipeline ----------------------------------------------------------

    def pipeline_raw(self) -> dict:
        """Build the deal-pipeline JSON (with nested stages[]) for hs_pipelines."""
        stages = []
        for label, slug, order, is_closed, prob in STAGE_DEFS:
            stages.append({
                "id": slug,
                "label": label,
                "displayOrder": order,
                "metadata": {"isClosed": "true" if is_closed else "false",
                             "probability": str(prob)},
                "createdAt": "2025-01-01T00:00:00Z",
                "updatedAt": "2025-01-01T00:00:00Z",
                "archived": False,
            })
        return {
            "id": PIPELINE_ID,
            "label": PIPELINE_LABEL,
            "displayOrder": 0,
            "stages": stages,
            "createdAt": "2025-01-01T00:00:00Z",
            "updatedAt": "2025-01-01T00:00:00Z",
            "archived": False,
        }


# ---------------------------------------------------------------------------
# Bronze insertion
# ---------------------------------------------------------------------------

def _json_default(obj):
    if isinstance(obj, (datetime,)):
        return obj.isoformat()
    raise TypeError(f"not serialisable: {type(obj)}")


def _object_rows(builder: SeedBuilder, records: dict[str, dict], extra_raw=None):
    """Turn {id: properties} into bronze (id, extracted_at, props_map, raw_json) tuples.

    The `properties` Map mirrors the live extractor (all values stringified); the
    `_raw` JSON carries the same properties plus `id`/`archived` so the silver
    JSONExtractBool(_raw,'archived') and JSON-source dims behave identically.
    """
    rows = []
    for rid, props in records.items():
        props_map = {k: ("" if v is None else str(v)) for k, v in props.items()}
        raw = {"id": rid, "properties": props_map, "archived": False}
        if extra_raw:
            raw.update(extra_raw.get(rid, {}))
        rows.append((rid, builder.now, props_map, json.dumps(raw, default=_json_default)))
    return rows


def _flat_json_rows(builder: SeedBuilder, records: dict[str, dict]):
    """Bronze rows for JSON-source objects (owners, pipelines): _raw is the record
    itself, properties Map left empty (matches the live owners/pipelines assets)."""
    rows = []
    for rid, raw in records.items():
        rows.append((rid, builder.now, {}, json.dumps(raw, default=_json_default)))
    return rows


def load_bronze(builder: SeedBuilder, ch: ClickHouseResource) -> dict[str, int]:
    counts: dict[str, int] = {}

    def insert(table, rows):
        n = ch.insert_records(table, rows)
        counts[table] = n
        return n

    def insert_assoc(table, pairs):
        rows = [(f, t, "demo", builder.now) for f, t in sorted(pairs)]
        n = ch.insert_association_records(table, rows)
        counts[table] = n
        return n

    # Flat-JSON objects
    insert("hs_owners", _flat_json_rows(builder, builder.owners))
    insert("hs_pipelines", _flat_json_rows(builder, {PIPELINE_ID: builder.pipeline_raw()}))

    # Property-Map objects
    insert("hs_companies", _object_rows(builder, builder.companies))
    insert("hs_contacts", _object_rows(builder, builder.contacts))
    insert("hs_deals", _object_rows(builder, builder.deals))
    bronze_for_activity = {
        "call": "hs_calls", "meeting": "hs_meetings", "email": "hs_engagement_emails",
        "note": "hs_notes", "task": "hs_tasks",
    }
    for kind, table in bronze_for_activity.items():
        insert(table, _object_rows(builder, builder.activities[kind]))

    # Associations
    for table, pairs in builder.assoc.items():
        insert_assoc(table, pairs)

    return counts


# ---------------------------------------------------------------------------
# Schema init + medallion transforms
# ---------------------------------------------------------------------------

def run_init(client) -> None:
    """Execute scripts/init_clickhouse.sql (creates databases + bronze tables)."""
    from app.warehouse_init import ensure_schema
    ensure_schema(client)


def materialize_layers(host, port, user, password) -> None:
    """Run silver -> gold -> anon in-process via Dagster's single-threaded executor.

    Each layer is materialized on its own; cross-layer deps (bronze→silver,
    silver→gold, silver/gold→anon) are external AssetKeys, so a per-layer
    selection resolves cleanly without needing the bronze assets (or the
    HubSpot resource) in scope.
    """
    from dagster import materialize

    def ch(db):
        return ClickHouseResource(host=host, port=port, username=user,
                                  password=password, database=db)

    from assets.silver import all_silver_assets
    from assets.gold import all_gold_assets
    from assets.silver_anon import all_silver_anon_assets
    from assets.gold_anon import all_gold_anon_assets

    print("→ Materializing silver…")
    res = materialize(all_silver_assets, resources={"ch_silver": ch("silver")})
    if not res.success:
        raise RuntimeError("silver materialization failed")

    print("→ Materializing gold…")
    res = materialize(all_gold_assets, resources={"ch_gold": ch("gold")})
    if not res.success:
        raise RuntimeError("gold materialization failed")

    print("→ Materializing anon (silver_anon + gold_anon)…")
    res = materialize(
        all_silver_anon_assets + all_gold_anon_assets,
        resources={"ch_silver_anon": ch("silver_anon"), "ch_gold_anon": ch("gold_anon")},
    )
    if not res.success:
        raise RuntimeError("anon materialization failed")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Seed ClickHouse from the demo CSV (no HubSpot token needed).")
    parser.add_argument("--csv", default=str(DEFAULT_CSV), help="Path to the HubSpot-export CSV.")
    parser.add_argument("--bronze-only", action="store_true", help="Load bronze only; skip silver/gold/anon.")
    parser.add_argument("--skip-init", action="store_true", help="Assume databases + bronze tables already exist.")
    args = parser.parse_args(argv)

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"ERROR: CSV not found: {csv_path}", file=sys.stderr)
        return 2

    host = os.environ.get("CLICKHOUSE_HOST")
    user = os.environ.get("CLICKHOUSE_USER")
    password = os.environ.get("CLICKHOUSE_PASSWORD")
    port = int(os.environ.get("CLICKHOUSE_PORT", 8123))
    if not (host and user and password is not None):
        print("ERROR: set CLICKHOUSE_HOST / CLICKHOUSE_USER / CLICKHOUSE_PASSWORD in .env", file=sys.stderr)
        return 2

    ch = ClickHouseResource(host=host, port=port, username=user, password=password)

    if not args.skip_init:
        print("→ Initializing ClickHouse schema (databases + bronze tables)…")
        run_init(ch.get_client())

    # Parse + build
    import csv as _csv
    print(f"→ Reading {csv_path}…")
    builder = SeedBuilder()
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in _csv.DictReader(f):
            builder.add_row(row)

    print(
        f"   built: {len(builder.owners)} owners, {len(builder.companies)} companies, "
        f"{len(builder.contacts)} contacts, {len(builder.deals)} deals, "
        f"{sum(len(v) for v in builder.activities.values())} activities"
    )

    print("→ Loading bronze…")
    counts = load_bronze(builder, ch)
    total = sum(counts.values())
    for table in sorted(counts):
        print(f"   {counts[table]:6d}  bronze.{table}")
    print(f"   {total} bronze rows total")

    if args.bronze_only:
        print("✓ Bronze loaded (--bronze-only). Skipping silver/gold/anon.")
        return 0

    materialize_layers(host, port, user, password)
    print("✓ Seed complete: bronze → silver → gold → anon populated.")
    print("  Start the app (uvicorn app.main:app --port 8192) and open the UI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
