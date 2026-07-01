import os
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal, init_db
from app.graph.store import seed_graph
from app.models import Node

PID = "plc"


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    d = tmp_path_factory.mktemp("targetrepo")
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=d, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=d, check=True)
    Path(d, "README.md").write_text("seed\n")
    subprocess.run(["git", "add", "-A"], cwd=d, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=d, check=True)
    return str(d)


@pytest.fixture(scope="module", autouse=True)
def _env(repo):
    os.environ["ASV3_AGENT_MODE"] = "simulated"
    os.environ["ASV3_TARGET_REPO_DIR"] = repo
    init_db()
    db = SessionLocal()
    if db.get(Node, f"{PID}-obj") is None:
        seed_graph(
            db,
            PID,
            nodes=[{"id": f"{PID}-obj", "kind": "objective", "label": "구독 할일앱"}],
            edges=[],
        )
    db.close()


def _client():
    # import inside the test so ASV3_* env vars are set before the router builds graphs
    from app.main import app

    return TestClient(app)


def test_full_lifecycle_persists_to_db_and_repo(repo):
    c = _client()
    tid = f"{PID}-t1"

    # 1) start plan -> graph interrupts at plan_approval. The ticket is NOT persisted yet
    #    (only on approve) so an abandoned/duplicated propose leaves no orphan ticket.
    r = c.post(f"/projects/{PID}/tickets/{tid}/plan", json={"title": "구독 결제 게이팅"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["awaiting"]["type"] == "plan_approval"
    assert len(body["awaiting"]["steps"]) == 3
    db = SessionLocal()
    assert db.get(Node, tid) is None  # not created at propose time (was: created eagerly)
    db.close()

    # 2) approve plan -> 3 step nodes, first step executed/committed/ingested
    steps = body["awaiting"]["steps"]
    r = c.post(f"/projects/{PID}/tickets/{tid}/plan/approve", json={"steps": steps})
    assert r.status_code == 200, r.text
    db = SessionLocal()
    step_nodes = db.query(Node).filter(Node.project_id == PID, Node.kind == "step").all()
    assert len(step_nodes) == 3
    assert db.get(Node, f"{tid}-s1").status == "awaiting_review"  # executed, at the gate
    crs = db.query(Node).filter(Node.project_id == PID, Node.kind == "code_region").all()
    assert len(crs) >= 1  # diff ingested into the graph
    db.close()
    # ASV3_TARGET_REPO_DIR is a per-project root, so the commit lands in {repo}/{PID}
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=os.path.join(repo, PID), capture_output=True, text=True
    ).stdout
    assert "step 1" in log  # a real commit landed in the target repo

    # 3) review-approve each step -> ticket reaches done
    for i in range(3):
        r = c.post(f"/projects/{PID}/steps/{tid}-s{i + 1}/review", json={"kind": "approve"})
        assert r.status_code == 200, r.text
    db = SessionLocal()
    assert db.get(Node, f"{tid}-s1").status == "done"
    assert db.get(Node, f"{tid}-s3").status == "done"
    assert db.get(Node, tid).status == "done"
    db.close()


def test_state_endpoint_reports_progress(repo):
    c = _client()
    tid = f"{PID}-t2"
    c.post(f"/projects/{PID}/tickets/{tid}/plan", json={"title": "두번째"})
    r = c.get(f"/projects/{PID}/tickets/{tid}/state")
    assert r.status_code == 200
    assert r.json()["awaiting"]["type"] == "plan_approval"


def test_start_plan_is_idempotent_and_never_resets_a_started_graph(repo):
    c = _client()
    tid = f"{PID}-t3"
    # calling /plan twice returns the same pending plan, no duplicate steps
    a = c.post(f"/projects/{PID}/tickets/{tid}/plan", json={"title": "세번째"}).json()
    b = c.post(f"/projects/{PID}/tickets/{tid}/plan", json={"title": "세번째"}).json()
    assert b["awaiting"]["type"] == "plan_approval"
    assert a["awaiting"]["steps"] == b["awaiting"]["steps"]

    # approve, then call /plan again: it must NOT reset the graph back to planning
    c.post(f"/projects/{PID}/tickets/{tid}/plan/approve", json={"steps": a["awaiting"]["steps"]})
    again = c.post(f"/projects/{PID}/tickets/{tid}/plan", json={"title": "세번째"}).json()
    assert again["awaiting"]["type"] == "review"  # still executing, not re-proposed
    db = SessionLocal()
    assert db.get(Node, f"{tid}-s1").status == "awaiting_review"
    db.close()
