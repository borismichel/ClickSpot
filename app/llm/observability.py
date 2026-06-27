"""Optional Langfuse tracing for ClickSpot's LLM calls.

Tracing activates only when **both** ``LANGFUSE_PUBLIC_KEY`` and
``LANGFUSE_SECRET_KEY`` are set *and* the ``langfuse`` package is installed
(``pip install 'clickspot[observability]'``). When either is missing, every
helper here is a no-op: the NL->SQL path runs unchanged, with no extra latency
and no import of the Langfuse/OpenTelemetry stack.

Privacy. ClickSpot only ever sends the schema-only system prompt, the user's
natural-language question, and the generated SQL to the LLM -- never CRM row
data, which never reaches the model. Langfuse traces therefore never contain
customer data either. Point ``LANGFUSE_HOST`` at a self-hosted Langfuse to keep
the whole loop on your own infrastructure.

Failure isolation. Tracing is strictly best-effort: any error while starting a
span, recording a result, or flushing is logged and swallowed. A broken or
misconfigured Langfuse never breaks query generation.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator

log = logging.getLogger("app.llm.observability")

_client: Any = None
_bootstrapped = False


def _bootstrap() -> None:
    """Initialise the Langfuse client once, lazily, from the environment."""
    global _client, _bootstrapped
    if _bootstrapped:
        return
    _bootstrapped = True

    if not (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY")):
        return  # not configured -> stay a no-op, never import langfuse

    try:
        from langfuse import get_client
    except ImportError:
        log.warning(
            "LANGFUSE_PUBLIC_KEY/SECRET_KEY are set but the 'langfuse' package is "
            "not installed. LLM tracing is disabled. Install it with "
            "`pip install 'clickspot[observability]'`."
        )
        return

    try:
        client = get_client()
        _client = client
        log.info(
            "Langfuse LLM tracing enabled (host=%s).",
            os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        )
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("Langfuse init failed; LLM tracing disabled: %s", exc)


def enabled() -> bool:
    """True when traces will actually be emitted."""
    _bootstrap()
    return _client is not None


class _NoopGeneration:
    """Stand-in returned when tracing is disabled, so call sites stay uniform."""

    def update(self, *args: Any, **kwargs: Any) -> None:
        pass


@contextmanager
def generation(name: str, model: str, input: Any) -> Iterator[Any]:
    """Wrap an LLM call in a Langfuse *generation* span.

    Yields the live generation (call :func:`record` on it) or a no-op stand-in.
    Span *creation* errors fall back to the no-op; exceptions raised inside the
    ``with`` body (i.e. the LLM call itself) propagate unchanged so callers keep
    their own error handling.
    """
    if not enabled():
        yield _NoopGeneration()
        return

    try:
        cm = _client.start_as_current_observation(
            as_type="generation", name=name, model=model, input=input
        )
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("Langfuse span '%s' could not start; not traced: %s", name, exc)
        yield _NoopGeneration()
        return

    with cm as gen:
        yield gen


def record(gen: Any, *, output: Any = None, usage: dict | None = None) -> None:
    """Attach output + token usage to a generation, swallowing any tracing error."""
    try:
        gen.update(output=output, usage_details=usage or None)
    except Exception as exc:  # pragma: no cover - defensive
        log.debug("Langfuse generation update failed (ignored): %s", exc)


def anthropic_usage(response: Any) -> dict:
    """Map an Anthropic Messages response's usage into Langfuse usage_details."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    details = {
        "input": getattr(usage, "input_tokens", 0) or 0,
        "output": getattr(usage, "output_tokens", 0) or 0,
    }
    for attr in ("cache_read_input_tokens", "cache_creation_input_tokens"):
        value = getattr(usage, attr, None)
        if value:
            details[attr] = value
    return details


def openai_usage(response: Any) -> dict:
    """Map an OpenAI chat-completion response's usage into Langfuse usage_details."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    return {
        "input": getattr(usage, "prompt_tokens", 0) or 0,
        "output": getattr(usage, "completion_tokens", 0) or 0,
    }


def flush() -> None:
    """Flush buffered traces (call on server shutdown). No-op when disabled."""
    if _client is None:
        return
    try:
        _client.flush()
    except Exception as exc:  # pragma: no cover - defensive
        log.debug("Langfuse flush failed (ignored): %s", exc)
