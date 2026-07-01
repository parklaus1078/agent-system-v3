"""Diff capture must survive a real CLI executor that commits its OWN work — then the
lifecycle's commit_all sees a clean tree and returns None, but the step's change is real and
must still be ingested (the SQewL 'NL→SQL translation layer' bug: empty diff for a 370-line
committed change)."""

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import init_db
from app.git.repo import commit_all, diff_since, head_sha


def _g(d, *a):
    subprocess.run(["git", *a], cwd=d, check=True, capture_output=True)


def test_diff_since_captures_a_commit_made_by_the_executor_itself(tmp_path):
    d = str(tmp_path)
    _g(d, "init", "-q")
    _g(d, "config", "user.email", "t@t")
    _g(d, "config", "user.name", "t")
    Path(tmp_path, "seed").write_text("s\n")
    _g(d, "add", "-A")
    _g(d, "commit", "-qm", "init")
    pre = head_sha(d)

    # a real CLI executor writes AND commits its own work -> the tree is clean afterward
    Path(tmp_path, "translator.py").write_text("x = 1\n")
    _g(d, "add", "-A")
    _g(d, "commit", "-qm", "step 2: NL->SQL translation layer")
    assert commit_all(d, "step 2") is None  # the OLD capture saw sha=None -> empty diff (the bug)

    # ...but HEAD moved, so diff_since captures the real change regardless of who committed it
    diff = diff_since(d, pre)
    assert "translator.py" in diff and "x = 1" in diff
    assert diff_since(d, head_sha(d)) == ""  # nothing new since HEAD -> genuinely empty


def test_graph_id_columns_are_not_length_limited():
    """Composite ids like `tested_by:{step_id}:{path}` exceed 64 chars on real projects. The
    id/ref columns must NOT be a small VARCHAR — Postgres REJECTED VARCHAR(64) (StringDataRight-
    Truncation) while SQLite silently accepted it, so this bug passed every test and only broke
    prod. Guard the widths so a future narrowing is caught here."""
    from app.models import Edge, Node

    for col in (Node.__table__.c.id, Edge.__table__.c.id, Edge.__table__.c.src, Edge.__table__.c.dst):
        length = getattr(col.type, "length", None)
        assert length is None or length >= 255, f"{col.table.name}.{col.name} is capped at {length}"


def test_lifecycle_captures_diff_when_the_executor_self_commits(tmp_path, monkeypatch):
    monkeypatch.setenv("ASV3_AGENT_MODE", "simulated")
    monkeypatch.setenv("ASV3_ASYNC_EXEC", "0")  # in-request execution so we can read the result
    monkeypatch.setenv("ASV3_WORKSPACE_DIR", str(tmp_path))
    init_db()

    import app.routers.lifecycle as lc
    from app.git.repo import _git

    # make the simulated executor COMMIT its own edit (like a real CLI can) -> commit_all sees clean
    orig = lc._sim_write

    def self_committing(repo_dir, tid):
        orig(repo_dir, tid)
        _git(repo_dir, "add", "-A")
        _git(repo_dir, "commit", "-q", "-m", "executor self-commit")

    monkeypatch.setattr(lc, "_sim_write", self_committing)

    from app.main import app

    c = TestClient(app)
    pid, tid = "selfc", "selfc-t1"
    body = c.post(f"/projects/{pid}/tickets/{tid}/plan", json={"title": "t"}).json()
    c.post(f"/projects/{pid}/tickets/{tid}/plan/approve", json={"steps": body["awaiting"]["steps"]})
    detail = c.get(f"/projects/{pid}/steps/{tid}-s1").json()
    # despite commit_all returning None (executor already committed), the diff is captured
    assert detail["diff"], "step diff must be captured even when the executor self-commits"
    assert any(b["patch"].strip() for b in detail["diff"])
