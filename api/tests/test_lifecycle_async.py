"""Phase 3 — live activity field + non-blocking (background-thread) execution."""

import os

import pytest
from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app
from app.routers import lifecycle as lc


@pytest.fixture(scope="module", autouse=True)
def _env():
    os.environ["ASV3_AGENT_MODE"] = "simulated"
    init_db()


@pytest.fixture()
def client():
    return TestClient(app)


def _make_ticket(client, slug):
    """Create a project (objective + 1 planning ticket) and return its ticket id."""
    client.post("/projects/approve", json={"slug": slug, "title": slug, "tickets": [{"title": "T"}]})
    g = client.get(f"/projects/{slug}/graph").json()
    return next(n["id"] for n in g["nodes"] if n["kind"] == "ticket")


def _propose(client, slug, tid):
    r = client.post(f"/projects/{slug}/tickets/{tid}/plan", json={})
    assert (r.json().get("awaiting") or {}).get("type") == "plan_approval"


def _activity(client, slug, tid):
    g = client.get(f"/projects/{slug}/graph").json()
    t = next(n for n in g["nodes"] if n["id"] == tid)
    return (t.get("data") or {}).get("activity")


def _drain():
    for th in list(lc._BG_THREADS):
        th.join(timeout=5)


def test_planning_activity_cleared_after_proposal_ready(client, monkeypatch):
    # "planning" is shown only WHILE the (real-mode) propose blocks; once the proposal is
    # ready it awaits the user, so the spinner is cleared (no perpetual spinner on the ticket).
    monkeypatch.setenv("ASV3_ASYNC_EXEC", "0")
    slug = "act-plan"
    tid = _make_ticket(client, slug)
    _propose(client, slug, tid)
    assert _activity(client, slug, tid) is None


def test_activity_progresses_through_steps_sync(client, monkeypatch):
    monkeypatch.setenv("ASV3_ASYNC_EXEC", "0")
    slug = "act-sync"
    tid = _make_ticket(client, slug)
    _propose(client, slug, tid)
    client.post(f"/projects/{slug}/tickets/{tid}/plan/approve", json={})
    # step 1 ran + stopped at its review gate
    a = _activity(client, slug, tid)
    assert a["state"] == "awaiting_review" and "1/3" in a["detail"]

    client.post(f"/projects/{slug}/steps/{tid}-s1/review", json={"kind": "approve"})
    a = _activity(client, slug, tid)
    assert a["state"] == "awaiting_review" and "2/3" in a["detail"]  # advanced to step 2

    # approve the rest -> ticket done, activity reads "done"
    client.post(f"/projects/{slug}/steps/{tid}-s2/review", json={"kind": "approve"})
    client.post(f"/projects/{slug}/steps/{tid}-s3/review", json={"kind": "approve"})
    a = _activity(client, slug, tid)
    assert a["state"] == "done"


def test_approve_returns_immediately_then_executes_in_background(client, monkeypatch):
    monkeypatch.setenv("ASV3_ASYNC_EXEC", "1")
    slug = "act-async"
    tid = _make_ticket(client, slug)
    _propose(client, slug, tid)

    r = client.post(f"/projects/{slug}/tickets/{tid}/plan/approve", json={})
    assert r.status_code == 200
    # the response is the PRE-execution snapshot (the plan gate) — it did NOT block on the run
    assert (r.json().get("awaiting") or {}).get("type") == "plan_approval"

    _drain()  # let the background worker finish (deterministic; avoids polling races)
    g = client.get(f"/projects/{slug}/graph").json()
    s1 = next(n for n in g["nodes"] if n["id"] == f"{tid}-s1")
    assert s1["status"] == "awaiting_review"  # executed + gated in the background
    a = _activity(client, slug, tid)
    assert a and a["state"] == "awaiting_review"


def test_async_review_approve_advances_in_background(client, monkeypatch):
    monkeypatch.setenv("ASV3_ASYNC_EXEC", "1")
    slug = "act-async2"
    tid = _make_ticket(client, slug)
    _propose(client, slug, tid)
    client.post(f"/projects/{slug}/tickets/{tid}/plan/approve", json={})
    _drain()  # step 1 gated

    # approving step 1 returns at once; step 2 executes in the background
    client.post(f"/projects/{slug}/steps/{tid}-s1/review", json={"kind": "approve"})
    g = client.get(f"/projects/{slug}/graph").json()
    assert next(n for n in g["nodes"] if n["id"] == f"{tid}-s1")["status"] == "done"  # reviewed step done now
    _drain()
    g = client.get(f"/projects/{slug}/graph").json()
    assert next(n for n in g["nodes"] if n["id"] == f"{tid}-s2")["status"] == "awaiting_review"
