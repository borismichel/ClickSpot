from datetime import datetime
from unittest.mock import MagicMock, patch
from resources.clickhouse import ClickHouseResource


def make_resource():
    return ClickHouseResource(
        host="localhost",
        port=8123,
        username="hs2ch",
        password="test",
    )


@patch("resources.clickhouse.clickhouse_connect.get_client")
def test_insert_records_calls_client(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    res = make_resource()
    rows = [("id1", datetime(2024, 1, 1), '{"id":"id1"}')]
    count = res.insert_records("hs_contacts", rows)

    assert count == 1
    mock_client.insert.assert_called_once_with(
        "hs_contacts",
        data=[("id1", datetime(2024, 1, 1), '{"id":"id1"}')],
        column_names=["_record_id", "_extracted_at", "_raw"],
    )


@patch("resources.clickhouse.clickhouse_connect.get_client")
def test_insert_records_empty_is_noop(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    res = make_resource()
    count = res.insert_records("hs_contacts", [])

    assert count == 0
    mock_client.insert.assert_not_called()
