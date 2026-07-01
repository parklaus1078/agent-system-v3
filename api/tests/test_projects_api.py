"""Phase 2 — project-level (two-level) planning: POST /projects/plan + /projects/approve."""

import os

import pytest
from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app


@pytest.fixture(scope="module", autouse=True)
def _env():
    os.environ["ASV3_AGENT_MODE"] = "simulated"
    init_db()


@pytest.fixture()
def client():
    return TestClient(app)


def test_plan_proposes_slug_title_tickets(client):
    r = client.post("/projects/plan", json={"goal": "Build a budgeting app"})
    assert r.status_code == 200
    body = r.json()
    assert body["slug"] == "build-a-budgeting-app"
    assert body["title"] == "Build a budgeting app"
    assert len(body["tickets"]) >= 2
    assert all("title" in t for t in body["tickets"])


def test_plan_persists_nothing(client):
    before = {p["projectId"] for p in client.get("/projects").json()}
    client.post("/projects/plan", json={"goal": "ephemeral idea xyz"})
    after = {p["projectId"] for p in client.get("/projects").json()}
    assert before == after  # /plan is a pure proposal — no project created


def test_approve_creates_objective_and_planning_tickets(client):
    prop = {
        "slug": "invoicing",
        "title": "Invoicing service",
        "tickets": [{"title": "API"}, {"title": "PDF render"}],
        "description": "send invoices",
    }
    r = client.post("/projects/approve", json=prop)
    assert r.status_code == 200
    out = r.json()
    assert out == {"projectId": "invoicing", "title": "Invoicing service", "tickets": 2, "created": True}

    g = client.get("/projects/invoicing/graph").json()
    objs = [n for n in g["nodes"] if n["kind"] == "objective"]
    tickets = [n for n in g["nodes"] if n["kind"] == "ticket"]
    assert [o["id"] for o in objs] == ["invoicing"]
    assert objs[0]["data"]["description"] == "send invoices"
    assert len(tickets) == 2
    assert all(t["status"] == "planning" for t in tickets)  # tickets start unplanned
    assert all(n["kind"] != "step" for n in g["nodes"])  # no steps yet (Part B decomposes)


def test_approve_is_idempotent_on_slug(client):
    prop = {"slug": "dup-proj", "title": "Dup", "tickets": [{"title": "T1"}]}
    first = client.post("/projects/approve", json=prop).json()
    second = client.post("/projects/approve", json=prop).json()
    assert first["created"] is True
    assert second["created"] is False  # no-op merge, not a duplicate
    tickets = [n for n in client.get("/projects/dup-proj/graph").json()["nodes"] if n["kind"] == "ticket"]
    assert len(tickets) == 1  # still one ticket, not doubled


def test_plan_dedupes_slug_against_existing_project(client):
    client.post("/projects/approve", json={"slug": "taken", "title": "Taken", "tickets": [{"title": "x"}]})
    # a fresh proposal whose natural slug would collide gets a unique suffix
    r = client.post("/projects/plan", json={"goal": "taken"})
    assert r.json()["slug"] == "taken-2"


def test_unicode_only_goal_yields_safe_slug(client):
    r = client.post("/projects/plan", json={"goal": "한글 목표"})
    assert r.json()["slug"]  # non-empty, url-safe (ascii fallback)
    assert all(c.isalnum() or c == "-" for c in r.json()["slug"])


def test_layout_persists_node_positions(client):
    client.post("/projects/approve", json={"slug": "layoutp", "title": "L", "tickets": [{"title": "T"}]})
    tid = next(n["id"] for n in client.get("/projects/layoutp/graph").json()["nodes"] if n["kind"] == "ticket")
    r = client.post(
        "/projects/layoutp/layout",
        json={"positions": {"layoutp": {"x": 10, "y": 20}, tid: {"x": -5.5, "y": 99}}},
    )
    assert r.json()["updated"] == 2
    # /graph echoes the saved positions on data.pos (so the map restores them on reload)
    nodes = {n["id"]: n for n in client.get("/projects/layoutp/graph").json()["nodes"]}
    assert nodes["layoutp"]["data"]["pos"] == {"x": 10, "y": 20}
    assert nodes[tid]["data"]["pos"] == {"x": -5.5, "y": 99}


def test_approve_persists_description_and_meta_edit_roundtrips(client):
    client.post(
        "/projects/approve",
        json={"slug": "descp", "title": "Desc proj", "tickets": [{"title": "T"}], "description": "원래 설명 본문"},
    )
    # description is stored at creation and surfaced by the landing list
    summary = next(p for p in client.get("/projects").json() if p["projectId"] == "descp")
    assert summary["description"] == "원래 설명 본문"

    # edit it later (view+edit inside the project)
    r = client.post("/projects/descp/meta", json={"title": "새 제목", "description": "고친 설명"})
    assert r.status_code == 200
    assert r.json() == {"projectId": "descp", "title": "새 제목", "description": "고친 설명"}
    obj = next(n for n in client.get("/projects/descp/graph").json()["nodes"] if n["kind"] == "objective")
    assert obj["label"] == "새 제목" and obj["data"]["description"] == "고친 설명"

    # blank description clears it; omitted title leaves it unchanged
    r = client.post("/projects/descp/meta", json={"description": "  "})
    assert r.json()["title"] == "새 제목" and r.json()["description"] is None


def test_meta_on_unknown_project_404s(client):
    assert client.post("/projects/nope/meta", json={"title": "x"}).status_code == 404


def test_layout_ignores_unknown_and_foreign_nodes(client):
    client.post("/projects/approve", json={"slug": "layq", "title": "L", "tickets": [{"title": "T"}]})
    r = client.post(
        "/projects/layq/layout",
        json={"positions": {"does-not-exist": {"x": 1, "y": 2}, "layoutp": {"x": 3, "y": 4}}},
    )
    assert r.json()["updated"] == 0  # unknown id + a node owned by another project are skipped
