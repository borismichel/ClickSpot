"""Claude OAuth token manager — stores and auto-refreshes OAuth tokens.

Users obtain a token via `claude setup-token` (Claude Code CLI) and paste it
into the settings UI. Tokens are stored in ~/.hs2ch/claude-oauth.json.

The access token (sk-ant-oat01-...) has an 8-hour lifetime and is auto-refreshed
when within 5 minutes of expiry.

Ported from vibespot's src/utils/claude-oauth.ts.
"""

import asyncio
import json
import logging
import stat
import time
from pathlib import Path

import httpx

log = logging.getLogger("app.llm.oauth")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
TOKEN_ENDPOINT = "https://console.anthropic.com/v1/oauth/token"
TOKEN_FILE = Path.home() / ".hs2ch" / "claude-oauth.json"
REFRESH_BUFFER_S = 5 * 60  # 5 minutes

OAUTH_EXTRA_HEADERS = {
    "user-agent": "claude-cli/2.1.75",
    "x-app": "cli",
    "anthropic-beta": "oauth-2025-04-20",
}

# ---------------------------------------------------------------------------
# Token persistence
# ---------------------------------------------------------------------------


def _load_tokens() -> dict | None:
    if not TOKEN_FILE.exists():
        return None
    try:
        return json.loads(TOKEN_FILE.read_text())
    except Exception:
        return None


def _save_tokens(tokens: dict) -> None:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(tokens, indent=2))
    try:
        TOKEN_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Token refresh (with concurrency guard)
# ---------------------------------------------------------------------------

_refresh_lock = asyncio.Lock()


async def _refresh_access_token(refresh_token: str) -> None:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            TOKEN_ENDPOINT,
            json={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": CLIENT_ID,
            },
        )

    if resp.status_code != 200:
        clear_tokens()
        raise ValueError("Claude OAuth session expired. Please re-authenticate in Settings.")

    data = resp.json()
    _save_tokens({
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", refresh_token),
        "expires_at": time.time() + data.get("expires_in", 28800),
    })


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def save_initial_token(access_token: str, refresh_token: str = "") -> None:
    """Save an initial OAuth token (from `claude setup-token` or manual paste)."""
    _save_tokens({
        "access_token": access_token,
        "refresh_token": refresh_token,
        # Default 8h expiry — corrected on first refresh
        "expires_at": time.time() + 28800,
    })


def has_valid_token() -> bool:
    """Check if a valid (non-expired) OAuth token exists."""
    tokens = _load_tokens()
    if not tokens:
        return False
    return tokens.get("expires_at", 0) > time.time()


async def get_valid_access_token() -> str | None:
    """Get a valid access token, auto-refreshing if needed."""
    tokens = _load_tokens()
    if not tokens:
        return None

    expires_at = tokens.get("expires_at", 0)

    # Still valid and not near expiry
    if expires_at - time.time() > REFRESH_BUFFER_S:
        return tokens["access_token"]

    # Need to refresh
    refresh_token = tokens.get("refresh_token", "")
    if refresh_token:
        async with _refresh_lock:
            # Re-check after acquiring lock (another coroutine may have refreshed)
            tokens = _load_tokens()
            if tokens and tokens.get("expires_at", 0) - time.time() > REFRESH_BUFFER_S:
                return tokens["access_token"]
            try:
                await _refresh_access_token(refresh_token)
            except Exception:
                return None
            refreshed = _load_tokens()
            return refreshed["access_token"] if refreshed else None

    # No refresh token — return current token even if expiring
    return tokens.get("access_token")


def get_token_info() -> dict | None:
    """Get token info for status display."""
    tokens = _load_tokens()
    if not tokens:
        return None
    expires_at = tokens.get("expires_at", 0)
    return {
        "authenticated": expires_at > time.time(),
        "expires_at": expires_at,
        "has_refresh_token": bool(tokens.get("refresh_token")),
    }


def clear_tokens() -> None:
    """Clear stored OAuth tokens (logout)."""
    if TOKEN_FILE.exists():
        try:
            TOKEN_FILE.unlink()
        except OSError:
            pass
