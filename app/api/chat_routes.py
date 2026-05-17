"""Chat API routes — natural language → SQL → ClickHouse results."""

import logging
import os
import re
import time

from fastapi import APIRouter, HTTPException, Request


_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def _require_localhost(request: Request) -> None:
    """Raise 403 if the request didn't come from the loopback interface.

    ClickSpot is self-hosted. The settings endpoint stores LLM API keys; it
    must only be reachable from the same host. Combined with the docker bind
    on 127.0.0.1 and the CORS allowlist, this is defense-in-depth against
    a malicious process on the local network being able to read/overwrite keys.
    """
    host = request.client.host if request.client else None
    if host not in _LOOPBACK:
        raise HTTPException(
            status_code=403,
            detail="Settings endpoints accept only loopback connections; "
            "set CLICKSPOT_TRUSTED_HOSTS to override for VPN setups.",
        )


# ClickHouse error messages look like:
#   "Code: 60. DB::Exception: Received from localhost:9000. DB::Exception: Table
#    silver.dim_foo doesn't exist. (UNKNOWN_TABLE) (version 26.2.5.45 ...)"
# We surface the user-meaningful error class (UNKNOWN_TABLE) and Code: N, but
# strip the full message (which can leak server version, file paths, internal
# table names) before returning to the client.
_CH_ERROR_CODE_RE = re.compile(r"Code:\s*(\d+)")
_CH_ERROR_CLASS_RE = re.compile(r"\(([A-Z_][A-Z0-9_]*)\)")


def _safe_clickhouse_error(exc: Exception) -> str:
    """Convert a clickhouse_connect exception into a short client-safe message.

    Falls back to a generic message if nothing useful can be extracted —
    full details remain in the server-side log.
    """
    msg = str(exc)
    code = _CH_ERROR_CODE_RE.search(msg)
    klass = _CH_ERROR_CLASS_RE.search(msg)
    if code and klass:
        return f"ClickHouse error {code.group(1)}: {klass.group(1)}"
    if klass:
        return f"ClickHouse error: {klass.group(1)}"
    return "Query execution failed"

from app.api.chat_models import ChatRequest, ChatResponse, ContextKPIResult
from app.db import async_query_rows, async_query_value
from app.llm.config import load_config, save_config, get_api_key, mask_key
from app.llm.oauth import save_initial_token, get_token_info, clear_tokens, has_valid_token
from app.llm.providers import get_provider, refresh_schema_prompt, ClaudeOAuthProvider, ClaudeCLIProvider
from app.llm.sql_validator import validate_sql, ensure_limit
from app.mcp.pii import hubspot_app_host
from app.semantic.layer import load_cache

router = APIRouter(prefix="/api/v1")
log = logging.getLogger("app.chat")


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    # 1. Get LLM provider
    try:
        provider = get_provider()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # 2. Build messages for LLM
    messages = [m.model_dump() for m in req.history]
    messages.append({"role": "user", "content": req.message})

    # 3. Call LLM
    t0 = time.time()
    try:
        llm_response = await provider.generate(messages)
    except Exception as e:
        log.error(f"LLM call failed: {e}")
        raise HTTPException(status_code=502, detail="LLM provider error; see server log")
    llm_ms = int((time.time() - t0) * 1000)

    sql = llm_response.sql.strip().rstrip(";")

    # 4. Validate SQL
    is_valid, error = validate_sql(sql)
    if not is_valid:
        raise HTTPException(status_code=422, detail=f"SQL validation failed: {error}")

    sql = ensure_limit(sql)

    # 5. Execute on ClickHouse
    t1 = time.time()
    try:
        rows = await async_query_rows(sql)
    except Exception as e:
        # Full error + SQL go to the server log; client gets a sanitized one-liner
        # so we don't leak server version / table internals / file paths.
        log.error(f"ClickHouse query failed: {e}\nSQL: {sql}")
        raise HTTPException(status_code=422, detail=_safe_clickhouse_error(e))
    query_ms = int((time.time() - t1) * 1000)

    columns = list(rows[0].keys()) if rows else []

    # 6. Execute context KPIs (non-blocking, errors silently skipped)
    context_results = []
    for kpi in llm_response.context:
        kpi_sql = kpi.sql.strip().rstrip(";")
        is_valid_kpi, _ = validate_sql(kpi_sql)
        if not is_valid_kpi:
            continue
        kpi_sql = ensure_limit(kpi_sql, max_limit=1)
        try:
            val = await async_query_value(kpi_sql)
            if val is None or val == "\\N":
                val = None

            # Execute previous period SQL if provided
            prev_val = None
            delta_pct = None
            if kpi.previous_sql:
                prev_sql = kpi.previous_sql.strip().rstrip(";")
                is_valid_prev, _ = validate_sql(prev_sql)
                if is_valid_prev:
                    prev_sql = ensure_limit(prev_sql, max_limit=1)
                    try:
                        prev_val = await async_query_value(prev_sql)
                        if prev_val is None or prev_val == "\\N":
                            prev_val = None
                    except Exception as e:
                        log.warning(f"Previous KPI failed ({kpi.label}): {e}")

                # Compute delta percent
                if val is not None and prev_val is not None:
                    try:
                        cur = float(val)
                        prev = float(prev_val)
                        if prev != 0:
                            delta_pct = round((cur - prev) / abs(prev) * 100, 1)
                        elif cur != 0:
                            delta_pct = 100.0
                    except (ValueError, TypeError):
                        pass

            context_results.append(ContextKPIResult(
                label=kpi.label,
                value=val,
                sql=kpi_sql,
                previous_sql=kpi.previous_sql.strip().rstrip(";") if kpi.previous_sql else None,
                previous_value=prev_val,
                delta_percent=delta_pct,
            ))
        except Exception as e:
            log.warning(f"Context KPI failed ({kpi.label}): {e}")

    return ChatResponse(
        explanation=llm_response.explanation,
        sql=sql,
        results=rows,
        columns=columns,
        row_count=len(rows),
        viz=llm_response.viz,
        title=llm_response.title,
        llm_ms=llm_ms,
        query_ms=query_ms,
        context=context_results,
    )


@router.get("/settings")
def get_settings():
    config = load_config()
    return {
        "ai_provider": config.get("ai_provider", "auto"),
        "anthropic_api_key": mask_key(config.get("anthropic_api_key", "")),
        "openai_api_key": mask_key(config.get("openai_api_key", "")),
        "anthropic_model": config.get("anthropic_model", "claude-sonnet-4-6"),
        "openai_model": config.get("openai_model", "gpt-4o"),
        "hubspot_hub_id": os.environ.get("HUBSPOT_HUB_ID", ""),
        "hubspot_app_host": hubspot_app_host(),
    }


@router.put("/settings")
def update_settings(updates: dict, request: Request):
    _require_localhost(request)
    config = load_config()
    for key in ("ai_provider", "anthropic_api_key", "openai_api_key", "anthropic_model", "openai_model"):
        val = updates.get(key, "")
        if val and not val.startswith("***"):
            config[key] = val
    save_config(config)
    return {"status": "ok"}


@router.get("/settings/providers")
def available_providers():
    config = load_config()
    return {
        "providers": [
            {
                "id": "auto",
                "name": "Auto-detect",
                "ready": True,
                "description": "Automatically use the best available provider",
            },
            {
                "id": "anthropic-api",
                "name": "Anthropic API",
                "ready": bool(config.get("anthropic_api_key")),
                "description": "Direct Anthropic API (fastest, supports prompt caching)",
            },
            {
                "id": "openai-api",
                "name": "OpenAI API",
                "ready": bool(config.get("openai_api_key")),
                "description": "OpenAI API (GPT-4o)",
            },
            {
                "id": "claude-oauth",
                "name": "Claude OAuth",
                "ready": ClaudeOAuthProvider.is_available(),
                "description": "Claude OAuth token (via vibespot authentication)",
            },
            {
                "id": "claude-cli",
                "name": "Claude CLI",
                "ready": ClaudeCLIProvider.is_available(),
                "description": "Uses local 'claude' CLI tool (no API key needed)",
            },
        ]
    }


@router.post("/oauth/save")
def save_oauth_token(body: dict, request: Request):
    """Save a Claude OAuth token (from `claude setup-token`)."""
    _require_localhost(request)
    access_token = body.get("access_token", "").strip()
    if not access_token:
        raise HTTPException(status_code=400, detail="access_token is required")
    refresh_token = body.get("refresh_token", "").strip()
    save_initial_token(access_token, refresh_token)
    # Auto-select claude-oauth as provider
    config = load_config()
    if config.get("ai_provider") != "claude-oauth":
        config["ai_provider"] = "claude-oauth"
        save_config(config)
    return {"ok": True}


@router.get("/oauth/status")
def oauth_status():
    """Return current OAuth authentication status."""
    info = get_token_info()
    if not info:
        return {"authenticated": False, "expires_at": None}
    return info


@router.post("/oauth/logout")
def oauth_logout(request: Request):
    """Clear stored OAuth tokens and reset provider if needed."""
    _require_localhost(request)
    clear_tokens()
    config = load_config()
    if config.get("ai_provider") == "claude-oauth":
        config["ai_provider"] = "auto"
        save_config(config)
    return {"ok": True}


@router.post("/schema/refresh")
def refresh_schema():
    """Rebuild semantic layer from HubSpot and refresh the schema prompt."""
    # For now, just refresh from cache. Full HubSpot fetch requires dagster resource.
    refresh_schema_prompt()
    layer = load_cache()
    table_count = len(layer.tables) if layer else 0
    return {"status": "ok", "tables": table_count}


@router.get("/schema/semantic")
def get_semantic():
    """Return current semantic layer for debugging."""
    layer = load_cache()
    if not layer:
        return {"tables": {}, "associations": [], "built_at": 0}
    return layer.to_dict()
