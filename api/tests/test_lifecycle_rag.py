import os
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.routers.lifecycle as lifecycle
from app.db import SessionLocal, init_db
from app.graph.store import seed_graph
from app.main import app
from app.models import Node
from app.routers.memory import MEMORY
from app.services.executor import ExecResult

PID = "prag"


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    d = tmp_path_factory.mktemp("ragrepo")
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=d, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=d, check=True)
    Path(d, "README.md").write_text("seed\n")
    subprocess.run(["git", "add", "-A"], cwd=d, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=d, check=True)
    return str(d)


def test_indexed_decision_reaches_the_executor_prompt(repo, monkeypatch):
    os.environ["ASV3_AGENT_MODE"] = "simulated"
    os.environ["ASV3_TARGET_REPO_DIR"] = repo
    init_db()
    db = SessionLocal()
    if db.get(Node, f"{PID}-obj") is None:
        seed_graph(
            db,
            PID,
            nodes=[{"id": f"{PID}-obj", "kind": "objective", "label": "billing gateway todo app"}],
            edges=[],
        )
    db.close()

    # a prior decision lives in semantic memory
    MEMORY.index_text(
        "Use Stripe for the billing gateway integration; never store raw card data.",
        {"project_id": PID, "node_id": "dprior", "kind": "decision"},
    )

    # capture the prompt the executor receives (what would be sent to Claude)
    captured: list[str] = []

    class CapturingExecutor:
        def __init__(self, write):
            self.write = write

        def run(self, repo_dir: str, prompt: str) -> ExecResult:
            captured.append(prompt)
            self.write(repo_dir)
            return ExecResult(summary="ok", decision=None, ok=True, output="")

    monkeypatch.setattr(lifecycle, "SimulatedExecutor", CapturingExecutor)

    c = TestClient(app)
    tid = f"{PID}-t1"
    c.post(f"/projects/{PID}/tickets/{tid}/plan", json={"title": "결제 붙이기"})
    c.post(f"/projects/{PID}/tickets/{tid}/plan/approve", json={})

    assert captured, "executor never ran"
    prompt = captured[0]
    assert "Relevant prior knowledge" in prompt  # the RAG packet was injected
    assert "Stripe" in prompt  # the actual prior decision reached the prompt


def test_changes_rerun_indexes_the_new_decision(repo, monkeypatch):
    os.environ["ASV3_AGENT_MODE"] = "simulated"
    os.environ["ASV3_TARGET_REPO_DIR"] = repo
    init_db()
    db = SessionLocal()
    if db.get(Node, "prag2-obj") is None:
        seed_graph(
            db, "prag2", nodes=[{"id": "prag2-obj", "kind": "objective", "label": "obj"}], edges=[]
        )
    db.close()

    calls = {"n": 0}

    class DecisionExecutor:
        def __init__(self, write):
            self.write = write

        def run(self, repo_dir: str, prompt: str) -> ExecResult:
            calls["n"] += 1
            self.write(repo_dir)
            return ExecResult(summary="ok", decision=f"decisiontoken{calls['n']}", ok=True, output="")

    monkeypatch.setattr(lifecycle, "SimulatedExecutor", DecisionExecutor)

    c = TestClient(app)
    tid = "prag2-t1"
    body = c.post(f"/projects/prag2/tickets/{tid}/plan", json={"title": "t"}).json()
    c.post(f"/projects/prag2/tickets/{tid}/plan/approve", json={"steps": body["awaiting"]["steps"]})
    # step 1 ran once -> decisiontoken1 indexed
    c.post(f"/projects/prag2/steps/{tid}-s1/review", json={"kind": "changes"})  # re-run step 1

    # the re-run produced a NEW decision; it must be the node label AND retrievable via RAG
    db = SessionLocal()
    assert db.get(Node, f"dec:{tid}-s1").label == "decisiontoken2"
    db.close()
    hits = MEMORY.retrieve("decisiontoken2", k=1)
    assert hits and "decisiontoken2" in hits[0]["text"]
