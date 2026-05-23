"""Unit tests for the demo-data seed loader (scripts/seed.py).

Covers the pure CSV -> bronze mapping logic — value coercion, deterministic id
minting, and the per-row object/association build — without touching ClickHouse.
"""

import json
import sys
from pathlib import Path

import pytest

# scripts/ is not an importable package; add it to the path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import seed  # noqa: E402


def _row(**over):
    """A representative CSV row; override fields per test."""
    base = {
        "First Name": "Noah", "Last Name": "Wang", "Email": "Noah.Wang@northstarmfg.com",
        "Company Name": "Northstar Manufacturing", "Company domain Name": "northstarmfg.com",
        "Deal Name": "Northstar - APAC Expansion", "Deal Stage": "Closed won",
        "Deal Pipeline": "Sales Pipeline", "Deal Create Date": "03/29/2026",
        "Deal Close Date": "05/05/2026", "Deal Amount": "10500",
        "Deal Owner": "Sarah Chen", "Contact Owner": "Sarah Chen",
        "Lifecycle Stage": "Customer", "Job Title": "CTO", "Industry": "Manufacturing",
        "Number of Employees": "3700", "Country": "Canada",
        "Original Source": "Paid Social", "Original Source Drill-Down 1": "Twitter Ads",
        "Call title": "Final negotiation", "Call notes": "Closed at $95K",
        "Call direction": "Outbound", "Call Activity Date": "04/14/2026",
        "Email subject": "Kickoff", "Email body": "Hi Noah", "Email direction": "OUTGOING_EMAIL",
        "Email Activity Date": "05/05/2026",
        "Meeting Name": "Contract signature", "Meeting Description": "Sign MSA",
        "Meeting Start time": "04/01/2026 17:15", "Meeting end time": "04/01/2026 17:45",
        "Note body": "Closed multi-year", "Note Activity Date": "04/06/2026",
        "Task title": "Schedule check-in", "Due date": "06/02/2026",
    }
    base.update(over)
    return base


# ---- value coercion --------------------------------------------------------

def test_iso_date_american_format():
    assert seed._iso_date("03/29/2026") == "2026-03-29"
    assert seed._iso_date("4/7/2026") == "2026-04-07"
    assert seed._iso_date("") == ""
    assert seed._iso_date(None) == ""


def test_iso_datetime():
    assert seed._iso_datetime("04/01/2026 17:15") == "2026-04-01 17:15:00"
    assert seed._iso_datetime("") == ""


def test_duration_ms():
    assert seed._duration_ms("2026-04-01 17:15:00", "2026-04-01 17:45:00") == str(30 * 60 * 1000)
    assert seed._duration_ms("", "") == ""


# ---- id minting ------------------------------------------------------------

def test_idminter_is_deterministic_and_stable():
    m = seed.IdMinter()
    a = m.get("contact", "x@y.com")
    b = m.get("contact", "z@y.com")
    assert a != b
    assert m.get("contact", "x@y.com") == a  # stable on repeat
    # distinct ranges per kind
    assert m.get("deal", "x@y.com").startswith("4")
    assert a.startswith("3")


# ---- per-row build ---------------------------------------------------------

def test_add_row_builds_all_objects_and_associations():
    b = seed.SeedBuilder()
    b.add_row(_row())

    assert len(b.owners) == 1  # deal owner == contact owner
    assert len(b.companies) == 1
    assert len(b.deals) == 1
    assert len(b.contacts) == 1
    assert all(len(b.activities[k]) == 1 for k in ("call", "email", "meeting", "note", "task"))

    # contact -> company / deal links + activity links exist
    assert b.assoc["hs_assoc_contact_company"]
    assert b.assoc["hs_assoc_contact_deal"]
    assert b.assoc["hs_assoc_deal_company"]
    assert b.assoc["hs_assoc_call_deal"]


def test_deal_stage_maps_to_slug_and_close_flags():
    b = seed.SeedBuilder()
    b.add_row(_row(**{"Deal Stage": "Closed won"}))
    deal = next(iter(b.deals.values()))
    assert deal["dealstage"] == "closedwon"
    assert deal["pipeline"] == seed.PIPELINE_ID
    assert deal["hs_is_closed_won"] == "true"
    assert deal["hs_is_closed"] == "true"
    # current-stage entry date stamped at close time for a closed deal
    assert deal["hs_v2_date_entered_closedwon"] == "2026-05-05"

    b2 = seed.SeedBuilder()
    b2.add_row(_row(**{"Deal Stage": "Qualified to buy"}))
    d2 = next(iter(b2.deals.values()))
    assert d2["dealstage"] == "qualifiedtobuy"
    assert d2["hs_is_closed"] == "false"
    assert d2["hs_v2_date_entered_qualifiedtobuy"] == "2026-03-29"  # open -> create date


def test_contact_lifecycle_backfills_entry_dates():
    b = seed.SeedBuilder()
    b.add_row(_row(**{"Lifecycle Stage": "Sales Qualified Lead"}))
    c = next(iter(b.contacts.values()))
    assert c["lifecyclestage"] == "salesqualifiedlead"
    # reached MQL + SQL, not opportunity/customer
    assert c["hs_v2_date_entered_marketingqualifiedlead"]
    assert c["hs_v2_date_entered_salesqualifiedlead"]
    assert "hs_v2_date_entered_customer" not in c


def test_shared_deal_and_company_deduped_across_rows():
    b = seed.SeedBuilder()
    b.add_row(_row(Email="a@northstarmfg.com", **{"First Name": "A"}))
    b.add_row(_row(Email="b@northstarmfg.com", **{"First Name": "B"}))
    assert len(b.contacts) == 2
    assert len(b.companies) == 1  # same domain
    assert len(b.deals) == 1      # same deal name


def test_pipeline_raw_has_ordered_stages_with_metadata():
    b = seed.SeedBuilder()
    raw = b.pipeline_raw()
    assert raw["id"] == seed.PIPELINE_ID
    slugs = [s["id"] for s in raw["stages"]]
    assert slugs == [s[1] for s in seed.STAGE_DEFS]
    won = next(s for s in raw["stages"] if s["id"] == "closedwon")
    assert won["metadata"]["isClosed"] == "true"
    assert won["metadata"]["probability"] == "1.0"


# ---- bronze row shaping ----------------------------------------------------

def test_object_rows_shape_matches_live_extractor():
    b = seed.SeedBuilder()
    b.add_row(_row())
    rows = seed._object_rows(b, b.deals)
    rid, extracted_at, props_map, raw_json = rows[0]
    assert isinstance(props_map, dict)
    assert all(isinstance(v, str) for v in props_map.values())  # everything stringified
    raw = json.loads(raw_json)
    assert raw["id"] == rid
    assert raw["archived"] is False
    assert raw["properties"]["dealname"] == "Northstar - APAC Expansion"


def test_flat_json_rows_leave_properties_empty():
    b = seed.SeedBuilder()
    b.owner_id("Sarah Chen")
    rows = seed._flat_json_rows(b, b.owners)
    rid, extracted_at, props_map, raw_json = rows[0]
    assert props_map == {}  # owners/pipelines carry no properties map
    raw = json.loads(raw_json)
    assert raw["firstName"] == "Sarah"
    assert raw["email"].endswith(seed.DEMO_OWNER_EMAIL_DOMAIN)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
