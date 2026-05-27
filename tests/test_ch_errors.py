"""Tests for app.ch_errors.safe_clickhouse_error (CLI-124).

Two guarantees: guardrail failures (out-of-memory, timeout) get a friendly,
actionable message; and nothing — friendly or not — ever leaks the raw
exception (server version, host:port, file paths, internal table names).
"""

from app.ch_errors import safe_clickhouse_error

# Realistic clickhouse_connect exception strings. These embed exactly the bits
# we must never surface to a client: version, host:port, internal table names.
MEMORY_ERR = (
    "Code: 241. DB::Exception: Received from localhost:9000. DB::Exception: "
    "Memory limit (for query) exceeded: would use 2.05 GiB (attempt to "
    "allocate chunk of 4.00 MiB bytes), maximum: 2.00 GiB. "
    "(MEMORY_LIMIT_EXCEEDED) (version 26.2.5.45 (official build))"
)
TIMEOUT_ERR = (
    "Code: 159. DB::Exception: Timeout exceeded: elapsed 60.001 seconds, "
    "maximum: 60. (TIMEOUT_EXCEEDED) (version 26.2.5.45 (official build))"
)
UNKNOWN_TABLE_ERR = (
    "Code: 60. DB::Exception: Received from localhost:9000. DB::Exception: "
    "Table silver.dim_foo doesn't exist. (UNKNOWN_TABLE) "
    "(version 26.2.5.45 (official build))"
)

# Substrings that would constitute a leak if they ever reached the client.
LEAK_MARKERS = [
    "version",
    "localhost",
    "9000",
    "DB::Exception",
    "GiB",
    "silver.dim_foo",
    "official build",
]


def _assert_no_leak(message: str):
    for marker in LEAK_MARKERS:
        assert marker not in message, f"leaked {marker!r} in: {message!r}"


class TestFriendlyGuardrailMessages:
    def test_memory_limit_by_code_and_class(self):
        msg = safe_clickhouse_error(Exception(MEMORY_ERR))
        assert "memory" in msg.lower()
        # Actionable: tells the user how to make the query smaller.
        assert "GROUP BY" in msg or "filter" in msg.lower() or "narrow" in msg.lower()
        # Not the bare "ClickHouse error 241: ..." form.
        assert "241" not in msg
        assert "MEMORY_LIMIT_EXCEEDED" not in msg
        _assert_no_leak(msg)

    def test_timeout_exceeded(self):
        msg = safe_clickhouse_error(Exception(TIMEOUT_ERR))
        assert "time" in msg.lower()
        assert "filter" in msg.lower() or "narrow" in msg.lower()
        assert "159" not in msg
        _assert_no_leak(msg)

    def test_memory_limit_class_only_no_code(self):
        # Some driver paths drop the leading "Code: N"; the class name is enough.
        err = "DB::Exception: would use 2.05 GiB. (MEMORY_LIMIT_EXCEEDED)"
        msg = safe_clickhouse_error(Exception(err))
        assert "memory" in msg.lower()
        _assert_no_leak(msg)


class TestSanitizationUnchanged:
    def test_unknown_table_shows_code_and_class_only(self):
        msg = safe_clickhouse_error(Exception(UNKNOWN_TABLE_ERR))
        assert msg == "ClickHouse error 60: UNKNOWN_TABLE"
        _assert_no_leak(msg)

    def test_class_only_when_no_code(self):
        err = "DB::Exception: Table silver.dim_foo doesn't exist. (UNKNOWN_TABLE)"
        msg = safe_clickhouse_error(Exception(err))
        assert msg == "ClickHouse error: UNKNOWN_TABLE"
        _assert_no_leak(msg)

    def test_generic_fallback_when_nothing_parseable(self):
        msg = safe_clickhouse_error(Exception("connection reset by peer"))
        assert msg == "Query execution failed"
