from datetime import datetime
from unittest.mock import MagicMock, patch

from clickhouse_connect.driver.exceptions import OperationalError

import resources.clickhouse as ch_mod
from resources.clickhouse import ClickHouseResource


def make_resource():
    return ClickHouseResource(
        host="localhost",
        port=8123,
        username="hs2ch",
        password="test",
    )


def _reset_cache():
    ch_mod._client_cache.clear()


@patch("resources.clickhouse.clickhouse_connect.create_client")
def test_insert_records_calls_client(mock_create_client):
    _reset_cache()
    mock_client = MagicMock()
    mock_create_client.return_value = mock_client

    res = make_resource()
    rows = [("id1", datetime(2024, 1, 1), {"email": "a@b.com"}, '{"id":"id1"}')]
    count = res.insert_records("hs_contacts", rows)

    assert count == 1
    mock_client.insert.assert_called_once_with(
        "hs_contacts",
        data=[("id1", datetime(2024, 1, 1), {"email": "a@b.com"}, '{"id":"id1"}')],
        column_names=["_record_id", "_extracted_at", "properties", "_raw"],
    )


@patch("resources.clickhouse.clickhouse_connect.create_client")
def test_insert_records_empty_is_noop(mock_create_client):
    _reset_cache()
    mock_client = MagicMock()
    mock_create_client.return_value = mock_client

    res = make_resource()
    count = res.insert_records("hs_contacts", [])

    assert count == 0
    mock_client.insert.assert_not_called()


@patch("resources.clickhouse.clickhouse_connect.create_client")
def test_execute_sql_retries_after_stale_connection(mock_create_client):
    """If the cached client raises OperationalError, the resource should
    invalidate, dial a new client, and retry the command once."""
    _reset_cache()
    stale_client = MagicMock()
    stale_client.command.side_effect = OperationalError("Connection reset by peer")
    fresh_client = MagicMock()
    fresh_client.command.return_value = "ok"
    mock_create_client.side_effect = [stale_client, fresh_client]

    res = make_resource()
    result = res.execute_sql("SELECT 1")

    assert result == "ok"
    assert mock_create_client.call_count == 2
    stale_client.command.assert_called_once_with("SELECT 1")
    stale_client.close.assert_called_once()
    fresh_client.command.assert_called_once_with("SELECT 1")


@patch("resources.clickhouse.time.sleep")
@patch("resources.clickhouse.clickhouse_connect.create_client")
def test_execute_sql_waits_for_server_restart(mock_create_client, mock_sleep):
    """If the server dies mid-query and is briefly unreachable (e.g. OOM-kill +
    docker restart), the resource should poll until it answers ping() again,
    then retry the command instead of failing on a dead socket."""
    _reset_cache()
    dying_client = MagicMock()
    dying_client.command.side_effect = OperationalError("Connection reset by peer")
    fresh_client = MagicMock()
    fresh_client.ping.return_value = True
    fresh_client.command.return_value = "ok"
    # Two reconnect attempts hit a still-restarting server, third succeeds.
    mock_create_client.side_effect = [
        dying_client,
        OperationalError("connection refused"),
        OperationalError("connection refused"),
        fresh_client,
    ]

    res = make_resource()
    result = res.execute_sql("SELECT 1")

    assert result == "ok"
    assert mock_create_client.call_count == 4
    assert mock_sleep.call_count >= 2
    fresh_client.command.assert_called_once_with("SELECT 1")


@patch("resources.clickhouse.time.sleep")
@patch("resources.clickhouse.clickhouse_connect.create_client")
def test_execute_sql_raises_when_server_stays_down(mock_create_client, mock_sleep):
    """If the server never comes back within the reconnect window, the
    original OperationalError should surface rather than looping forever."""
    _reset_cache()
    dying_client = MagicMock()
    dying_client.command.side_effect = OperationalError("Connection reset by peer")
    mock_create_client.side_effect = [dying_client] + [
        OperationalError("connection refused")
    ] * 100

    res = make_resource()
    try:
        res.execute_sql("SELECT 1")
        raised = False
    except OperationalError:
        raised = True

    assert raised
    # Bounded: far fewer reconnect attempts than the side_effect allows.
    assert mock_create_client.call_count < 30


@patch("resources.clickhouse.time.sleep")
@patch("resources.clickhouse.clickhouse_connect.create_client")
def test_execute_sql_retries_op_after_second_reset(mock_create_client, mock_sleep):
    """A retry that itself hits a reset (server killed again) should trigger
    one more wait-and-retry cycle before giving up."""
    _reset_cache()
    dying1 = MagicMock()
    dying1.command.side_effect = OperationalError("Connection reset by peer")
    dying2 = MagicMock()
    dying2.ping.return_value = True
    dying2.command.side_effect = OperationalError("Connection reset by peer")
    fresh = MagicMock()
    fresh.ping.return_value = True
    fresh.command.return_value = "ok"
    mock_create_client.side_effect = [dying1, dying2, fresh]

    res = make_resource()
    result = res.execute_sql("SELECT 1")

    assert result == "ok"
    fresh.command.assert_called_once_with("SELECT 1")


@patch("resources.clickhouse.clickhouse_connect.create_client")
def test_insert_records_retries_after_stale_connection(mock_create_client):
    _reset_cache()
    stale_client = MagicMock()
    stale_client.insert.side_effect = OperationalError("Connection reset by peer")
    fresh_client = MagicMock()
    mock_create_client.side_effect = [stale_client, fresh_client]

    res = make_resource()
    rows = [("id1", datetime(2024, 1, 1), {"email": "a@b.com"}, '{}')]
    count = res.insert_records("hs_contacts", rows)

    assert count == 1
    assert mock_create_client.call_count == 2
    stale_client.insert.assert_called_once()
    fresh_client.insert.assert_called_once()
