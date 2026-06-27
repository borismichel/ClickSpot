"""Tests for the optional Langfuse LLM tracing layer (app/llm/observability)."""

import importlib
import sys

import pytest


@pytest.fixture
def fresh_obs(monkeypatch):
    """Reload the module with a clean bootstrap state and no Langfuse env."""
    for var in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"):
        monkeypatch.delenv(var, raising=False)
    sys.modules.pop("app.llm.observability", None)
    mod = importlib.import_module("app.llm.observability")
    return importlib.reload(mod)


def test_disabled_when_env_missing(fresh_obs, monkeypatch):
    """No keys -> tracing off, and the langfuse package is never imported."""
    monkeypatch.setitem(sys.modules, "langfuse", None)  # would explode if imported
    assert fresh_obs.enabled() is False


def test_noop_generation_is_safe(fresh_obs):
    """The context manager + record/flush are inert no-ops when disabled."""
    with fresh_obs.generation(name="nl-to-sql", model="claude-sonnet-4-6", input={"q": 1}) as gen:
        fresh_obs.record(gen, output={"sql": "SELECT 1"}, usage={"input": 5, "output": 2})
    fresh_obs.flush()  # must not raise


def test_session_is_passthrough_when_disabled(fresh_obs):
    """session() must be a transparent no-op when tracing is off (any id, or none)."""
    with fresh_obs.session("chat-123"):
        pass
    with fresh_obs.session(None):
        pass
    # combined with a (no-op) generation, mirroring how routes use it
    with fresh_obs.session("chat-123"):
        with fresh_obs.generation(name="nl-to-sql", model="m", input={}) as gen:
            fresh_obs.record(gen, output={"sql": "SELECT 1"})


def test_anthropic_usage_mapping(fresh_obs):
    class Usage:
        input_tokens = 120
        output_tokens = 45
        cache_read_input_tokens = 900
        cache_creation_input_tokens = 0

    class Resp:
        usage = Usage()

    details = fresh_obs.anthropic_usage(Resp())
    assert details["input"] == 120
    assert details["output"] == 45
    assert details["cache_read_input_tokens"] == 900
    # zero-valued cache-creation is omitted, not sent as 0
    assert "cache_creation_input_tokens" not in details


def test_openai_usage_mapping(fresh_obs):
    class Usage:
        prompt_tokens = 300
        completion_tokens = 80

    class Resp:
        usage = Usage()

    assert fresh_obs.openai_usage(Resp()) == {"input": 300, "output": 80}


def test_usage_mapping_handles_missing_usage(fresh_obs):
    class Resp:
        usage = None

    assert fresh_obs.anthropic_usage(Resp()) == {}
    assert fresh_obs.openai_usage(Resp()) == {}
