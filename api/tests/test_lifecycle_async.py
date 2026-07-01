"""Phase 3 — live activity field + non-blocking (background-thread) execution."""

import os
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app
from app.routers import lifecycle as lc


def _block_executor(monkeypatch):
    """Make the simulated executor park inside its run() on a gate the test releases, so the
    background worker is observably mid-execution. Returns the gate Event."""
    gate = threading.Event()
    orig = lc._sim_write
    monkeypatch.setattr(lc, "_sim_write", lambda repo_dir, tid: (gate.wait(5), orig(repo_dir, tid)))
    return gate


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


def test_running_step_reads_executing_not_planned(client, monkeypatch):
    # #2 — while a step's executor runs, the step node must read 'executing' (was stuck at
    # 'planning' so the board looked frozen).
    monkeypatch.setenv("ASV3_ASYNC_EXEC", "1")
    gate = _block_executor(monkeypatch)
    slug = "exec-status"
    tid = _make_ticket(client, slug)
    _propose(client, slug, tid)
    client.post(f"/projects/{slug}/tickets/{tid}/plan/approve", json={})
    try:
        s1, seen = f"{tid}-s1", None
        deadline = time.time() + 3
        while time.time() < deadline:
            n = next((x for x in client.get(f"/projects/{slug}/graph").json()["nodes"] if x["id"] == s1), None)
            if n and n["status"] == "executing":
                seen = "executing"
                break
            time.sleep(0.05)
        assert seen == "executing"  # the running step left PLANNED for EXECUTING
    finally:
        gate.set()
    _drain()
    n = next(x for x in client.get(f"/projects/{slug}/graph").json()["nodes"] if x["id"] == s1)
    assert n["status"] == "awaiting_review"


def test_can_propose_other_ticket_while_one_executes(client, monkeypatch):
    # #3 — the reported bug: proposing a plan for ticket B must NOT block on ticket A's run.
    monkeypatch.setenv("ASV3_ASYNC_EXEC", "1")
    gate = _block_executor(monkeypatch)
    client.post("/projects/approve", json={"slug": "conc", "title": "C", "tickets": [{"title": "A"}, {"title": "B"}]})
    tickets = [n["id"] for n in client.get("/projects/conc/graph").json()["nodes"] if n["kind"] == "ticket"]
    ta, tb = tickets[0], tickets[1]
    try:
        # ticket A starts executing; its worker parks inside the executor (holds A's exec lock)
        client.post(f"/projects/conc/tickets/{ta}/plan", json={})
        client.post(f"/projects/conc/tickets/{ta}/plan/approve", json={})
        # ... while A runs, propose for ticket B should return promptly (lock-free read/propose)
        t0 = time.time()
        r = client.post(f"/projects/conc/tickets/{tb}/plan", json={})
        elapsed = time.time() - t0
        assert (r.json().get("awaiting") or {}).get("type") == "plan_approval"
        assert elapsed < 2.0  # did NOT wait for A's (5s-parked) execution to finish
    finally:
        gate.set()
    _drain()


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
