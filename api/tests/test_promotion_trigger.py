import os
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal, init_db
from app.graph.store import seed_graph
from app.main import app
from app.models import Node

PID = "pprom"


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    d = tmp_path_factory.mktemp("promrepo")
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=d, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=d, check=True)
    Path(d, "README.md").write_text("seed\n")
    subprocess.run(["git", "add", "-A"], cwd=d, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=d, check=True)
    return str(d)


def test_completing_the_last_ticket_promotes_decisions_to_wiki(repo, tmp_path_factory):
    wiki = tmp_path_factory.mktemp("wiki")
    os.environ["ASV3_AGENT_MODE"] = "simulated"
    os.environ["ASV3_TARGET_REPO_DIR"] = repo
    os.environ["ASV3_LLM_WIKI_ROOT"] = str(wiki)
    init_db()
    db = SessionLocal()
    if db.get(Node, f"{PID}-obj") is None:
        seed_graph(
            db,
            PID,
            nodes=[
                {"id": f"{PID}-obj", "kind": "objective", "label": "todo"},
                {"id": f"{PID}-dec", "kind": "decision", "label": "Gate by entitlement flag."},
            ],
            edges=[],
        )
    db.close()

    c = TestClient(app)
    tid = f"{PID}-t1"
    body = c.post(f"/projects/{PID}/tickets/{tid}/plan", json={"title": "유일 티켓"}).json()
    c.post(f"/projects/{PID}/tickets/{tid}/plan/approve", json={"steps": body["awaiting"]["steps"]})
    # approve every step's review gate -> ticket (and the whole project) completes
    for i in range(len(body["awaiting"]["steps"])):
        c.post(f"/projects/{PID}/steps/{tid}-s{i + 1}/review", json={"kind": "approve"})

    db = SessionLocal()
    assert db.get(Node, tid).status == "done"
    db.close()
    # promotion fired: the project's Decision is now a wiki page
    page = wiki / "kay_second_brain" / "wiki" / "decisions" / f"asv3-{PID}-{PID}-dec.md"
    assert page.exists(), "promote_project was not triggered on project completion"
    assert "entitlement flag" in page.read_text()
