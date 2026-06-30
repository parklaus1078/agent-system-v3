from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import SessionLocal, get_session, make_checkpointer
from ..graph import store
from ..graph.diff_ingest import apply_step_diff, parse_diff
from ..git.repo import commit_all, diff_of_commit
from ..models import Node, Edge
from ..schemas import (
    LifecycleStateOut,
    PlanApproveIn,
    PlanStartIn,
    ProjectInfoOut,
    ProjectRepoIn,
    ReviewActionIn,
)
from ..schemas_plan import StepSpec
from ..services.executor import CliExecutor, SimulatedExecutor
from ..services.lifecycle_graph import build_graph
from ..services.planner import CliPlanner, LangChainPlanner, SimulatedPlanner
from ..services.prompt_build import build_step_prompt, step_rag_context
from ..services.promotion import promote_project
from .memory import MEMORY

router = APIRouter(prefix="/projects/{pid}", tags=["lifecycle"])
logger = logging.getLogger("asv3.lifecycle")

_REVIEW_STATUS = {"approve": "done", "changes": "executing", "takeover": "awaiting_review"}

# Serializes the (rare, single-user) concurrent access to the shared LangGraph checkpointer
# — a background execution invoke vs. another user action. The live UI poll hits getGraph
# (the DB graph, incl. `data.activity`), NOT the checkpointer, so polling never waits here.
_GRAPH_LOCK = threading.RLock()
# Background execution threads — tracked only so tests can deterministically join them
# (pruned of finished threads on each spawn so it doesn't grow unbounded in production).
_BG_THREADS: list[threading.Thread] = []


def _mode() -> str:
    return os.environ.get("ASV3_AGENT_MODE", "simulated")


def _async_enabled() -> bool:
    """Run the (slow, real-Claude) execution in a background thread so the request returns
    immediately and the UI tracks progress via `data.activity` polling. Tests/sync callers
    set ASV3_ASYNC_EXEC=0 for deterministic, in-request execution."""
    return os.environ.get("ASV3_ASYNC_EXEC", "1").lower() not in ("0", "false", "no")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _set_activity(db: Session, pid: str, tid: str, state: str | None, detail: str = "") -> None:
    """Record coarse 'what the backend is doing now' on the ticket node (read live by the
    UI's getGraph poll). state=None clears it. Tolerates a not-yet-created ticket."""
    t = db.get(Node, tid)
    if t is None:
        return
    data = dict(t.data or {})
    if state is None:
        data.pop("activity", None)
    else:
        data["activity"] = {"state": state, "detail": detail, "since": _now_iso()}
    t.data = data
    db.commit()


def _total_steps(db: Session, pid: str, tid: str) -> int:
    return sum(1 for n in store.neighbors(db, pid, tid, "out") if n.kind == "step")


# Default workspace root (under api/) when nothing is configured.
_DEFAULT_WORKSPACE = Path(__file__).resolve().parents[2] / ".asv3-workspace"


def _ensure_git_repo(path: str) -> None:
    """Make `path` an initialized git repo with at least one commit, so the executor's
    commits land. Idempotent + cheap (only acts when `.git` is missing); never touches the
    CWD. An existing repo (e.g. a user's real project) is left untouched."""
    if not path or path == "." or os.path.isdir(os.path.join(path, ".git")):
        return
    try:
        os.makedirs(path, exist_ok=True)
        subprocess.run(["git", "init", "-q"], cwd=path, check=False)  # noqa: S607
        subprocess.run(["git", "config", "user.email", "control-tower@local"], cwd=path, check=False)
        subprocess.run(["git", "config", "user.name", "Control Tower"], cwd=path, check=False)
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "init (asv3)"], cwd=path, check=False)
    except Exception:  # noqa: BLE001 — best-effort; commits degrade gracefully if this fails
        logger.exception("could not initialize target repo at %s", path)


def _resolve_repo_path(db: Session, pid: str) -> tuple[str, str]:
    """Resolve a project's target repo path (NO side effects) + where it came from.
    Precedence:
      1) the Objective's data.repo_dir          (explicit per-project override)
      2) $ASV3_WORKSPACE_DIR/{project_id}        (workspace root -> one repo per project)
      3) $ASV3_TARGET_REPO_DIR/{project_id}      (deprecated alias of the workspace root)
      4) <api>/.asv3-workspace/{project_id}      (default workspace)"""
    obj = _objective(db, pid)
    override = (obj.data or {}).get("repo_dir") if obj else None
    workspace = os.environ.get("ASV3_WORKSPACE_DIR")
    legacy = os.environ.get("ASV3_TARGET_REPO_DIR")
    if override:
        return str(override), "override"
    if workspace:
        return os.path.join(workspace, pid), "workspace"
    if legacy:
        # ASV3_TARGET_REPO_DIR is a deprecated ALIAS of the workspace root: it too is a
        # PER-PROJECT root ({root}/{pid}), not a single repo shared by all projects.
        return os.path.join(legacy, pid), "legacy"
    return str(_DEFAULT_WORKSPACE / pid), "default"


def _repo_dir(db: Session, pid: str) -> str:
    """The git repo a project's executor commits into (resolved per-project) — lazily
    created + git-init'd."""
    path, _ = _resolve_repo_path(db, pid)
    _ensure_git_repo(path)
    return path


def _cfg(tid: str) -> dict:
    return {"configurable": {"thread_id": f"ticket:{tid}"}}


def _ticket_of_step(db: Session, pid: str, sid: str) -> str:
    """The owning ticket of a step. Prefer the real parent via the `has` edge (works for
    any id, incl. seeded ids like s4/sy2 that don't follow the {tid}-s{n} convention);
    fall back to the naming convention if the step isn't in the DB."""
    parent = next(
        (p for p in store.neighbors(db, pid, sid, "in") if p.kind == "ticket"), None
    )
    return parent.id if parent is not None else re.sub(r"-s\d+$", "", sid)


def _sim_write(repo_dir: str, tid: str) -> None:
    """Simulated executor edit: add a new file per step so every step yields a real,
    non-empty commit (which diff_of_commit + apply_step_diff then ingest). Namespaced by
    ticket (generated/{tid}/) so distinct tickets produce DISTINCT code-region nodes —
    otherwise every ticket's step N wrote the same generated/step_N.ts and shared the one
    global `cr:generated/step_N.ts` node (cross-ticket touches collision)."""
    gen = os.path.join(repo_dir, "generated", tid)
    os.makedirs(gen, exist_ok=True)
    n = len([f for f in os.listdir(gen) if f.endswith(".ts")]) + 1
    with open(os.path.join(gen, f"step_{n}.ts"), "w", encoding="utf-8") as f:
        f.write(f"export const step{n} = true;\n")


def _objective(db: Session, pid: str) -> Node | None:
    return db.scalars(
        select(Node).where(Node.project_id == pid, Node.kind == "objective")
    ).first()


def _all_tickets_done(db: Session, pid: str) -> bool:
    tickets = db.scalars(
        select(Node).where(Node.project_id == pid, Node.kind == "ticket")
    ).all()
    return bool(tickets) and all(t.status == "done" for t in tickets)


def _existing_steps(db: Session, pid: str, tid: str) -> list[dict]:
    """A ticket's current step children (ordered by their `has` edge), as proposal dicts.
    Re-planning seeds the proposal from these so the planner revises the EXISTING plan
    instead of replacing it with generic steps."""
    edges = db.scalars(
        select(Edge).where(Edge.project_id == pid, Edge.src == tid, Edge.kind == "has")
    ).all()
    out: list[dict] = []
    for e in sorted(edges, key=lambda e: e.id):
        child = db.get(Node, e.dst)
        if child is not None and child.kind == "step":
            out.append({"label": child.label, "intent": "", "acceptance": ""})
    return out


def _build(db: Session, pid: str, tid: str, title: str | None = None):
    def on_steps_approved(steps: list[dict]) -> None:
        store.approve_plan(db, pid, tid, [s["label"] for s in steps], title)
        # execution begins next — surface it immediately so the board isn't a frozen blank.
        _set_activity(db, pid, tid, "executing", f"step 1/{len(steps)}")

    def on_step_start(i: int, total: int) -> None:
        _set_activity(db, pid, tid, "executing", f"step {i + 1}/{total}")

    def on_step_committed(
        i: int, sha: str | None, summary: str, decision: str | None, ok: bool = True
    ) -> None:
        sid = f"{tid}-s{i + 1}"
        diff_blobs: list[dict] = []
        if sha:  # None => executor made no edits; still gate the step, just no diff
            try:
                diff_text = diff_of_commit(_repo_dir(db, pid), sha)
                apply_step_diff(db, pid, sid, sha, diff_text)
                # store the per-file patch ON THE STEP node so the review pane renders the
                # real diff (was: step_detail returned patch="" — empty diff view).
                diff_blobs = [{"path": tf.path, "patch": tf.patch} for tf in parse_diff(diff_text)]
            except Exception:  # git/diff failure must not strand the step un-gated
                db.rollback()  # discard any partial ingest; the status update below still lands
                logger.exception("diff ingest failed for step %s (commit %s)", sid, sha)
        node = db.get(Node, sid)
        if node is not None:
            # a failed/no-op executor must NOT masquerade as a clean awaiting_review gate
            node.status = "awaiting_review" if ok else "blocked"
            node.data = {**(node.data or {}), "summary": summary, "diff": diff_blobs, "ok": ok}
        total = _total_steps(db, pid, tid) or (i + 1)
        _set_activity(
            db, pid, tid,
            "awaiting_review" if ok else "blocked",
            f"step {i + 1}/{total} {'리뷰 대기' if ok else '실패'}",
        )
        logger.info(
            "step committed: %s ok=%s sha=%s files=%d", sid, ok, (sha or "-")[:8], len(diff_blobs)
        )
        if decision:
            did = f"dec:{sid}"
            existing = db.get(Node, did)
            if existing is None:
                db.add(Node(id=did, project_id=pid, kind="decision", label=decision))
                db.add(
                    Edge(id=f"decided:{sid}", project_id=pid, src=sid, dst=did, kind="decided")
                )
            else:
                existing.label = decision  # a 'changes' re-run can produce a new decision
            # ALWAYS index the latest decision so later steps recall it via RAG (even on re-run)
            MEMORY.index_text(decision, {"project_id": pid, "node_id": did, "kind": "decision"})
        db.commit()

    def build_prompt(state, step) -> str:
        spec = StepSpec(**step)
        rag = step_rag_context(MEMORY, state.get("objective", ""), spec)
        return build_step_prompt(db, pid, tid, spec, rag_context=rag)

    if _mode() == "real":
        brain = os.environ.get("ASV3_BRAIN", "claude")
        # ChatAnthropic needs ANTHROPIC_API_KEY; without it, route planning through the
        # CLI (same Claude Code OAuth as the executor) so real mode still reaches Claude.
        if os.environ.get("ANTHROPIC_API_KEY"):
            planner = LangChainPlanner()
        else:
            planner = CliPlanner(brain=brain)
        executor = CliExecutor(brain=brain)
    else:
        planner = SimulatedPlanner()
        executor = SimulatedExecutor(lambda repo_dir: _sim_write(repo_dir, tid))

    return build_graph(
        planner=planner,
        executor=executor,
        checkpointer=make_checkpointer(),
        commit_fn=commit_all,
        on_steps_approved=on_steps_approved,
        on_step_start=on_step_start,
        on_step_committed=on_step_committed,
        build_prompt=build_prompt,
    )


def _invoke_async(pid: str, tid: str, title: str | None, resume: dict, after=None) -> None:
    """Run a (possibly long) graph resume in a background daemon thread so the HTTP request
    returns immediately. Uses its OWN DB session (sessions aren't thread-safe) and serializes
    the shared checkpointer behind _GRAPH_LOCK. `after(db2)` runs post-invoke (e.g. mark the
    ticket done / promote) in the same worker session."""

    def worker() -> None:
        db2 = SessionLocal()
        try:
            graph = _build(db2, pid, tid, title=title)
            with _GRAPH_LOCK:
                graph.invoke(Command(resume=resume), _cfg(tid))
                snap = graph.get_state(_cfg(tid))
            if after is not None:
                after(db2, snap)
        except Exception:  # never crash the worker thread silently
            logger.exception("async graph invoke failed (pid=%s tid=%s)", pid, tid)
            try:
                _set_activity(db2, pid, tid, "blocked", "실행 중 오류")
            except Exception:
                logger.exception("could not record async-failure activity")
        finally:
            db2.close()

    th = threading.Thread(target=worker, daemon=True, name=f"exec:{tid}")
    _BG_THREADS[:] = [t for t in _BG_THREADS if t.is_alive()]  # prune finished
    _BG_THREADS.append(th)
    th.start()


def _awaiting(snap):
    return snap.interrupts[0].value if snap.interrupts else None


def _payload(tid: str, snap) -> dict:
    vals = snap.values or {}
    # `done` must mean "ran to completion", not "no pending node". A never-planned ticket
    # has an empty checkpoint (no next), which is NOT done — only report done once the
    # graph actually started (has state) AND has no next node.
    started = bool(vals)
    return {
        "ticketId": tid,
        "next": list(snap.next),
        "done": started and not snap.next,
        "current": vals.get("current"),
        "steps": vals.get("steps", []),
        "awaiting": _awaiting(snap),
    }


@router.post("/tickets/{tid}/plan", response_model=LifecycleStateOut)
def start_plan(pid: str, tid: str, body: PlanStartIn, db: Session = Depends(get_session)):
    graph = _build(db, pid, tid, title=body.title)
    cfg = _cfg(tid)
    with _GRAPH_LOCK:
        snap = graph.get_state(cfg)
    awaiting = _awaiting(snap)
    if awaiting and awaiting.get("type") == "plan_approval":
        return _payload(tid, snap)  # already proposed; return the pending plan
    if snap.values:
        # graph already started (mid-execution or done) — re-invoking with a fresh
        # state would reset the checkpoint out of sync with the DB. Return as-is.
        return _payload(tid, snap)

    obj = _objective(db, pid)
    existing = db.get(Node, tid)
    title = body.title or (existing.label if existing else tid)
    # Surface "planning" on an existing (project-init) ticket so the map/board shows the
    # PLAN agent is working — the proposal itself stays synchronous (the modal spinner).
    _set_activity(db, pid, tid, "planning", "계획 수립 중")
    # Do NOT persist the ticket here. The proposed plan lives in the LangGraph checkpoint
    # (thread_id ticket:{tid}); store.approve_plan creates the ticket (and the project's
    # Objective if missing) only on approval. So an abandoned or re-opened propose leaves
    # NO orphan/duplicate ticket on the map (was: a ticket committed per propose call).
    logger.info("start_plan: mode=%s pid=%s tid=%s title=%r", _mode(), pid, tid, title)

    with _GRAPH_LOCK:
        graph.invoke(
            {
                "project_id": pid,
                "ticket_id": tid,
                "repo_dir": _repo_dir(db, pid),
                # use the goal text as the objective when the project has no Objective yet,
                # so the planner + step prompts still receive the goal (not an empty "").
                "objective": obj.label if obj else title,
                "ticket_title": title,
                # re-planning an existing ticket seeds the proposal from its current steps so
                # the plan is revised, not silently replaced with a generic 3-step template.
                "existing_steps": _existing_steps(db, pid, tid),
                "steps": [],
                "current": 0,
                "decisions": [],
            },
            cfg,
        )
        snap = graph.get_state(cfg)
    # Proposal ready — it now awaits the user's approval, not the PLAN agent. Clear the
    # "planning" spinner (set above, visible while the slow real-mode propose blocked) so an
    # abandoned/closed plan modal doesn't leave a perpetual spinner on the ticket.
    _set_activity(db, pid, tid, None)
    return _payload(tid, snap)


@router.post("/tickets/{tid}/plan/approve", response_model=LifecycleStateOut)
def approve_plan(pid: str, tid: str, body: PlanApproveIn, db: Session = Depends(get_session)):
    logger.info("approve_plan: pid=%s tid=%s steps=%d", pid, tid, len(body.steps or []))
    graph = _build(db, pid, tid, title=body.title)
    cfg = _cfg(tid)
    with _GRAPH_LOCK:
        snap = graph.get_state(cfg)
    awaiting = _awaiting(snap)
    if not (awaiting and awaiting.get("type") == "plan_approval"):
        raise HTTPException(409, "no plan awaiting approval; call /plan first")
    # The goal/title was supplied at propose time and lives in the checkpoint; use it (over
    # the usually-absent approve-body title) so the ticket/Objective get the real goal label.
    title = body.title or (snap.values or {}).get("ticket_title")
    resume: dict = {"approve": True}
    if body.steps is not None:
        resume["steps"] = [s.model_dump() for s in body.steps]

    # Execution (step 1 onward) is the slow part. Run it in the background so the request
    # returns at once; the board fills in + step status advances via getGraph polling
    # (data.activity). Sync path (ASV3_ASYNC_EXEC=0 / tests) keeps the original behavior.
    if _async_enabled():
        _invoke_async(pid, tid, title, resume)
        return _payload(tid, snap)  # pre-execution snapshot; steps appear via polling
    if title != body.title:
        graph = _build(db, pid, tid, title=title)  # rebuild so on_steps_approved uses it
    with _GRAPH_LOCK:
        graph.invoke(Command(resume=resume), cfg)
        snap = graph.get_state(cfg)
    return _payload(tid, snap)


def _ticket_done_if_all_steps_done(db: Session, pid: str, tid: str) -> None:
    ticket = db.get(Node, tid)
    if ticket is None:
        return
    steps = [n for n in store.neighbors(db, pid, tid, "out") if n.kind == "step"]
    if steps and all(s.status == "done" for s in steps):
        ticket.status = "done"


def _review_db_direct(db: Session, pid: str, tid: str, sid: str, action: ReviewActionIn) -> None:
    """Apply a review to a step that has NO live LangGraph interrupt — i.e. seeded demo
    steps (the seed only populates the DB graph, never a checkpoint) and steps whose graph
    already ended (e.g. after a takeover). Without this, those gates 409'd and the UI
    failed silently; here the gate is actionable straight on the DB so the demo and the
    post-takeover hand-off both work."""
    node = db.get(Node, sid)
    ticket = db.get(Node, tid)
    if action.kind == "approve":
        if node is not None:
            node.status = "done"
        _ticket_done_if_all_steps_done(db, pid, tid)
    elif action.kind == "takeover":
        if ticket is not None:
            ticket.status = "awaiting_review"
        # leave the step awaiting_review so the human can later mark it done (approve)
    # changes: no executor to re-run here; the step stays awaiting_review (no-op, no error)
    if action.kind == "approve" and ticket is not None and ticket.status == "done":
        _set_activity(db, pid, tid, "done", "완료")
    db.commit()
    if action.kind == "approve" and _all_tickets_done(db, pid):
        promote_project(db, pid, MEMORY)


def _finalize_review(db: Session, pid: str, tid: str, sid: str, action: ReviewActionIn, snap) -> None:
    """Post-invoke DB updates for a live-interrupt review (shared by the sync path and the
    async worker, so both end in the same state)."""
    node = db.get(Node, sid)
    ticket = db.get(Node, tid)
    if action.kind == "approve":
        if node is not None:
            node.status = "done"
        if not snap.next and ticket is not None:
            ticket.status = "done"
            _set_activity(db, pid, tid, "done", "완료")
    elif action.kind == "takeover":
        if ticket is not None:
            ticket.status = "awaiting_review"
        # leave the step awaiting_review so a later approve (DB-direct, graph ended) completes it
    # changes: on_step_committed already reset the step to awaiting_review during the re-run
    db.commit()
    # project complete (this approve finished its last ticket) -> distill Decisions into
    # the personal ~/llm_wiki + index them for cross-project recall.
    if action.kind == "approve" and not snap.next and _all_tickets_done(db, pid):
        promote_project(db, pid, MEMORY)


@router.post("/steps/{sid}/review", response_model=LifecycleStateOut)
def review_step(pid: str, sid: str, action: ReviewActionIn, db: Session = Depends(get_session)):
    logger.info("review_step: pid=%s sid=%s kind=%s", pid, sid, action.kind)
    tid = _ticket_of_step(db, pid, sid)
    graph = _build(db, pid, tid)
    cfg = _cfg(tid)
    with _GRAPH_LOCK:
        snap = graph.get_state(cfg)
    awaiting = _awaiting(snap)
    if not (awaiting and awaiting.get("type") == "review"):
        # No live interrupt: a seeded step, or a step whose graph already ended (takeover).
        # Operate directly on the DB if the step is in a reviewable state — else 409.
        node = db.get(Node, sid)
        if node is None or node.kind != "step" or node.status not in {
            "awaiting_review",
            "blocked",
        }:
            raise HTTPException(409, "no step awaiting review")
        _review_db_direct(db, pid, tid, sid, action)
        return _payload(tid, snap)

    vals = snap.values or {}
    steps = vals.get("steps", [])
    cur = vals.get("current", 0) or 0
    resume = {"kind": action.kind, "comment": action.comment}
    # approve of a non-last step re-enters execute_step (slow); changes always re-runs the
    # current step (slow). takeover and last-step approve are quick (no execution).
    will_execute = action.kind == "changes" or (action.kind == "approve" and cur + 1 < len(steps))

    if _async_enabled() and will_execute:
        node = db.get(Node, sid)
        if action.kind == "approve":
            if node is not None:
                node.status = "done"  # reviewed step done now — don't wait for the next run
            _set_activity(db, pid, tid, "executing", f"step {cur + 2}/{len(steps)}")
        else:  # changes -> the same step re-runs
            if node is not None:
                node.status = "executing"
            _set_activity(db, pid, tid, "executing", f"step {cur + 1}/{len(steps)}")
        db.commit()
        _invoke_async(
            pid, tid, None, resume,
            after=lambda db2, snap2: _finalize_review(db2, pid, tid, sid, action, snap2),
        )
        return _payload(tid, snap)

    # Sync path: takeover, last-step approve, or async disabled (tests).
    with _GRAPH_LOCK:
        graph.invoke(Command(resume=resume), cfg)
        snap = graph.get_state(cfg)
    _finalize_review(db, pid, tid, sid, action, snap)
    return _payload(tid, snap)


@router.get("/tickets/{tid}/state", response_model=LifecycleStateOut)
def ticket_state(pid: str, tid: str, db: Session = Depends(get_session)):
    graph = _build(db, pid, tid)
    with _GRAPH_LOCK:
        snap = graph.get_state(_cfg(tid))
    return _payload(tid, snap)


@router.get("/info", response_model=ProjectInfoOut)
def project_info(pid: str, db: Session = Depends(get_session)):
    """The project's resolved target repo (where its executor commits) + its source."""
    path, source = _resolve_repo_path(db, pid)
    return {"projectId": pid, "repoDir": path, "repoSource": source}


@router.post("/repo", response_model=ProjectInfoOut)
def set_project_repo(pid: str, body: ProjectRepoIn, db: Session = Depends(get_session)):
    """Set (or clear) the project's target repo override (stored on its Objective)."""
    obj = _objective(db, pid)
    if obj is None:
        raise HTTPException(404, "project (objective) not found")
    data = dict(obj.data or {})
    repo = (body.repoDir or "").strip()
    if repo:
        data["repo_dir"] = repo
    else:
        data.pop("repo_dir", None)  # cleared -> falls back to workspace/default
    obj.data = data  # reassign so SQLAlchemy tracks the JSON change
    db.commit()
    path, source = _resolve_repo_path(db, pid)
    return {"projectId": pid, "repoDir": path, "repoSource": source}
