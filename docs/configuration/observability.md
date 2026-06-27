# LLM observability (Langfuse)

ClickSpot can send a trace of every NL→SQL call to [Langfuse](https://langfuse.com) so you
can see the exact prompt, the generated SQL, token usage, cost, and latency — and iterate on
prompts with real data behind you. It is **off by default** and entirely optional.

When it's off, nothing changes: the Langfuse SDK isn't even imported, and the chat path runs
with no added latency.

## What gets traced

Every call through the chat and dashboard generators (all four providers — Anthropic API,
OpenAI, Claude OAuth, Claude CLI) is recorded as a Langfuse *generation* with:

- the **model** used (so cost is computed automatically),
- the **input** — the schema-only system prompt plus the conversation,
- the **output** — the generated SQL / dashboard spec,
- **token usage** (including Anthropic prompt-cache reads), and
- **latency**.

!!! note "Privacy holds"
    ClickSpot only ever sends your **schema** and your **question** to the LLM — never CRM row
    data, which never reaches the model. So traces never contain customer data either. Point
    `LANGFUSE_HOST` at a self-hosted Langfuse to keep the whole loop on your own
    infrastructure. See [The privacy model](../concepts/privacy.md).

## Enable it

1. Install the optional dependency:

    ```bash
    pip install 'clickspot[observability]'
    ```

2. Set your Langfuse keys (from Langfuse → Settings → API Keys) before starting the backend:

    ```bash
    export LANGFUSE_PUBLIC_KEY=pk-lf-...
    export LANGFUSE_SECRET_KEY=sk-lf-...
    export LANGFUSE_HOST=https://cloud.langfuse.com   # or your self-hosted URL
    ```

Both keys must be present for tracing to activate. If the keys are set but the package isn't
installed, ClickSpot logs a one-line warning and keeps running untraced.

Open Langfuse and you'll see traces named `nl-to-sql` (chat) and one per dashboard tool call
as queries come in.

## Good to know

- **Self-hosted, fully offline** — Langfuse runs in Docker; nothing leaves your network.
- **Best-effort** — if Langfuse is unreachable or misconfigured, tracing is skipped and query
  generation is never affected.
- **Not yet wired:** `session_id`/`user_id` on traces and Langfuse prompt management. The
  current scope is observability + cost/latency/prompt visibility for prompt engineering.
