# Security Audit — 2026-04-06 (re-verified 2026-05-17)

> **Threat model: self-hosted only.** ClickSpot is meant to run on a user's
> own machine / private network. The auth gap (#4) is **accepted as designed**
> for trusted-network deployments; the remaining fixes harden defaults so a
> new user can't accidentally expose themselves.

## Status legend

- ✅ shipped
- ◐ partially shipped or out of scope for the self-hosted threat model
- ⏳ open
- ⛔ accepted risk (documented; not fixed)


## Critical (2) — both ✅ shipped 2026-05-17

### 1. SQL Injection via `/api/v1/query` — `condition` parameter
**`app/engine/sql_builder.py:218-220`**, **`app/api/models.py:10`**

The `condition` field in `MeasureRequest` accepts arbitrary strings and is interpolated directly into SQL:
```python
agg_expr = f"countIf({condition})"
agg_expr = f"{agg}If({column}, {condition})"
```
An attacker can POST to `/api/v1/query` with `"condition": "1=1) FROM system.one; DROP TABLE silver.dim_deals--"` and it goes straight into the query.

**✅ Fix:** `condition` field removed from `MeasureRequest`; `build_conditional_measure_query` deleted. Conditional aggregates now live exclusively in `app/engine/metrics.py::COMPUTED_METRICS` (curated SQL). Covered by `tests/test_sql_builder_safety.py::TestConditionInjectionRemoved`.

### 2. SQL Injection via unvalidated column names in `/api/v1/query`
**`app/engine/sql_builder.py:130,155,176,255-278,311-324`**

`column`, `group_by`, `date_column`, and `measure_column` from user requests are f-string interpolated into SQL without validation against `TABLES` config. Table names are checked, but column names are not. The `agg` parameter is also unvalidated in `build_measure_query`.

**✅ Fix:** new `_validate_column(table, col)` + `_validate_granularity(g)` helpers in `app/engine/sql_builder.py`. Every entry point (`build_measure_query`, `build_grouped_measure_query`, `build_time_series_query`, `build_field_values_query`, `build_where_clause`) validates inputs at the top. `agg` already had `_ALLOWED_AGGS`; the check was hoisted to fire before any string interpolation. Covered by `tests/test_sql_builder_safety.py` (19 tests).

---

## High (5)

### 3. SQL Validator bypasses on chat endpoint — ✅ shipped
**`app/llm/sql_validator.py`**

The regex-based validator had multiple gaps:
- **`UNION` not blocked** — allowed appending arbitrary SELECT queries
- **ClickHouse table functions** (`url()`, `remote()`, `file()`, `s3()`) not blocked — could exfiltrate data or read local files
- **Subqueries** captured? `_TABLE_REF_PATTERN.findall()` returns all matches in the string so it actually DID catch subquery-embedded `FROM db.tbl` — verified
- **`OPTIMIZE TABLE`** and other ClickHouse-specific DDL not in the blocklist

**✅ Fix:** Added `_UNION_PATTERN`, `_OUTFILE_PATTERN`, `_TABLE_FUNCTIONS` (url, remote, file, s3, hdfs, mysql, postgresql, input, merge, cluster, ...). Extended `_FORBIDDEN` with `OPTIMIZE | KILL | EXCHANGE | FREEZE | UNFREEZE`. Covered by `tests/test_sql_validator.py` (38 tests, all attack patterns).

### 4. No authentication on any endpoint — ⛔ accepted risk
**`app/main.py:11-26`**

**Threat model:** ClickSpot is self-hosted. Each user runs their own copy on localhost / VPN. Adding bearer-token auth would block legitimate browser use of the frontend without solving the actual problem (which is the network reachability, not the lack of token). Defense-in-depth instead:
- ✅ Docker bound to 127.0.0.1 (#8)
- ✅ CORS locked to localhost (#5)
- ✅ Settings + OAuth endpoints additionally guarded by `_require_localhost(request)` to refuse non-loopback connections even if the backend is exposed
- 📝 Documented in README "Setup" section: ClickSpot must not be exposed to the public internet without putting auth in front of it (reverse proxy with basic auth / oauth2-proxy / etc.)

### 5. Wildcard CORS — ✅ shipped
**`app/main.py`**

`allow_origins=["*"]` is now an allowlist defaulting to `http://localhost:8193 / :8192` and `http://127.0.0.1:*` (the frontend and backend dev hosts). Override via `CLICKSPOT_CORS_ORIGINS` env (comma-separated) for VPN / reverse-proxy setups. Methods narrowed from `*` to `GET POST PUT DELETE`; headers narrowed to `content-type authorization`.

### 6. API key exposure via settings endpoints — ✅ shipped
**`app/api/chat_routes.py`**

Settings GET continues to return masked keys (first 4 + last 4). Settings PUT, OAuth save, and OAuth logout now require a loopback client IP via `_require_localhost(request)` — non-loopback connections get 403 even if CORS is opened up. Combined with the docker-bound-to-localhost change, three layers protect the API keys.

### 7. Sensitive business data in localStorage indefinitely — ✅ shipped
**`frontend/src/hooks/useConversations.ts`**

Resolved as part of the server-side persistence migration (see also `useDashboards.ts`, `useObjectRepo.ts`). The localStorage path is now a *one-time migration source*: on first load it POSTs any existing local state to `/api/v1/conversations/import` and then calls `localStorage.removeItem(LS_KEY)`. New chat results never touch localStorage; they go straight to the SQLite-backed server store at `~/.clickspot/app.db`.

---

## Medium (6)

### 8. ClickHouse ports bound to 0.0.0.0 — ◐ partial
**`docker-compose.yml`**

Ports now bound to `127.0.0.1:8124:8123` and `127.0.0.1:9001:9000` — ClickHouse unreachable from outside the host. Credentials remain `hs2ch/hs2ch` per the deliberate "leave docker alone" decision documented in the project-rename pass; changing them would require destroying the docker volume. `CLICKHOUSE_DEFAULT_ACCESS_MANAGEMENT: 1` still grants superuser to the `hs2ch` user — accepted because the user is only reachable from loopback now.

### 9. Selection column names not validated — ✅ shipped
**`app/engine/sql_builder.py::build_where_clause`**

Selection dict keys now go through `_validate_column(table, col)` before being interpolated. Same fix as #2; covered by `tests/test_sql_builder_safety.py::TestWhereClauseRejects`.

### 10. ClickHouse error messages leaked to client — ✅ shipped
**`app/api/chat_routes.py`, `app/api/data_routes.py`**

New `_safe_clickhouse_error(exc)` helper extracts only the ClickHouse `Code: N` and error-class enum (e.g. `UNKNOWN_TABLE`, `SYNTAX_ERROR`) and returns those to the client. Full error + SQL are logged server-side. Applied to both the chat path and the dashboard `/api/v1/sql` path. The LLM-provider error path also stopped echoing the raw exception.

### 11. No Python dependency lockfile — ⏳ deferred
**`pyproject.toml`**

All dependencies still use floor pins (`>=`). No `requirements.txt` or `uv.lock`. Deferred — orthogonal to runtime security; can be added when we adopt a CI pipeline.

### 12. Unpinned Docker image — ✅ shipped earlier
**`docker-compose.yml`**

Pinned to `clickhouse/clickhouse-server:26.2.5.45` during the ClickHouse perf-hardening pass.

### 13. Schema cache file world-readable — ✅ shipped
**`app/semantic/layer.py::save_cache`**

`os.chmod(CACHE_DIR, 0o700)` + `os.chmod(CACHE_FILE, 0o600)` applied on every save. `app/customer/config.py::save()` already applied the same on `customer.json`; this brings the schema cache in line.

---

## Low (4)

### 14. No rate limiting — ⏳ deferred
No rate limiting middleware on any endpoint. Defer until there's a reverse-proxy / hosted scenario where rate limiting is meaningful — on localhost-only it's not a real attack vector.

### 15. No input length limit on chat — ✅ shipped
**`frontend/src/components/chat/ChatInput.tsx`, `app/api/chat_models.py`**

Frontend: `MAX_INPUT_LENGTH = 4000` enforced via `maxLength` + send-button disable + character counter at 80%. Server: `ChatMessage.content` and `ChatRequest.message` declared `Field(max_length=4000)` — Pydantic rejects with 422 before any LLM call.

### 16. ClickHouse DB fallback to `default` superuser — ✅ shipped
**`app/db.py`**

`get_client()` now fails fast with a clear error if `CLICKHOUSE_USER` or `CLICKHOUSE_PASSWORD` are unset. The previous fallback silently used the `default` superuser against fresh CH installs.

### 17. No CI/CD or automated security scanning — ⏳ deferred
Out of scope; would pair naturally with the dependency-lockfile work (#11).

---

## Positive Findings

- No XSS: all dynamic content via React JSX. Zero `dangerouslySetInnerHTML`.
- No data sent to LLM: results stripped from conversation history.
- No secrets in git: `.env` gitignored, never committed.
- API key config file gets `0600` permissions.
- Zero npm audit vulnerabilities.
- Claude CLI provider uses `create_subprocess_exec` (not `shell=True`).

---

## Status summary (post 2026-05-17 hardening pass)

| | Count |
|---|---|
| ✅ Shipped | 11 (#1, #2, #3, #5, #6, #7, #8 partial, #9, #10, #12, #13, #15, #16) |
| ⛔ Accepted risk (self-hosted threat model) | 1 (#4) |
| ⏳ Deferred (orthogonal / CI-track) | 3 (#11, #14, #17) |

## Threat model + deployment guidance

ClickSpot is **self-hosted only**. Each user runs their own copy on localhost or a private network. The defaults reflect this:

- **ClickHouse** bound to `127.0.0.1` only (docker-compose).
- **FastAPI backend** CORS allowlists `localhost:8193` / `127.0.0.1:8193`. Override via `CLICKSPOT_CORS_ORIGINS` only for VPN / reverse-proxy setups where you control the origin list.
- **Settings + OAuth + schema-refresh endpoints** additionally refuse non-loopback connections.
- **LLM API keys** stored in `~/.clickspot/config.json` at `0600`; SQLite store + semantic cache + OAuth token + spaces at the same perms; directory at `0700`.
- **No authentication** is intentional — auth in a single-user, localhost-only deployment adds friction without solving any real attack. **If you put ClickSpot on the public internet**, sit it behind a reverse proxy that adds authentication (basic auth, oauth2-proxy, Cloudflare Access, etc.) AND keep the loopback-only guards on; they're defense in depth, not a substitute for proper auth.

The Critical + High items that are accepted-risk under this model become **blockers** the moment ClickSpot is deployed multi-tenant or internet-facing. Re-open this audit at that point.
