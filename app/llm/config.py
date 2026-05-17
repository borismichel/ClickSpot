"""LLM provider configuration — loads from ~/.clickspot/config.json and env vars."""

import json
import os
import stat
from pathlib import Path

CONFIG_DIR = Path.home() / ".clickspot"
CONFIG_FILE = CONFIG_DIR / "config.json"

_DEFAULTS = {
    "ai_provider": "auto",
    "anthropic_api_key": "",
    "openai_api_key": "",
    "anthropic_model": "claude-sonnet-4-6",
    "openai_model": "gpt-4o",
}


def load_config() -> dict:
    """Load config from file, falling back to env vars."""
    config = dict(_DEFAULTS)

    # File config
    if CONFIG_FILE.exists():
        try:
            file_config = json.loads(CONFIG_FILE.read_text())
            config.update({k: v for k, v in file_config.items() if v})
        except Exception:
            pass

    # Env var overrides
    env_map = {
        "ANTHROPIC_API_KEY": "anthropic_api_key",
        "OPENAI_API_KEY": "openai_api_key",
    }
    for env_key, config_key in env_map.items():
        val = os.environ.get(env_key, "")
        if val:
            config[config_key] = val

    return config


def save_config(config: dict) -> None:
    """Save config to file with restricted permissions."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2))
    try:
        CONFIG_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600
    except OSError:
        pass


def get_api_key(config: dict | None = None) -> tuple[str, str]:
    """Return (provider, api_key) for the active provider.

    Returns the first available key found.
    """
    if config is None:
        config = load_config()

    provider = config.get("ai_provider", "anthropic-api")

    if provider == "anthropic-api" and config.get("anthropic_api_key"):
        return "anthropic", config["anthropic_api_key"]
    if provider == "openai-api" and config.get("openai_api_key"):
        return "openai", config["openai_api_key"]

    # Auto-detect fallback
    if config.get("anthropic_api_key"):
        return "anthropic", config["anthropic_api_key"]
    if config.get("openai_api_key"):
        return "openai", config["openai_api_key"]

    return "none", ""


def mask_key(key: str) -> str:
    """Mask an API key for display."""
    if len(key) <= 8:
        return "***"
    return key[:4] + "..." + key[-4:]
