"""Chat API routes — natural language → SQL → ClickHouse results."""

import logging
import time

from fastapi import APIRouter, HTTPException

from app.api.chat_models import ChatRequest, ChatResponse, ContextKPIResult
from app.db import query_rows, query_value
from app.llm.config import load_config, save_config, get_api_key, mask_key
from app.llm.providers import get_provider, refresh_schema_prompt, ClaudeOAuthProvider, ClaudeCLIProvider
from app.llm.sql_validator import validate_sql, ensure_limit
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
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")
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
        rows = query_rows(sql)
    except Exception as e:
        log.error(f"ClickHouse query failed: {e}\nSQL: {sql}")
        raise HTTPException(
            status_code=422,
            detail=f"ClickHouse error: {e}\n\nSQL: {sql}",
        )
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
            val = query_value(kpi_sql)
            context_results.append(ContextKPIResult(
                label=kpi.label,
                value=val,
                sql=kpi_sql,
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
    }


@router.put("/settings")
def update_settings(updates: dict):
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
