import clickhouse_connect
from dagster import ConfigurableResource


class ClickHouseResource(ConfigurableResource):
    host: str
    port: int = 8123
    username: str
    password: str
    database: str = "bronze"

    def get_client(self):
        return clickhouse_connect.get_client(
            host=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            database=self.database,
        )

    def insert_records(self, table: str, rows: list[tuple]) -> int:
        """Insert rows as (record_id, extracted_at, raw_json) tuples.

        Args:
            table: ClickHouse table name (no database prefix — hs2ch user is scoped to bronze).
            rows: list of (_record_id, _extracted_at, _raw) tuples.

        Returns:
            Number of rows inserted.
        """
        if not rows:
            return 0
        client = self.get_client()
        client.insert(
            table,
            data=list(rows),
            column_names=["_record_id", "_extracted_at", "_raw"],
        )
        return len(rows)
