"""LLM provider, OAuth, and schema-cache endpoints.

Lifted out of chat_routes.py (where they lived for historical reasons but had
no relation to /chat). All of these read/write ~/.clickspot/config.json or the
on-disk schema cache; none of them invoke the LLM.

URLs are unchanged so the frontend keeps working without coordination.
"""

from __future__ import annotations

import ipaddress
import os

from fastapi import APIRouter, HTTPException, Request

from app.llm.config import load_config, save_config, mask_key
from app.llm.oauth import save_initial_token, get_token_info, clear_tokens
from app.llm.providers import refresh_schema_prompt, ClaudeOAuthProvider, ClaudeCLIProvider
from app.mcp.pii import hubspot_app_host
from app.semantic.layer import load_cache

router = APIRouter(prefix="/api/v1")


# Hostnames/IPs always treated as local, regardless of configuration.
_LOOPBACK_NAMES = {"localhost"}
_LOOPBACK_NETS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
)


def _parse_trusted_hosts(raw: str) -> tuple[set[str], list]:
    """Split CLICKSPOT_TRUSTED_HOSTS into literal names and IP networks.

    Each comma-separated entry is parsed as an IP or CIDR when possible — so
    both "172.16.0.0/12" and a bare "10.0.0.5" work — and anything that isn't a
    valid address (e.g. a hostname) is kept for a literal match.
    """
    names: set[str] = set()
    nets: list = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            nets.append(ipaddress.ip_network(token, strict=False))
        except ValueError:
            names.add(token)
    return names, nets


def _host_is_trusted(host: str | None) -> bool:
    """True if `host` is loopback or listed in CLICKSPOT_TRUSTED_HOSTS."""
    if not host:
        return False
    if host in _LOOPBACK_NAMES:
        return True

    names, nets = _parse_trusted_hosts(os.environ.get("CLICKSPOT_TRUSTED_HOSTS", ""))
    if host in names:
        return True

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    # Normalise IPv4-mapped IPv6 (e.g. "::ffff:127.0.0.1") to its v4 form.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    if any(ip in net for net in _LOOPBACK_NETS):
        return True
    return any(ip in net for net in nets)


def _require_localhost(request: Request) -> None:
    """Raise 403 unless the request came from the local host (or a trusted one).

    These endpoints store LLM API keys and OAuth tokens, so they must only be
    reachable from the same host. Loopback is always allowed. Behind Docker's
    port-forwarding or a reverse proxy the peer address is the bridge gateway or
    proxy container — never 127.0.0.1 — so extra hosts (or CIDR ranges) can be
    allowed via CLICKSPOT_TRUSTED_HOSTS; the bundled demo sets this to the
    Docker bridge range so the in-app key form works out of the box. Combined
    with the default loopback port bind and the CORS allowlist, this is
    defense-in-depth against a process elsewhere on the network reading or
    overwriting keys.
    """
    host = request.client.host if request.client else None
    if not _host_is_trusted(host):
        raise HTTPException(
            status_code=403,
            detail=(
                f"Settings endpoints accept only loopback connections "
                f"(got {host or 'unknown'}); set CLICKSPOT_TRUSTED_HOSTS "
                f"(comma-separated IPs or CIDRs) to allow this host."
            ),
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
