"""Tests for the conversation REST endpoints, focused on sidebar search.

Conversations live in SQLite (separate from ClickHouse), so these run without
any analytics backend: we point ``DB_PATH`` at a tmp file, initialise the
schema, and drive the real FastAPI routes via ``TestClient``.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    import app.store as store

    monkeypatch.setattr(store, "DB_PATH", tmp_path / "app.db")
    asyncio.run(store.init_db())

    from app.main import app

    # No context manager: we already initialised the DB and don't want the
    # lifespan startup (which reaches for ClickHouse) to run.
    return TestClient(app)


def _new_conv(client: TestClient, title: str) -> str:
    res = client.post("/api/v1/conversations", json={"title": title})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _add_msg(client: TestClient, conv_id: str, role: str, content: str) -> None:
    res = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"role": role, "content": content},
    )
    assert res.status_code == 201, res.text


def test_list_returns_all_without_query(client):
    _new_conv(client, "Revenue by region")
    _new_conv(client, "Top deals this quarter")

    res = client.get("/api/v1/conversations")
    assert res.status_code == 200
    assert len(res.json()) == 2


def test_search_matches_title(client):
    _new_conv(client, "Revenue by region")
    _new_conv(client, "Top deals this quarter")

    res = client.get("/api/v1/conversations", params={"q": "revenue"})
    assert res.status_code == 200
    assert [c["title"] for c in res.json()] == ["Revenue by region"]


def test_search_matches_message_content(client):
    target = _new_conv(client, "Untitled chat")
    _add_msg(client, target, "user", "How many leads converted in Germany?")

    other = _new_conv(client, "Another chat")
    _add_msg(client, other, "user", "Show me pipeline velocity")

    res = client.get("/api/v1/conversations", params={"q": "germany"})
    assert res.status_code == 200
    # Only the conversation whose *message body* matched — title had no match.
    assert [c["id"] for c in res.json()] == [target]


def test_search_is_case_insensitive(client):
    _new_conv(client, "Revenue by region")
    res = client.get("/api/v1/conversations", params={"q": "REGION"})
    assert len(res.json()) == 1


def test_search_no_match_returns_empty(client):
    _new_conv(client, "Revenue by region")
    res = client.get("/api/v1/conversations", params={"q": "zzz-not-here"})
    assert res.json() == []


def test_search_escapes_like_wildcards(client):
    """A bare '%' must be matched literally, not act as a match-all wildcard."""
    _new_conv(client, "Revenue by region")
    res = client.get("/api/v1/conversations", params={"q": "%"})
    assert res.json() == []


# --- Idempotent message persistence (CLI-84: "history populates 4x") ---------


def _add_msg_with_id(client: TestClient, conv_id: str, msg_id: str, role: str, content: str):
    return client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"id": msg_id, "role": role, "content": content},
    )


def test_add_message_preserves_client_id(client):
    """The server must store the id the client sent, not mint its own.

    The sidebar re-saves a conversation by diffing the ids it holds against the
    stored ones; if the server rewrites the id, that diff never matches.
    """
    conv = _new_conv(client, "Untitled chat")
    res = _add_msg_with_id(client, conv, "msg-1-abc", "user", "Show revenue by owner")
    assert res.status_code in (200, 201), res.text
    assert res.json()["id"] == "msg-1-abc"

    fetched = client.get(f"/api/v1/conversations/{conv}").json()
    assert [m["id"] for m in fetched["messages"]] == ["msg-1-abc"]


def test_resaving_same_ids_does_not_duplicate(client):
    """Re-posting messages with ids that already exist is a no-op.

    Reproduces the 4x bug: the App-level save effect fires repeatedly, so the
    same client messages get POSTed more than once. With stable ids that must
    not grow the conversation.
    """
    conv = _new_conv(client, "Untitled chat")
    pair = [("msg-1-aaa", "user", "Show me activity trends by type"),
            ("msg-2-bbb", "assistant", "Here are your activity trends.")]

    # Save the pair three times over (simulating repeated save cycles).
    for _ in range(3):
        for mid, role, content in pair:
            res = _add_msg_with_id(client, conv, mid, role, content)
            assert res.status_code in (200, 201), res.text

    fetched = client.get(f"/api/v1/conversations/{conv}").json()
    assert [m["id"] for m in fetched["messages"]] == ["msg-1-aaa", "msg-2-bbb"]
    assert len(fetched["messages"]) == 2  # not 6


def test_add_message_without_id_still_works(client):
    """Backward compat: a caller that omits the id gets a server-minted one."""
    conv = _new_conv(client, "Untitled chat")
    res = client.post(
        f"/api/v1/conversations/{conv}/messages",
        json={"role": "user", "content": "no id supplied"},
    )
    assert res.status_code == 201, res.text
    assert res.json()["id"].startswith("msg-")
    fetched = client.get(f"/api/v1/conversations/{conv}").json()
    assert len(fetched["messages"]) == 1
