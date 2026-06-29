import subprocess
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from app.services.planner import SimulatedPlanner
from app.services.executor import SimulatedExecutor
from app.services.lifecycle_graph import build_graph


def _commit(repo: str, msg: str) -> str:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", msg], cwd=repo, check=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()


def test_plan_approve_then_review_each_step(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)

    committed = []
    ex = SimulatedExecutor(lambda repo: Path(repo, "f.ts").write_text("x\n"))
    graph = build_graph(
        planner=SimulatedPlanner(),
        executor=ex,
        checkpointer=MemorySaver(),
        on_steps_approved=lambda steps: None,
        on_step_committed=lambda i, sha, summary, decision: committed.append((i, summary)),
        commit_fn=_commit,
    )
    cfg = {"configurable": {"thread_id": "ticket:1"}}
    state = {
        "project_id": "p1",
        "ticket_id": "t1",
        "repo_dir": str(tmp_path),
        "objective": "Todo",
        "ticket_title": "CRUD",
        "steps": [],
        "current": 0,
        "decisions": [],
    }

    # 1) plan node interrupts for approval
    graph.invoke(state, cfg)
    assert graph.get_state(cfg).next  # interrupted (awaiting approval)

    # 2) approve decomposition -> run first step -> interrupt at review
    graph.invoke(Command(resume={"approve": True}), cfg)
    assert len(committed) == 1

    # 3) approve the review gate for each of the 3 steps -> graph reaches END
    for _ in range(3):
        graph.invoke(Command(resume={"kind": "approve"}), cfg)
    assert len(committed) == 3
    assert not graph.get_state(cfg).next  # END


def test_changes_reruns_same_step(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)

    committed = []
    ex = SimulatedExecutor(lambda repo: Path(repo, "f.ts").write_text("x\n"))
    graph = build_graph(
        planner=SimulatedPlanner(),
        executor=ex,
        checkpointer=MemorySaver(),
        on_step_committed=lambda i, sha, summary, decision: committed.append(i),
        commit_fn=_commit,
    )
    cfg = {"configurable": {"thread_id": "ticket:2"}}
    graph.invoke(
        {"project_id": "p1", "ticket_id": "t1", "repo_dir": str(tmp_path), "objective": "O",
         "ticket_title": "T", "steps": [], "current": 0, "decisions": []},
        cfg,
    )
    graph.invoke(Command(resume={"approve": True}), cfg)  # exec step 0
    assert committed == [0]
    # request changes -> re-runs the SAME step (current stays 0)
    graph.invoke(Command(resume={"kind": "changes"}), cfg)
    assert committed == [0, 0]
