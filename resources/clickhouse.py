import clickhouse_connect
from clickhouse_connect.driver.exceptions import OperationalError
from dagster import ConfigurableResource


_client_cache: dict = {}


class ClickHouseResource(ConfigurableResource):
    host: str
    port: int = 8123
    username: str
    password: str
    database: str = "bronze"

    def _cache_key(self):
        return (self.host, self.port, self.username, self.password, self.database)

    def _create_client(self):
        return clickhouse_connect.create_client(
            host=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            database=self.database,
            send_receive_timeout=600,
            autogenerate_session_id=False,
            settings={"cancel_http_readonly_queries_on_client_close": "0"},
        )

    def get_client(self):
        key = self._cache_key()
        client = _client_cache.get(key)
        if client is None:
            client = self._create_client()
            _client_cache[key] = client
        return client

    def _invalidate_client(self):
        key = self._cache_key()
        client = _client_cache.pop(key, None)
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

    def _with_retry(self, op):
        """Run op(client); on stale-connection errors, recreate client and retry once."""
        try:
            return op(self.get_client())
        except OperationalError:
            self._invalidate_client()
            return op(self.get_client())

    def insert_records(self, table: str, rows: list[tuple]) -> int:
        """Insert rows as (record_id, extracted_at, properties_map, raw_json) tuples."""
        if not rows:
            return 0
        data = list(rows)
        self._with_retry(lambda c: c.insert(
            table,
            data=data,
            column_names=["_record_id", "_extracted_at", "properties", "_raw"],
        ))
        return len(rows)

    def execute_sql(self, sql: str):
        """Execute a SQL command and return the result."""
        return self._with_retry(lambda c: c.command(sql))

    def insert_association_records(self, table: str, rows: list[tuple]) -> int:
        """Insert association rows as (from_id, to_id, association_type, extracted_at) tuples."""
        if not rows:
            return 0
        data = list(rows)
        self._with_retry(lambda c: c.insert(
            table,
            data=data,
            column_names=["_from_id", "_to_id", "_association_type", "_extracted_at"],
        ))
        return len(rows)
