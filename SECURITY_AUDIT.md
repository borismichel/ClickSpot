# Security Audit — 2026-04-06

## Critical (2)

### 1. SQL Injection via `/api/v1/query` — `condition` parameter
**`app/engine/sql_builder.py:218-220`**, **`app/api/models.py:10`**

The `condition` field in `MeasureRequest` accepts arbitrary strings and is interpolated directly into SQL:
```python
agg_expr = f"countIf({condition})"
agg_expr = f"{agg}If({column}, {condition})"
```
An attacker can POST to `/api/v1/query` with `"condition": "1=1) FROM system.one; DROP TABLE silver.dim_deals--"` and it goes straight into the query.

### 2. SQL Injection via unvalidated column names in `/api/v1/query`
**`app/engine/sql_builder.py:130,155,176,255-278,311-324`**

`column`, `group_by`, `date_column`, and `measure_column` from user requests are f-string interpolated into SQL without validation against `TABLES` config. Table names are checked, but column names are not. The `agg` parameter is also unvalidated in `build_measure_query`.

---

## High (5)

### 3. SQL Validator bypasses on chat endpoint
**`app/llm/sql_validator.py:23-65`**

The regex-based validator has multiple gaps:
- **`UNION` not blocked** — allows appending arbitrary SELECT queries
- **ClickHouse table functions** (`url()`, `remote()`, `file()`, `s3()`) not blocked — can exfiltrate data or read local files
- **Subqueries** bypass the `_TABLE_REF_PATTERN` regex (only catches `FROM/JOIN \s+table.name`, not nested subqueries)
- **`OPTIMIZE TABLE`** and other ClickHouse-specific DDL not in the blocklist

### 4. No authentication on any endpoint
**`app/main.py:11-26`**, **`app/api/chat_routes.py`**

Zero auth on all endpoints. Anyone on the network can execute queries, read/overwrite API keys, trigger schema rebuilds, read full DB schema.

### 5. Wildcard CORS
**`app/main.py:17-22`**

```python
allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
```
Combined with no auth, any website on the internet can make cross-origin requests to all endpoints.

### 6. API key exposure via settings endpoints
**`app/api/chat_routes.py:96-115`**, **`app/llm/config.py:79-83`**

`GET /api/v1/settings` returns masked keys (first 4 + last 4 chars). `PUT /api/v1/settings` accepts and stores new keys with no auth.

### 7. Sensitive business data in localStorage indefinitely
**`frontend/src/hooks/useConversations.ts:27-53`**

Full query results (deal amounts, contact details, revenue figures) persisted in `localStorage` with no expiration.

---

## Medium (6)

### 8. ClickHouse ports bound to 0.0.0.0 with weak credentials
**`docker-compose.yml:6-10`**

Ports `8124` and `9001` exposed to all interfaces. Credentials `hs2ch`/`hs2ch`. `CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT: 1` grants superuser access.

### 9. Selection column names not validated
**`app/engine/sql_builder.py:47-63`**

Selection dict keys interpolated into WHERE clauses without validation.

### 10. ClickHouse error messages leaked to client
**`app/api/chat_routes.py:55-58`**

Raw ClickHouse errors (schema details, server version, file paths) and generated SQL returned in HTTP responses.

### 11. No Python dependency lockfile
**`pyproject.toml`**

All dependencies use floor pins (`>=`) or no pin. No `requirements.txt` or `uv.lock`.

### 12. Unpinned Docker image
**`docker-compose.yml:3`**

`clickhouse/clickhouse-server:latest` — subject to supply-chain drift.

### 13. Schema cache file world-readable
**`app/semantic/layer.py:183`**

`~/.clickspot/schema_cache.json` written with no `chmod`. Directory `~/.clickspot/` created without restrictive permissions (though `config.json` correctly gets `0600`).

---

## Low (4)

### 14. No rate limiting
No rate limiting middleware on any endpoint.

### 15. No input length limit on chat
**`frontend/src/components/chat/ChatInput.tsx:19`** — only `trim()` + empty check.

### 16. ClickHouse DB fallback to `default` superuser
**`app/db.py:18`** — falls back to `username="default"`, `password=""` if env vars unset.

### 17. No CI/CD or automated security scanning

---

## Positive Findings

- No XSS: all dynamic content via React JSX. Zero `dangerouslySetInnerHTML`.
- No data sent to LLM: results stripped from conversation history.
- No secrets in git: `.env` gitignored, never committed.
- API key config file gets `0600` permissions.
- Zero npm audit vulnerabilities.
- Claude CLI provider uses `create_subprocess_exec` (not `shell=True`).

---

## Priority Fixes

| Priority | Action | Fixes |
|----------|--------|-------|
| **P0** | Validate all column names, `agg`, and `condition` against allowlists from `TABLES` config. Remove or restructure `condition` field entirely. | #1, #2, #9 |
| **P0** | Use a **read-only ClickHouse user** for the analytics app (`GRANT SELECT ON silver.*, gold.*`). | #1, #2, #3 |
| **P0** | Harden SQL validator: block `UNION`, ClickHouse table functions (`url`, `remote`, `file`, `s3`, `merge`, `input`), validate table refs in subqueries. | #3 |
| **P1** | Restrict CORS to `http://localhost:8193`. | #5 |
| **P1** | Add auth (bearer token) on `/api/v1/settings` and optionally all endpoints. | #4, #6 |
| **P1** | Stop returning raw ClickHouse errors to client. Log server-side, return generic messages. | #10 |
| **P2** | Strip `results` from conversations before persisting to localStorage. | #7 |
| **P2** | Bind Docker ports to `127.0.0.1`, use env var for password, pin ClickHouse image. | #8, #12 |
| **P2** | Add `pip-compile` or `uv lock` for Python dependency pinning. | #11 |
| **P2** | `chmod 0600` on schema cache, `chmod 0700` on `~/.clickspot/` directory. | #13 |
