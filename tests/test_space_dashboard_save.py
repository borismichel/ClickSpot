"""Save → reload fidelity for the One Shot Dashboard (CLI-130).

The transient OSD draft is promoted to a saved space dashboard via
``POST /api/v1/spaces/{space_id}/dashboards/draft``. These tests prove the saved
snapshot round-trips faithfully on the subsequent GET: widget order, each
widget's (generated or hand-edited) SQL and viz type, the grid layout, and the
dashboard-level filters. The DB is a throwaway SQLite file and the space lookup
is faked, so no ClickHouse / LLM is touched.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.spaces.config import DataSpaceConfig, GrainConfig

SPACE_ID = "sp1"


@pytest.fixture
def client(tmp_path, monkeypatch):
    import app.store as store

    monkeypatch.setattr(store, "DB_PATH", tmp_path / "app.db")
    asyncio.run(store.init_db())

    # Bare TestClient(app) skips the lifespan startup (which would reach
    # ClickHouse); the create path only needs get_space to resolve.
    import app.spaces.routes_dashboards as routes

    config = DataSpaceConfig(
        id=SPACE_ID,
        name="Sales",
        grain=GrainConfig(entity="dim_deals", key="deal_id", columns=["amount", "dealstage"]),
    )
    monkeypatch.setattr(routes, "get_space", lambda sid: config if sid == SPACE_ID else None)

    from app.main import app

    return TestClient(app)


def _draft_payload() -> dict:
    # A user-edited number SQL (note the inline comment) + a generated bar chart,
    # each with its own non-default tile layout, plus an applied dashboard filter.
    return {
        "title": "Pipeline health",
        "source_description": "How healthy is our sales pipeline right now?",
        "filters": [{"column": "dealstage", "operator": "in", "values": ["closedwon"]}],
        "widgets": [
            {
                "title": "Total pipeline",
                "intent": "How much revenue is in the pipeline?",
                "sql": "SELECT count() AS n FROM gold.ds_sp1  -- hand-edited",
                "viz": "number",
                "layout": {"x": 0, "y": 0, "w": 3, "h": 2},
            },
            {
                "title": "Value by stage",
                "intent": "Where does deal value concentrate across stages?",
                "sql": "SELECT dealstage, sum(amount) AS v FROM gold.ds_sp1 GROUP BY dealstage",
                "viz": "bar",
                "layout": {"x": 3, "y": 0, "w": 6, "h": 4},
            },
        ],
    }


def test_save_draft_roundtrips_sql_viz_layout_and_filters(client):
    payload = _draft_payload()

    created = client.post(f"/api/v1/spaces/{SPACE_ID}/dashboards/draft", json=payload)
    assert created.status_code == 201
    dash_id = created.json()["id"]

    reloaded = client.get(f"/api/v1/spaces/{SPACE_ID}/dashboards/{dash_id}")
    assert reloaded.status_code == 200
    data = reloaded.json()

    assert data["title"] == payload["title"]
    assert data["filters"] == payload["filters"]

    items = data["items"]
    assert len(items) == len(payload["widgets"])
    # Order is preserved (sort_order follows the draft's widget order).
    assert [i["title"] for i in items] == [w["title"] for w in payload["widgets"]]

    for sent, got in zip(payload["widgets"], items):
        # SQL must be byte-for-byte identical — generated and user-edited alike.
        assert got["sql"] == sent["sql"]
        assert got["viz"] == sent["viz"]
        assert got["layout"] == sent["layout"]

    # The create response and the reload return the same shape.
    assert created.json()["items"] == items


def test_save_draft_preserves_provenance(client):
    """A5: the originating prompt and each widget's intent survive save→reload."""
    payload = _draft_payload()

    created = client.post(f"/api/v1/spaces/{SPACE_ID}/dashboards/draft", json=payload)
    assert created.status_code == 201
    dash_id = created.json()["id"]

    data = client.get(f"/api/v1/spaces/{SPACE_ID}/dashboards/{dash_id}").json()

    assert data["source_description"] == payload["source_description"]
    assert [i["intent"] for i in data["items"]] == [w["intent"] for w in payload["widgets"]]


def test_save_draft_rejects_error_widgets_then_allows_override(client):
    """A5: a broken widget is not silently saved — it's rejected until opted in."""
    payload = _draft_payload()
    payload["widgets"][1]["status"] = "error"

    rejected = client.post(f"/api/v1/spaces/{SPACE_ID}/dashboards/draft", json=payload)
    assert rejected.status_code == 409
    detail = rejected.json()["detail"]
    assert detail["error"] == "error_widgets"
    assert detail["widgets"] == ["Value by stage"]

    # Explicit opt-in saves the whole board, broken widget included.
    payload["allow_error_widgets"] = True
    saved = client.post(f"/api/v1/spaces/{SPACE_ID}/dashboards/draft", json=payload)
    assert saved.status_code == 201
    assert len(saved.json()["items"]) == 2


def test_save_draft_unknown_space_404(client):
    res = client.post("/api/v1/spaces/nope/dashboards/draft", json=_draft_payload())
    assert res.status_code == 404


def test_save_draft_allows_empty_widgets(client):
    res = client.post(
        f"/api/v1/spaces/{SPACE_ID}/dashboards/draft",
        json={"title": "Empty start", "filters": [], "widgets": []},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["items"] == []
    assert body["title"] == "Empty start"
