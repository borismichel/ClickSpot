import json
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from assets.marketing import hs_campaigns, hs_forms, hs_lead_pipelines
from resources.hubspot import HubSpotResource
from resources.clickhouse import ClickHouseResource


def _mock_hubspot(batches):
    res = MagicMock(spec=HubSpotResource)
    res.fetch_marketing_list.return_value = iter(batches)
    return res


def _mock_clickhouse():
    res = MagicMock(spec=ClickHouseResource)
    res.insert_records.side_effect = lambda table, rows: len(rows)
    return res


def _make_mock_context():
    """Build a minimal mock AssetExecutionContext (no Dagster machinery needed)."""
    ctx = MagicMock()
    ctx.instance.get_latest_materialization_event.return_value = None
    return ctx


def _call_asset(asset_def, context, **resources):
    """Call the underlying asset function directly, bypassing Dagster resource validation."""
    fn = asset_def.op.compute_fn.decorated_fn
    return list(fn(context, **resources))


def test_marketing_assets_exist():
    assert hs_campaigns is not None
    assert hs_forms is not None
    assert hs_lead_pipelines is not None


def test_campaigns_inserts_to_correct_table_and_calls_fetch_marketing_list():
    hs = _mock_hubspot([[{"id": "camp1", "name": "Summer Sale"}]])
    ch = _mock_clickhouse()
    ctx = _make_mock_context()

    results = _call_asset(hs_campaigns, ctx, hubspot=hs, ch=ch)

    assert len(results) == 1

    # Verify fetch_marketing_list was called with the campaigns path
    call_args = hs.fetch_marketing_list.call_args
    assert call_args[0][0] == "/marketing/v3/campaigns"

    # Verify insert was called with the correct table
    table_arg = ch.insert_records.call_args[0][0]
    assert table_arg == "hs_campaigns"


def test_campaigns_row_shape():
    hs = _mock_hubspot([[{"id": "camp1", "name": "Summer Sale"}]])
    ch = _mock_clickhouse()
    ctx = _make_mock_context()

    _call_asset(hs_campaigns, ctx, hubspot=hs, ch=ch)

    rows = ch.insert_records.call_args[0][1]
    assert len(rows) == 1
    record_id, extracted_at, properties, raw = rows[0]
    assert record_id == "camp1"
    assert isinstance(extracted_at, datetime)
    assert isinstance(properties, dict)
    parsed = json.loads(raw)
    assert parsed["id"] == "camp1"


def test_forms_inserts_to_correct_table():
    hs = _mock_hubspot([[{"id": "form1", "name": "Contact Form"}]])
    ch = _mock_clickhouse()
    ctx = _make_mock_context()

    results = _call_asset(hs_forms, ctx, hubspot=hs, ch=ch)

    assert len(results) == 1
    table_arg = ch.insert_records.call_args[0][0]
    assert table_arg == "hs_forms"

    call_args = hs.fetch_marketing_list.call_args
    assert call_args[0][0] == "/marketing/v3/forms"


def test_lead_pipelines_inserts_to_correct_table():
    hs = _mock_hubspot([[{"id": "pipe1", "label": "Default Lead Pipeline", "stages": []}]])
    ch = _mock_clickhouse()
    ctx = _make_mock_context()

    results = _call_asset(hs_lead_pipelines, ctx, hubspot=hs, ch=ch)

    assert len(results) == 1
    table_arg = ch.insert_records.call_args[0][0]
    assert table_arg == "hs_lead_pipelines"

    call_args = hs.fetch_marketing_list.call_args
    assert call_args[0][0] == "/crm/v3/pipelines/leads"


def test_campaigns_no_records_still_succeeds():
    hs = _mock_hubspot([])
    ch = _mock_clickhouse()
    ctx = _make_mock_context()

    results = _call_asset(hs_campaigns, ctx, hubspot=hs, ch=ch)

    assert len(results) == 1
    ch.insert_records.assert_not_called()
