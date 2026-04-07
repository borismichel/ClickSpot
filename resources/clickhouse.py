import clickhouse_connect
from dagster import ConfigurableResource


_client_cache: dict = {}


class ClickHouseResource(ConfigurableResource):
    host: str
    port: int = 8123
    username: str
    password: str
    database: str = "bronze"

    def get_client(self):
        cache_key = (self.host, self.port, self.username, self.password, self.database)
        client = _client_cache.get(cache_key)
        if client is None:
            client = clickhouse_connect.create_client(
                host=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                database=self.database,
                send_receive_timeout=600,
                autogenerate_session_id=False,
                settings={"cancel_http_readonly_queries_on_client_close": "0"},
            )
            _client_cache[cache_key] = client
        return client

    def insert_records(self, table: str, rows: list[tuple]) -> int:
        """Insert rows as (record_id, extracted_at, properties_map, raw_json) tuples.

        Args:
            table: ClickHouse table name (no database prefix — hs2ch user is scoped to bronze).
            rows: list of (_record_id, _extracted_at, properties, _raw) tuples.

        Returns:
            Number of rows inserted.
        """
        if not rows:
            return 0
        client = self.get_client()
        client.insert(
            table,
            data=list(rows),
            column_names=["_record_id", "_extracted_at", "properties", "_raw"],
        )
        return len(rows)

    def execute_sql(self, sql: str):
        """Execute a SQL command and return the result."""
        client = self.get_client()
        return client.command(sql)

    def insert_association_records(self, table: str, rows: list[tuple]) -> int:
        """Insert association rows as (from_id, to_id, association_type, extracted_at) tuples."""
        if not rows:
            return 0
        client = self.get_client()
        client.insert(
            table,
            data=list(rows),
            column_names=["_from_id", "_to_id", "_association_type", "_extracted_at"],
        )
        return len(rows)
