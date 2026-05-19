"""LLM provider, OAuth, and schema-cache endpoints.

Lifted out of chat_routes.py (where they lived for historical reasons but had
no relation to /chat). All of these read/write ~/.clickspot/config.json or the
on-disk schema cache; none of them invoke the LLM.

URLs are unchanged so the frontend keeps working without coordination.
"""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException, Request

from app.llm.config import load_config, save_config, mask_key
from app.llm.oauth import save_initial_token, get_token_info, clear_tokens
from app.llm.providers import refresh_schema_prompt, ClaudeOAuthProvider, ClaudeCLIProvider
from app.mcp.pii import hubspot_app_host
from app.semantic.layer import load_cache

router = APIRouter(prefix="/api/v1")


_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def _require_localhost(request: Request) -> None:
    """Raise 403 if the request didn't come from the loopback interface.

    These endpoints store LLM API keys and OAuth tokens; they must only be
    reachable from the same host. Combined with the docker bind on 127.0.0.1
    and the CORS allowlist, this is defense-in-depth against a malicious
    process on the local network being able to read/overwrite keys.
    """
    host = request.client.host if request.client else None
    if host not in _LOOPBACK:
        raise HTTPException(
            status_code=403,
            detail="Settings endpoints accept only loopback connections; "
            "set CLICKSPOT_TRUSTED_HOSTS to override for VPN setups.",
        )


# ---------------------------------------------------------------------------
# LLM settings
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Claude OAuth
# ---------------------------------------------------------------------------


@router.post("/oauth/save")
def save_oauth_token(body: dict, request: Request):
    """Save a Claude OAuth token (from `claude setup-token`)."""
    _require_localhost(request)
    access_token = body.get("access_token", "").strip()
    if not access_token:
        raise HTTPException(status_code=400, detail="access_token is required")
    refresh_token = body.get("refresh_token", "").strip()
    save_initial_token(access_token, refresh_token)
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


# ---------------------------------------------------------------------------
# Schema cache / semantic layer
# ---------------------------------------------------------------------------


@router.post("/schema/refresh")
def refresh_schema():
    """Rebuild semantic layer from HubSpot and refresh the schema prompt."""
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
