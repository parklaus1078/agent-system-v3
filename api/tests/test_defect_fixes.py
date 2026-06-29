"""Regression tests for the user-flow E2E defect fixes (docs/defects.md)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal, init_db
from app.graph.store import seed_graph
from app.models import Node
from app.services.embeddings import DeterministicEmbeddings
from app.services.memory import MemoryStore

PID = "pfix"


def test_d02_korean_text_embeds_nonzero_and_search_does_not_500():
    """D-02: a Korean decision must embed to a non-zero vector so retrieve/search
    doesn't raise NaN. Previously [a-z0-9]+ tokenization gave an all-zero vector → 500."""
    e = DeterministicEmbeddings()
    v = e.embed_query("게이팅은 플래그로 (티어 분기 금지)")
    assert any(x != 0.0 for x in v), "Korean text must not embed to an all-zero vector"

    m = MemoryStore(e)
    m.index_text("게이팅은 플래그로 (티어 분기 금지)", {"node_id": "dec", "kind": "decision"})
    # must not raise (regression: ValueError 'NaN values found')
    hits = m.retrieve("게이팅", k=4)
    assert isinstance(hits, list)


def test_d06_reindex_is_idempotent_no_duplicate_vectors():
    """D-06: re-indexing the same decision upserts (stable ids) instead of appending."""
    m = MemoryStore(DeterministicEmbeddings())
    m.index_text("Gate features with flags.", {"node_id": "d1", "kind": "decision"})
    m.index_text("Gate features with flags.", {"node_id": "d1", "kind": "decision"})
    # InMemoryVectorStore keys by id; stable {node_id}:{i} ids mean one stored doc, not two
    assert len(m.store.store) == 1


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    d = tmp_path_factory.mktemp("fixrepo")
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=d, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=d, check=True)
    Path(d, "README.md").write_text("seed\n")
    subprocess.run(["git", "add", "-A"], cwd=d, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=d, check=True)
    return str(d)


def test_d01_seeded_step_review_is_actionable_via_db_direct(repo):
    """D-01: a seeded awaiting_review step (no LangGraph checkpoint) can be approved
    directly on the DB instead of returning a dead, silent 409."""
    os.environ["ASV3_AGENT_MODE"] = "simulated"
    os.environ["ASV3_TARGET_REPO_DIR"] = repo
    init_db()
    db = SessionLocal()
    if db.get(Node, f"{PID}-t") is None:
        seed_graph(
            db,
            PID,
            nodes=[
                {"id": f"{PID}-obj", "kind": "objective", "label": "todo"},
                {"id": f"{PID}-t", "kind": "ticket", "label": "ticket", "status": "executing"},
                {"id": f"{PID}-t-only", "kind": "step", "label": "게이트", "status": "awaiting_review"},
            ],
            edges=[
                {"id": f"e-{PID}-1", "from": f"{PID}-obj", "to": f"{PID}-t", "kind": "has"},
                {"id": f"e-{PID}-2", "from": f"{PID}-t", "to": f"{PID}-t-only", "kind": "has"},
            ],
        )
    db.close()

    from app.main import app

    c = TestClient(app)
    r = c.post(f"/projects/{PID}/steps/{PID}-t-only/review", json={"kind": "approve"})
    assert r.status_code == 200, r.text  # was 409 before the DB-direct fallback
    db = SessionLocal()
    assert db.get(Node, f"{PID}-t-only").status == "done"
    assert db.get(Node, f"{PID}-t").status == "done"  # its only step done -> ticket done
    db.close()


def test_d01_review_on_unknown_step_still_409s(repo):
    """The DB-direct fallback must not turn a genuinely-invalid review into a success."""
    from app.main import app

    c = TestClient(app)
    r = c.post(f"/projects/{PID}/steps/{PID}-nope/review", json={"kind": "approve"})
    assert r.status_code == 409


def test_d03_takeover_then_complete_is_not_a_dead_end(repo):
    """D-03: after a takeover the graph ends, but the taken-over step can still be
    completed via a follow-up approve (now routed through the DB-direct path) — it is no
    longer a permanent dead end."""
    os.environ["ASV3_AGENT_MODE"] = "simulated"
    os.environ["ASV3_TARGET_REPO_DIR"] = repo
    init_db()
    db = SessionLocal()
    if db.get(Node, "ptk-obj") is None:
        seed_graph(
            db, "ptk", nodes=[{"id": "ptk-obj", "kind": "objective", "label": "todo"}], edges=[]
        )
    db.close()

    from app.main import app

    c = TestClient(app)
    tid = "ptk-t1"
    body = c.post(f"/projects/ptk/tickets/{tid}/plan", json={"title": "인수 검증"}).json()
    c.post(f"/projects/ptk/tickets/{tid}/plan/approve", json={"steps": body["awaiting"]["steps"]})
    # step 1 is at its review gate -> take it over (graph ends here)
    r = c.post(f"/projects/ptk/steps/{tid}-s1/review", json={"kind": "takeover"})
    assert r.status_code == 200, r.text
    # the human finished it manually -> mark it done (DB-direct, since the graph ended)
    r = c.post(f"/projects/ptk/steps/{tid}-s1/review", json={"kind": "approve"})
    assert r.status_code == 200, r.text  # was a dead 409 before
    db = SessionLocal()
    assert db.get(Node, f"{tid}-s1").status == "done"
    db.close()


def test_d04_unhandled_500_keeps_cors_headers(monkeypatch):
    """D-04: an unhandled error must still return CORS headers (catch-all middleware sits
    inside CORS), so a browser cross-origin fetch can read the error instead of an opaque
    'Failed to fetch'."""
    from app.main import app
    from app.routers import memory as mem_router

    def boom(*_a, **_k):
        raise RuntimeError("boom")

    monkeypatch.setattr(mem_router.MEMORY, "retrieve", boom)
    c = TestClient(app, raise_server_exceptions=False)
    r = c.get(
        "/memory/search", params={"q": "x"}, headers={"Origin": "http://127.0.0.1:5180"}
    )
    assert r.status_code == 500
    assert r.headers.get("access-control-allow-origin") == "*"


def test_d25_distinct_tickets_get_distinct_code_regions(repo):
    """D-25: two tickets in the same project must produce DISTINCT code-region nodes —
    simulated output is namespaced per ticket, so step N of ticket A no longer collides
    with step N of ticket B on a single global cr:generated/step_N.ts node."""
    os.environ["ASV3_AGENT_MODE"] = "simulated"
    os.environ["ASV3_TARGET_REPO_DIR"] = repo
    init_db()
    db = SessionLocal()
    if db.get(Node, "pcr-obj") is None:
        seed_graph(
            db, "pcr", nodes=[{"id": "pcr-obj", "kind": "objective", "label": "o"}], edges=[]
        )
    db.close()

    from app.main import app

    c = TestClient(app)
    for tid in ("pcr-a", "pcr-b"):
        b = c.post(f"/projects/pcr/tickets/{tid}/plan", json={"title": tid}).json()
        c.post(f"/projects/pcr/tickets/{tid}/plan/approve", json={"steps": b["awaiting"]["steps"]})

    db = SessionLocal()
    crs = [
        n.id for n in db.query(Node).filter(Node.project_id == "pcr", Node.kind == "code_region")
    ]
    db.close()
    # each ticket got its own region (namespaced by tid), not a single shared node
    assert any("pcr-a" in cid for cid in crs)
    assert any("pcr-b" in cid for cid in crs)


def test_workspace_root_gives_each_project_its_own_repo(tmp_path, monkeypatch):
    """ASV3_WORKSPACE_DIR: each project commits into its OWN {workspace}/{project_id} repo
    (auto-created), instead of one global ASV3_TARGET_REPO_DIR shared by all projects."""
    monkeypatch.setenv("ASV3_AGENT_MODE", "simulated")
    monkeypatch.setenv("ASV3_WORKSPACE_DIR", str(tmp_path))
    monkeypatch.delenv("ASV3_TARGET_REPO_DIR", raising=False)  # workspace wins anyway
    init_db()
    db = SessionLocal()
    for pid in ("pw1", "pw2"):
        if db.get(Node, f"{pid}-obj") is None:
            seed_graph(db, pid, nodes=[{"id": f"{pid}-obj", "kind": "objective", "label": pid}], edges=[])
    db.close()

    from app.main import app

    c = TestClient(app)
    for pid in ("pw1", "pw2"):
        b = c.post(f"/projects/{pid}/tickets/{pid}-t/plan", json={"title": "t"}).json()
        c.post(f"/projects/{pid}/tickets/{pid}-t/plan/approve", json={"steps": b["awaiting"]["steps"]})

    # each project got its own auto-init'd repo under the workspace root...
    assert (tmp_path / "pw1" / ".git").is_dir()
    assert (tmp_path / "pw2" / ".git").is_dir()
    # ...and the executor wrote into the correct per-project repo
    assert (tmp_path / "pw1" / "generated" / "pw1-t").is_dir()
    assert (tmp_path / "pw2" / "generated" / "pw2-t").is_dir()


def test_objective_repo_dir_override_wins(tmp_path, monkeypatch):
    """A project's Objective.data.repo_dir overrides the workspace/env resolution."""
    monkeypatch.setenv("ASV3_AGENT_MODE", "simulated")
    monkeypatch.setenv("ASV3_WORKSPACE_DIR", str(tmp_path / "workspace"))
    custom = tmp_path / "my-existing-repo"
    init_db()
    db = SessionLocal()
    if db.get(Node, "povr-obj") is None:
        seed_graph(
            db, "povr",
            nodes=[{"id": "povr-obj", "kind": "objective", "label": "o", "data": {"repo_dir": str(custom)}}],
            edges=[],
        )
    db.close()

    from app.main import app

    c = TestClient(app)
    b = c.post("/projects/povr/tickets/povr-t/plan", json={"title": "t"}).json()
    c.post("/projects/povr/tickets/povr-t/plan/approve", json={"steps": b["awaiting"]["steps"]})
    assert (custom / "generated" / "povr-t").is_dir()                  # used the override
    assert not (tmp_path / "workspace" / "povr").exists()              # not the workspace path


def test_project_info_and_repo_override_endpoints(monkeypatch):
    """UI sync: GET /projects/{pid}/info exposes the per-project target repo, and
    POST /projects/{pid}/repo sets/clears the override (stored on the Objective)."""
    monkeypatch.setenv("ASV3_AGENT_MODE", "simulated")
    monkeypatch.setenv("ASV3_WORKSPACE_DIR", "/tmp/ws-test")
    monkeypatch.delenv("ASV3_TARGET_REPO_DIR", raising=False)
    init_db()
    db = SessionLocal()
    if db.get(Node, "pinfo-obj") is None:
        seed_graph(db, "pinfo", nodes=[{"id": "pinfo-obj", "kind": "objective", "label": "o"}], edges=[])
    db.close()

    from app.main import app

    c = TestClient(app)
    # default resolution = workspace/{pid}
    r = c.get("/projects/pinfo/info").json()
    assert r == {"projectId": "pinfo", "repoDir": "/tmp/ws-test/pinfo", "repoSource": "workspace"}
    # set an override
    r = c.post("/projects/pinfo/repo", json={"repoDir": "/custom/repo"}).json()
    assert r["repoDir"] == "/custom/repo" and r["repoSource"] == "override"
    assert c.get("/projects/pinfo/info").json()["repoDir"] == "/custom/repo"  # persisted
    # clear -> back to the workspace default
    r = c.post("/projects/pinfo/repo", json={"repoDir": ""}).json()
    assert r["repoSource"] == "workspace" and r["repoDir"] == "/tmp/ws-test/pinfo"


def test_d11_never_started_ticket_is_not_done(repo):
    """D-11: a ticket that was never planned must report done:false (empty checkpoint
    is 'not started', not 'finished')."""
    from app.main import app

    c = TestClient(app)
    r = c.get(f"/projects/{PID}/tickets/{PID}-never/state")
    assert r.status_code == 200
    assert r.json()["done"] is False
