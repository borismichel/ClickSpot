import json
from datetime import datetime
from unittest.mock import MagicMock

from assets.crm import hs_contacts
from resources.hubspot import HubSpotResource
from resources.clickhouse import ClickHouseResource


def _mock_hubspot(batches):
    res = MagicMock(spec=HubSpotResource)
    res.fetch_crm_objects_batched.return_value = iter(batches)
    return res


def _mock_clickhouse():
    res = MagicMock(spec=ClickHouseResource)
    res.insert_records.side_effect = lambda table, rows: len(rows)
    return res


def _make_mock_context():
    """Build a minimal mock AssetExecutionContext (no Dagster machinery needed)."""
    ctx = MagicMock()
    # Simulate no previous materialization (first run)
    ctx.instance.get_latest_materialization_event.return_value = None
    return ctx


def _call_asset(asset_def, context, **resources):
    """Call the underlying asset function directly, bypassing Dagster resource validation."""
    fn = asset_def.op.compute_fn.decorated_fn
    return list(fn(context, **resources))


def test_contacts_inserts_records_and_emits_metadata():
    hs = _mock_hubspot([[{"id": "c1", "properties": {"email": "a@b.com"}}]])
    ch = _mock_clickhouse()
    ctx = _make_mock_context()

    results = _call_asset(hs_contacts, ctx, hubspot=hs, ch=ch)

    # asset yields one MaterializeResult
    assert len(results) == 1

    # verify insert was called with the right table
    table_arg = ch.insert_records.call_args[0][0]
    assert table_arg == "hs_contacts"

    # verify rows have the expected shape: (record_id, datetime, json_str)
    rows = ch.insert_records.call_args[0][1]
    assert len(rows) == 1
    record_id, extracted_at, raw = rows[0]
    assert record_id == "c1"
    assert isinstance(extracted_at, datetime)
    parsed = json.loads(raw)
    assert parsed["id"] == "c1"


def test_contacts_no_records_still_succeeds():
    hs = _mock_hubspot([])
    ch = _mock_clickhouse()
    ctx = _make_mock_context()

    results = _call_asset(hs_contacts, ctx, hubspot=hs, ch=ch)

    # asset should still yield a MaterializeResult with zero records
    assert len(results) == 1
    ch.insert_records.assert_not_called()
