# LLM providers

Chat is the only part of ClickSpot that calls an LLM, to turn your question into SQL. The
model only sees your schema (see [The privacy model](../concepts/privacy.md)). Everything
else runs against the warehouse directly and needs no key.

Configure a provider in the Settings drawer (top-right) or in `~/.clickspot/config.json`.

## Supported providers

| Provider | Setup | Notes |
|----------|-------|-------|
| Anthropic API | Set `ANTHROPIC_API_KEY` | Best quality. Prompt caching for fast responses. |
| OpenAI API | Set `OPENAI_API_KEY` | Good fallback. |
| Claude OAuth | Paste token in Settings | For Claude Pro/Max subscribers. Auto-refreshes. |
| Claude CLI | Install the `claude` CLI | Zero-config for developers running from source. **Not** available inside the Docker images — use an API key or Claude OAuth there. |

## Setting a key

=== "Environment variable"

    ```bash
    ANTHROPIC_API_KEY=sk-... docker compose up   # or OPENAI_API_KEY=sk-...
    ```

=== "Settings drawer"

    Open the frontend, click **Settings** (top-right), and paste your key or Claude OAuth
    token. The write is restricted to loopback / trusted hosts. See
    [Trusted hosts](index.md#trusted-hosts).

!!! note "Docker and the Claude CLI"
    The Claude CLI provider is convenient when running from source, but it isn't present in
    the Docker images. In Docker, use an Anthropic/OpenAI API key or a Claude OAuth token.
