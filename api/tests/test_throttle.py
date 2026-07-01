"""CP1 — autonomy throttle: auto-pilot / co-pilot / per-step (resolver, lifecycle, endpoints).

Runs in the conftest default SYNC mode (ASV3_ASYNC_EXEC=0): plan/approve execute in-request,
so the auto/co-pilot run and its DB reconciliation are observable right after the call.
"""

import os

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal, init_db
from app.main import app
from app.models import Setting
from app.services import governance
from app.services.executor import ExecResult


# ───────────────────────────── unit: resolve_autonomy ─────────────────────────────
def test_default_autonomy_is_per_step(session, monkeypatch):
    monkeypatch.delenv("ASV3_THROTTLE", raising=False)
    assert governance.resolve_autonomy(session, None) == "per-step"


def test_global_env_then_setting_then_project(session, monkeypatch):
    monkeypatch.setenv("ASV3_THROTTLE", "co-pilot")
    assert governance.get_global_autonomy(session) == "co-pilot"  # env default
    governance.set_global_autonomy(session, "auto")
    assert governance.get_global_autonomy(session) == "auto"  # saved setting beats env
    from app.graph.store import seed_graph

    seed_graph(session, "pa", nodes=[{"id": "pa", "kind": "objective", "label": "o"}], edges=[])
    governance.set_project_autonomy(session, "pa", "per-step")
    assert governance.resolve_autonomy(session, "pa") == "per-step"  # project override wins


def test_invalid_level_coerced_and_clear(session):
    from app.graph.store import seed_graph

    seed_graph(session, "pb", nodes=[{"id": "pb", "kind": "objective", "label": "o"}], edges=[])
    assert governance.set_global_autonomy(session, "bogus") == "per-step"  # invalid -> default
    governance.set_project_autonomy(session, "pb", "auto")
    assert governance.get_project_autonomy(session, "pb") == "auto"
    governance.set_project_autonomy(session, "pb", None)  # clear -> inherit global
    assert governance.get_project_autonomy(session, "pb") is None
    assert governance.set_project_autonomy(session, "missing", "auto") is None  # no project


# ───────────────────────────── lifecycle behaviour ─────────────────────────────
@pytest.fixture(scope="module", autouse=True)
def _env():
    os.environ["ASV3_AGENT_MODE"] = "simulated"
    os.environ.pop("ASV3_THROTTLE", None)
    init_db()


@pytest.fixture(autouse=True)
def _clean_global_autonomy():
    def _clear():
        db = SessionLocal()
        try:
            row = db.get(Setting, "autonomy.global")
            if row is not None:
                db.delete(row)
            db.commit()
        finally:
            db.close()

    _clear()
    yield
    _clear()


@pytest.fixture()
def client():
    return TestClient(app)


def _make_planned(client, slug):
    client.post("/projects/approve", json={"slug": slug, "title": slug, "tickets": [{"title": "T"}]})
    tid = next(
        n["id"] for n in client.get(f"/projects/{slug}/graph").json()["nodes"] if n["kind"] == "ticket"
    )
    client.post(f"/projects/{slug}/tickets/{tid}/plan", json={})
    return tid


def _steps(client, slug, tid):
    g = client.get(f"/projects/{slug}/graph").json()
    nbrs = {e["to"] for e in g["edges"] if e["from"] == tid and e["kind"] == "has"}
    steps = [n for n in g["nodes"] if n["id"] in nbrs and n["kind"] == "step"]
    return sorted(steps, key=lambda n: n["id"])


def _ticket(client, slug, tid):
    return next(n for n in client.get(f"/projects/{slug}/graph").json()["nodes"] if n["id"] == tid)


def test_autopilot_runs_ticket_to_done_with_no_review(client):
    slug = "auto1"
    tid = _make_planned(client, slug)
    client.put(f"/projects/{slug}/autonomy", json={"level": "auto"})
    # approve the plan — and DO NOT call /review at all
    client.post(f"/projects/{slug}/tickets/{tid}/plan/approve", json={})
    steps = _steps(client, slug, tid)
    assert steps and all(s["status"] == "done" for s in steps)  # every step ran + auto-approved
    assert _ticket(client, slug, tid)["status"] == "done"  # ticket completed autonomously


def test_autopilot_async_drains_to_done(client, monkeypatch):
    # the documented flow: approve -> (drain the background worker) -> ticket done, no review.
    monkeypatch.setenv("ASV3_ASYNC_EXEC", "1")
    import app.routers.lifecycle as lc

    slug = "auto-async"
    tid = _make_planned(client, slug)
    client.put(f"/projects/{slug}/autonomy", json={"level": "auto"})
    client.post(f"/projects/{slug}/tickets/{tid}/plan/approve", json={})
    for th in list(lc._BG_THREADS):  # join the worker before reading (no race)
        th.join(timeout=5)
    steps = _steps(client, slug, tid)
    assert steps and all(s["status"] == "done" for s in steps)
    assert _ticket(client, slug, tid)["status"] == "done"


def test_copilot_auto_advances_then_stops_at_final_step(client):
    slug = "cop-final"
    tid = _make_planned(client, slug)
    client.put(f"/projects/{slug}/autonomy", json={"level": "co-pilot"})
    client.post(f"/projects/{slug}/tickets/{tid}/plan/approve", json={})
    steps = _steps(client, slug, tid)
    assert all(s["status"] == "done" for s in steps[:-1])  # earlier steps auto-advanced
    assert steps[-1]["status"] == "awaiting_review"  # stops at the last step for final review
    assert _ticket(client, slug, tid)["status"] != "done"  # not done until that review
    # the human approves the final step -> ticket completes
    client.post(f"/projects/{slug}/steps/{steps[-1]['id']}/review", json={"kind": "approve"})
    assert _steps(client, slug, tid)[-1]["status"] == "done"
    assert _ticket(client, slug, tid)["status"] == "done"


def test_copilot_stops_on_a_blocked_step(client, monkeypatch):
    class FailOnSecond:
        def __init__(self, write):
            self.write, self.n = write, 0

        def run(self, repo_dir: str, prompt: str) -> ExecResult:
            self.n += 1
            self.write(repo_dir)
            return ExecResult(summary="x", decision=None, ok=self.n != 2, output="")  # step 2 fails

    monkeypatch.setattr(governance, "SimulatedExecutor", FailOnSecond)
    slug = "cop-blocked"
    tid = _make_planned(client, slug)
    client.put(f"/projects/{slug}/autonomy", json={"level": "co-pilot"})
    client.post(f"/projects/{slug}/tickets/{tid}/plan/approve", json={})
    steps = _steps(client, slug, tid)
    assert steps[0]["status"] == "done"  # step 1 auto-advanced
    assert steps[1]["status"] == "blocked"  # step 2 failed -> co-pilot stops here
    assert steps[2]["status"] == "planning"  # step 3 never ran
    assert _ticket(client, slug, tid)["status"] != "done"


class _FailNth:
    """A simulated executor that returns ok=False on the n-th step (1-based), else succeeds."""

    def __init__(self, write, fail_on):
        self.write, self.fail_on, self.n = write, fail_on, 0

    def run(self, repo_dir: str, prompt: str) -> ExecResult:
        self.n += 1
        self.write(repo_dir)
        return ExecResult(summary="x", decision=None, ok=self.n != self.fail_on, output="")


def test_copilot_single_approve_of_blocked_final_step_completes_ticket(client, monkeypatch):
    # regression: a blocked FINAL step in co-pilot must complete on ONE approve (was silently
    # lost because _finalize_run skipped 'blocked' -> ticket stuck until a second approve).
    monkeypatch.setattr(governance, "SimulatedExecutor", lambda w: _FailNth(w, 3))  # last of 3 fails
    slug = "cop-blocked-final"
    tid = _make_planned(client, slug)
    client.put(f"/projects/{slug}/autonomy", json={"level": "co-pilot"})
    client.post(f"/projects/{slug}/tickets/{tid}/plan/approve", json={})
    steps = _steps(client, slug, tid)
    assert steps[-1]["status"] == "blocked"  # co-pilot stopped at the failed final step
    client.post(f"/projects/{slug}/steps/{steps[-1]['id']}/review", json={"kind": "approve"})  # ONE approve
    assert _steps(client, slug, tid)[-1]["status"] == "done"
    assert _ticket(client, slug, tid)["status"] == "done"


def test_copilot_approve_of_blocked_nonfinal_step_is_not_stranded(client, monkeypatch):
    # regression: approving a blocked NON-final step must mark it done and let the run continue.
    monkeypatch.setattr(governance, "SimulatedExecutor", lambda w: _FailNth(w, 2))  # step 2 of 3 fails
    slug = "cop-blocked-mid"
    tid = _make_planned(client, slug)
    client.put(f"/projects/{slug}/autonomy", json={"level": "co-pilot"})
    client.post(f"/projects/{slug}/tickets/{tid}/plan/approve", json={})
    steps = _steps(client, slug, tid)
    assert steps[1]["status"] == "blocked"
    client.post(f"/projects/{slug}/steps/{steps[1]['id']}/review", json={"kind": "approve"})
    steps = _steps(client, slug, tid)
    assert steps[1]["status"] == "done"  # the blocked step is completed, not stranded
    assert steps[2]["status"] == "awaiting_review"  # run continued to the final-review stop


def test_per_step_default_still_gates_every_step(client):
    slug = "perstep1"
    tid = _make_planned(client, slug)
    # no autonomy set -> default per-step: approve runs ONLY step 1, then waits at the gate
    client.post(f"/projects/{slug}/tickets/{tid}/plan/approve", json={})
    steps = _steps(client, slug, tid)
    assert steps[0]["status"] == "awaiting_review"  # gated, NOT auto-advanced
    assert steps[1]["status"] == "planning"
    assert _ticket(client, slug, tid)["status"] != "done"


# ───────────────────────────── endpoints ─────────────────────────────
def test_global_autonomy_endpoint(client):
    assert client.get("/autonomy").json()["level"] == "per-step"  # default
    assert client.put("/autonomy", json={"level": "auto"}).json() == {"level": "auto"}
    assert client.get("/autonomy").json()["level"] == "auto"


def test_project_autonomy_endpoint(client):
    slug = "authrottle"
    client.post("/projects/approve", json={"slug": slug, "title": "A", "tickets": [{"title": "T"}]})
    body = client.put(f"/projects/{slug}/autonomy", json={"level": "co-pilot"}).json()
    assert body["project"] == "co-pilot" and body["resolved"] == "co-pilot"
    assert "auto" in body["levels"]
    # clearing the override falls back to global
    cleared = client.put(f"/projects/{slug}/autonomy", json={"level": None}).json()
    assert cleared["project"] is None and cleared["resolved"] == cleared["global"]
    assert client.put("/projects/nope/autonomy", json={"level": "auto"}).status_code == 404
