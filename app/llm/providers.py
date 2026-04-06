"""LLM provider implementations — Anthropic API, OpenAI, Claude OAuth, and Claude CLI."""

import asyncio
import json
import logging
import shutil
import time
from abc import ABC, abstractmethod
from pathlib import Path

import anthropic
import openai

from app.llm.config import load_config, get_api_key
from app.llm.oauth import get_valid_access_token, has_valid_token, OAUTH_EXTRA_HEADERS
from app.llm.response_schema import ChatSQLResponse
from app.llm.schema_prompt import build_schema_prompt
from app.semantic.layer import SemanticLayer, load_cache

log = logging.getLogger("app.llm")

# Shared schema prompt — built once, reused across requests
_schema_prompt: str | None = None
_semantic_layer: SemanticLayer | None = None


def _get_schema_prompt() -> str:
    global _schema_prompt, _semantic_layer
    if _schema_prompt is None:
        _semantic_layer = load_cache()
        _schema_prompt = build_schema_prompt(_semantic_layer)
    return _schema_prompt


def refresh_schema_prompt() -> None:
    """Force rebuild of schema prompt (after semantic layer refresh)."""
    global _schema_prompt, _semantic_layer
    _semantic_layer = load_cache()
    _schema_prompt = build_schema_prompt(_semantic_layer)


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, messages: list[dict]) -> ChatSQLResponse:
        """Generate SQL from conversation messages.

        messages: [{role: "user"|"assistant", content: str, sql: str|None}]
        The system prompt is handled internally by each provider.
        """

    def _build_llm_messages(self, messages: list[dict]) -> list[dict]:
        """Convert chat messages to LLM format (no query results, just questions + SQL)."""
        llm_msgs = []
        for msg in messages:
            if msg["role"] == "user":
                llm_msgs.append({"role": "user", "content": msg["content"]})
            elif msg["role"] == "assistant":
                # Include explanation + SQL so LLM can reference its previous work
                text = msg.get("content", "")
                sql = msg.get("sql", "")
                if sql:
                    text = f"{text}\n\nSQL: {sql}" if text else f"SQL: {sql}"
                if text:
                    llm_msgs.append({"role": "assistant", "content": text})
        return llm_msgs[-20:]  # Last 10 exchanges


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model

    async def generate(self, messages: list[dict]) -> ChatSQLResponse:
        schema = _get_schema_prompt()
        llm_messages = self._build_llm_messages(messages)

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=[
                {
                    "type": "text",
                    "text": schema,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=llm_messages,
            tools=[
                {
                    "name": "generate_sql",
                    "description": "Generate a ClickHouse SQL query for the user's question",
                    "input_schema": ChatSQLResponse.model_json_schema(),
                }
            ],
            tool_choice={"type": "tool", "name": "generate_sql"},
        )

        # Extract tool use result
        for block in response.content:
            if block.type == "tool_use":
                return ChatSQLResponse.model_validate(block.input)

        raise ValueError("No tool_use block in Anthropic response")


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o"):
        self.client = openai.AsyncOpenAI(api_key=api_key)
        self.model = model

    async def generate(self, messages: list[dict]) -> ChatSQLResponse:
        schema = _get_schema_prompt()
        llm_messages = [{"role": "system", "content": schema}]
        llm_messages.extend(self._build_llm_messages(messages))

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=llm_messages,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "sql_response",
                    "strict": True,
                    "schema": ChatSQLResponse.model_json_schema(),
                },
            },
            max_tokens=1024,
        )

        content = response.choices[0].message.content
        return ChatSQLResponse.model_validate_json(content)


class ClaudeOAuthProvider(LLMProvider):
    """Uses Claude OAuth token stored at ~/.hs2ch/claude-oauth.json.

    Token obtained via `claude setup-token`, pasted in Settings.
    Auto-refreshes when within 5 minutes of expiry.
    """

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self.model = model

    async def generate(self, messages: list[dict]) -> ChatSQLResponse:
        token = await get_valid_access_token()
        if not token:
            raise ValueError("Claude OAuth token expired or missing. Re-authenticate in Settings.")

        client = anthropic.AsyncAnthropic(
            auth_token=token,
            default_headers=OAUTH_EXTRA_HEADERS,
        )
        schema = _get_schema_prompt()
        llm_messages = self._build_llm_messages(messages)

        response = await client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=[
                {
                    "type": "text",
                    "text": schema,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=llm_messages,
            tools=[
                {
                    "name": "generate_sql",
                    "description": "Generate a ClickHouse SQL query for the user's question",
                    "input_schema": ChatSQLResponse.model_json_schema(),
                }
            ],
            tool_choice={"type": "tool", "name": "generate_sql"},
        )

        for block in response.content:
            if block.type == "tool_use":
                return ChatSQLResponse.model_validate(block.input)

        raise ValueError("No tool_use block in Anthropic response")

    @classmethod
    def is_available(cls) -> bool:
        return has_valid_token()


class ClaudeCLIProvider(LLMProvider):
    """Uses the `claude` CLI tool — no API key needed, CLI handles auth."""

    async def generate(self, messages: list[dict]) -> ChatSQLResponse:
        schema = _get_schema_prompt()
        llm_messages = self._build_llm_messages(messages)

        # Build the user prompt from conversation
        parts = []
        for msg in llm_messages:
            if msg["role"] == "user":
                parts.append(f"User: {msg['content']}")
            elif msg["role"] == "assistant":
                parts.append(f"Assistant: {msg['content']}")
        conversation = "\n".join(parts)

        prompt = f"""{schema}

{conversation}

Respond with ONLY a JSON object (no markdown, no code fences) with these exact fields:
- "sql": the ClickHouse SQL query string
- "viz": one of "number", "table", "bar", "line", "funnel"
- "title": short chart title (max 10 words)
- "explanation": one sentence explaining what the query shows"""

        proc = await asyncio.create_subprocess_exec(
            "claude", "--print", "--model", "claude-sonnet-4-6",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(prompt.encode())

        if proc.returncode != 0:
            raise ValueError(f"claude CLI failed: {stderr.decode()}")

        output = stdout.decode().strip()
        # Strip markdown code fences if present
        if output.startswith("```"):
            lines = output.split("\n")
            lines = [l for l in lines if not l.startswith("```")]
            output = "\n".join(lines).strip()

        return ChatSQLResponse.model_validate_json(output)

    @classmethod
    def is_available(cls) -> bool:
        return shutil.which("claude") is not None


def get_provider() -> LLMProvider:
    """Get the active LLM provider based on config.

    If ai_provider is explicit, use that. If "auto", try in order:
    1. Anthropic API key
    2. OpenAI API key
    3. Claude OAuth (vibespot)
    4. Claude CLI
    """
    config = load_config()
    selected = config.get("ai_provider", "auto")

    # Explicit provider selection
    if selected == "anthropic-api":
        _, api_key = get_api_key(config)
        if not api_key:
            raise ValueError("Anthropic API selected but no API key configured")
        model = config.get("anthropic_model", "claude-sonnet-4-6")
        return AnthropicProvider(api_key=api_key, model=model)

    if selected == "openai-api":
        key = config.get("openai_api_key", "")
        if not key:
            raise ValueError("OpenAI API selected but no API key configured")
        model = config.get("openai_model", "gpt-4o")
        return OpenAIProvider(api_key=key, model=model)

    if selected == "claude-oauth":
        if not ClaudeOAuthProvider.is_available():
            raise ValueError("Claude OAuth selected but token is expired or missing")
        model = config.get("anthropic_model", "claude-sonnet-4-6")
        return ClaudeOAuthProvider(model=model)

    if selected == "claude-cli":
        if not ClaudeCLIProvider.is_available():
            raise ValueError("Claude CLI selected but 'claude' not found in PATH")
        return ClaudeCLIProvider()

    # Auto-detect: try each in order
    _, api_key = get_api_key(config)
    if api_key:
        provider_name, _ = get_api_key(config)
        if provider_name == "anthropic":
            return AnthropicProvider(api_key=api_key, model=config.get("anthropic_model", "claude-sonnet-4-6"))
        if provider_name == "openai":
            return OpenAIProvider(api_key=api_key, model=config.get("openai_model", "gpt-4o"))

    if ClaudeOAuthProvider.is_available():
        log.info("Auto-detected: Claude OAuth")
        return ClaudeOAuthProvider(model=config.get("anthropic_model", "claude-sonnet-4-6"))

    if ClaudeCLIProvider.is_available():
        log.info("Auto-detected: Claude CLI")
        return ClaudeCLIProvider()

    raise ValueError(
        "No LLM provider available. Configure an API key, authenticate via OAuth, "
        "or install the claude CLI."
    )
