import json
from datetime import datetime
from unittest.mock import MagicMock

from assets.activities import hs_calls, hs_meetings, hs_engagement_emails, hs_notes, hs_tasks
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


def test_calls_inserts_to_correct_table():
    hs = _mock_hubspot([[{"id": "call1", "properties": {}}]])
    ch = _mock_clickhouse()
    ctx = _make_mock_context()

    results = _call_asset(hs_calls, ctx, hubspot=hs, ch=ch)

    assert len(results) == 1
    table_arg = ch.insert_records.call_args[0][0]
    assert table_arg == "hs_calls"
    hs.fetch_crm_objects_batched.assert_called_once()
    assert hs.fetch_crm_objects_batched.call_args[0][0] == "calls"


def test_meetings_inserts_to_correct_table():
    hs = _mock_hubspot([[{"id": "meeting1", "properties": {}}]])
    ch = _mock_clickhouse()
    ctx = _make_mock_context()

    results = _call_asset(hs_meetings, ctx, hubspot=hs, ch=ch)

    assert len(results) == 1
    table_arg = ch.insert_records.call_args[0][0]
    assert table_arg == "hs_meetings"
    hs.fetch_crm_objects_batched.assert_called_once()
    assert hs.fetch_crm_objects_batched.call_args[0][0] == "meetings"


def test_engagement_emails_inserts_to_correct_table():
    hs = _mock_hubspot([[{"id": "email1", "properties": {}}]])
    ch = _mock_clickhouse()
    ctx = _make_mock_context()

    results = _call_asset(hs_engagement_emails, ctx, hubspot=hs, ch=ch)

    assert len(results) == 1
    table_arg = ch.insert_records.call_args[0][0]
    assert table_arg == "hs_engagement_emails"
    hs.fetch_crm_objects_batched.assert_called_once()
    assert hs.fetch_crm_objects_batched.call_args[0][0] == "emails"


def test_notes_inserts_to_correct_table():
    hs = _mock_hubspot([[{"id": "note1", "properties": {}}]])
    ch = _mock_clickhouse()
    ctx = _make_mock_context()

    results = _call_asset(hs_notes, ctx, hubspot=hs, ch=ch)

    assert len(results) == 1
    table_arg = ch.insert_records.call_args[0][0]
    assert table_arg == "hs_notes"
    hs.fetch_crm_objects_batched.assert_called_once()
    assert hs.fetch_crm_objects_batched.call_args[0][0] == "notes"


def test_tasks_inserts_to_correct_table():
    hs = _mock_hubspot([[{"id": "task1", "properties": {}}]])
    ch = _mock_clickhouse()
    ctx = _make_mock_context()

    results = _call_asset(hs_tasks, ctx, hubspot=hs, ch=ch)

    assert len(results) == 1
    table_arg = ch.insert_records.call_args[0][0]
    assert table_arg == "hs_tasks"
    hs.fetch_crm_objects_batched.assert_called_once()
    assert hs.fetch_crm_objects_batched.call_args[0][0] == "tasks"


def test_all_five_activity_assets_exist():
    for asset_def in [hs_calls, hs_meetings, hs_engagement_emails, hs_notes, hs_tasks]:
        assert asset_def is not None
