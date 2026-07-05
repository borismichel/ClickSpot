"""Inline SQL edit for saved space-dashboard widgets (CLI-166/B4).

Draft/saved parity: the transient draft card lets you view + edit each widget's
SQL; these tests cover the endpoint that brings the same affordance to a *saved*
widget — ``PUT /api/v1/spaces/{space_id}/dashboards/{dash_id}/items/{item_id}``.
The edited SQL must persist verbatim and round-trip on reload, and the endpoint
must refuse edits that cross space/dashboard/item ownership. The DB is a
throwaway SQLite file and the space lookup is faked, so no ClickHouse is touched.
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

    import app.spaces.routes_dashboards as routes

    config = DataSpaceConfig(
        id=SPACE_ID,
        name="Sales",
        grain=GrainConfig(entity="dim_deals", key="deal_id", columns=["amount", "dealstage"]),
    )
    monkeypatch.setattr(routes, "get_space", lambda sid: config if sid == SPACE_ID else None)

    from app.main import app

    return TestClient(app)


def _make_dashboard(client) -> tuple[str, str]:
    """Save a one-widget draft and return (dash_id, item_id)."""
    payload = {
        "title": "Pipeline health",
        "filters": [],
        "widgets": [
            {
                "title": "Total pipeline",
                "intent": "How much revenue is in the pipeline?",
                "sql": "SELECT count() AS n FROM gold.ds_sp1",
                "viz": "number",
                "layout": {"x": 0, "y": 0, "w": 3, "h": 2},
            }
        ],
    }
    created = client.post(f"/api/v1/spaces/{SPACE_ID}/dashboards/draft", json=payload)
    assert created.status_code == 201
    body = created.json()
    return body["id"], body["items"][0]["id"]


def test_edit_item_sql_persists(client):
    dash_id, item_id = _make_dashboard(client)
    new_sql = "SELECT sum(amount) AS total FROM gold.ds_sp1  -- edited on the saved card"

    res = client.put(
        f"/api/v1/spaces/{SPACE_ID}/dashboards/{dash_id}/items/{item_id}",
        json={"sql": new_sql},
    )
    assert res.status_code == 200
    # The endpoint echoes the whole dashboard with the edit already applied.
    assert res.json()["items"][0]["sql"] == new_sql

    # And it survives a fresh reload, byte-for-byte.
    reloaded = client.get(f"/api/v1/spaces/{SPACE_ID}/dashboards/{dash_id}").json()
    assert reloaded["items"][0]["sql"] == new_sql
    # Untouched fields are left alone.
    assert reloaded["items"][0]["viz"] == "number"
    assert reloaded["items"][0]["intent"] == "How much revenue is in the pipeline?"


def test_edit_item_viz_too(client):
    dash_id, item_id = _make_dashboard(client)
    res = client.put(
        f"/api/v1/spaces/{SPACE_ID}/dashboards/{dash_id}/items/{item_id}",
        json={"viz": "table"},
    )
    assert res.status_code == 200
    reloaded = client.get(f"/api/v1/spaces/{SPACE_ID}/dashboards/{dash_id}").json()
    assert reloaded["items"][0]["viz"] == "table"
    # SQL untouched when only viz is sent.
    assert reloaded["items"][0]["sql"] == "SELECT count() AS n FROM gold.ds_sp1"


def test_edit_empty_body_is_400(client):
    dash_id, item_id = _make_dashboard(client)
    res = client.put(
        f"/api/v1/spaces/{SPACE_ID}/dashboards/{dash_id}/items/{item_id}",
        json={},
    )
    assert res.status_code == 400


def test_edit_blank_sql_rejected(client):
    dash_id, item_id = _make_dashboard(client)
    # min_length=1 on the field ⇒ FastAPI validation error, not a persisted blank.
    res = client.put(
        f"/api/v1/spaces/{SPACE_ID}/dashboards/{dash_id}/items/{item_id}",
        json={"sql": ""},
    )
    assert res.status_code == 422


def test_edit_unknown_item_404(client):
    dash_id, _ = _make_dashboard(client)
    res = client.put(
        f"/api/v1/spaces/{SPACE_ID}/dashboards/{dash_id}/items/sitem-doesnotexist",
        json={"sql": "SELECT 1"},
    )
    assert res.status_code == 404


def test_edit_item_wrong_space_404(client):
    """An item can't be edited through a space that doesn't own its dashboard."""
    dash_id, item_id = _make_dashboard(client)
    res = client.put(
        f"/api/v1/spaces/other/dashboards/{dash_id}/items/{item_id}",
        json={"sql": "SELECT 1"},
    )
    assert res.status_code == 404
    # The original SQL is unchanged.
    reloaded = client.get(f"/api/v1/spaces/{SPACE_ID}/dashboards/{dash_id}").json()
    assert reloaded["items"][0]["sql"] == "SELECT count() AS n FROM gold.ds_sp1"
