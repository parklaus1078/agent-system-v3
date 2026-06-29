from __future__ import annotations

import logging
import os
import re

from fastapi import APIRouter, Depends, HTTPException
from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session, make_checkpointer
from ..graph import store
from ..graph.diff_ingest import apply_step_diff
from ..git.repo import commit_all, diff_of_commit
from ..models import Node, Edge
from ..schemas import LifecycleStateOut, PlanApproveIn, PlanStartIn, ReviewActionIn
from ..schemas_plan import StepSpec
from ..services.executor import CliExecutor, SimulatedExecutor
from ..services.lifecycle_graph import build_graph
from ..services.planner import CliPlanner, LangChainPlanner, SimulatedPlanner
from ..services.prompt_build import build_step_prompt, step_rag_context
from .memory import MEMORY

router = APIRouter(prefix="/projects/{pid}", tags=["lifecycle"])
logger = logging.getLogger("asv3.lifecycle")

_REVIEW_STATUS = {"approve": "done", "changes": "executing", "takeover": "awaiting_review"}


def _mode() -> str:
    return os.environ.get("ASV3_AGENT_MODE", "simulated")


def _repo_dir() -> str:
    return os.environ.get("ASV3_TARGET_REPO_DIR", ".")


def _cfg(tid: str) -> dict:
    return {"configurable": {"thread_id": f"ticket:{tid}"}}


def _ticket_of_step(sid: str) -> str:
    return re.sub(r"-s\d+$", "", sid)


def _sim_write(repo_dir: str) -> None:
    """Simulated executor edit: add a new file per step so every step yields a real,
    non-empty commit (which diff_of_commit + apply_step_diff then ingest)."""
    gen = os.path.join(repo_dir, "generated")
    os.makedirs(gen, exist_ok=True)
    n = len([f for f in os.listdir(gen) if f.endswith(".ts")]) + 1
    with open(os.path.join(gen, f"step_{n}.ts"), "w", encoding="utf-8") as f:
        f.write(f"export const step{n} = true;\n")


def _objective(db: Session, pid: str) -> Node | None:
    return db.scalars(
        select(Node).where(Node.project_id == pid, Node.kind == "objective")
    ).first()


def _build(db: Session, pid: str, tid: str, title: str | None = None):
    repo = _repo_dir()

    def on_steps_approved(steps: list[dict]) -> None:
        store.approve_plan(db, pid, tid, [s["label"] for s in steps], title)

    def on_step_committed(i: int, sha: str | None, summary: str, decision: str | None) -> None:
        sid = f"{tid}-s{i + 1}"
        if sha:  # None => executor made no edits; still gate the step, just no diff
            try:
                apply_step_diff(db, pid, sid, sha, diff_of_commit(repo, sha))
            except Exception:  # git/diff failure must not strand the step un-gated
                db.rollback()  # discard any partial ingest; the status update below still lands
                logger.exception("diff ingest failed for step %s (commit %s)", sid, sha)
        node = db.get(Node, sid)
        if node is not None:
            node.status = "awaiting_review"
            node.data = {**(node.data or {}), "summary": summary}
        if decision:
            did = f"dec:{sid}"
            if db.get(Node, did) is None:
                db.add(Node(id=did, project_id=pid, kind="decision", label=decision))
                db.add(
                    Edge(id=f"decided:{sid}", project_id=pid, src=sid, dst=did, kind="decided")
                )
                # index the decision text so later steps can recall it via RAG
                MEMORY.index_text(
                    decision, {"project_id": pid, "node_id": did, "kind": "decision"}
                )
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
        executor = SimulatedExecutor(_sim_write)

    return build_graph(
        planner=planner,
        executor=executor,
        checkpointer=make_checkpointer(),
        commit_fn=commit_all,
        on_steps_approved=on_steps_approved,
        on_step_committed=on_step_committed,
        build_prompt=build_prompt,
    )


def _awaiting(snap):
    return snap.interrupts[0].value if snap.interrupts else None


def _payload(tid: str, snap) -> dict:
    vals = snap.values or {}
    return {
        "ticketId": tid,
        "next": list(snap.next),
        "done": not snap.next,
        "current": vals.get("current"),
        "steps": vals.get("steps", []),
        "awaiting": _awaiting(snap),
    }


@router.post("/tickets/{tid}/plan", response_model=LifecycleStateOut)
def start_plan(pid: str, tid: str, body: PlanStartIn, db: Session = Depends(get_session)):
    graph = _build(db, pid, tid, title=body.title)
    cfg = _cfg(tid)
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
    if existing is None:
        db.add(
            Node(id=tid, project_id=pid, kind="ticket", label=title, status="planning", data={})
        )
        if obj is not None:
            db.add(
                Edge(id=f"has-{obj.id}-{tid}", project_id=pid, src=obj.id, dst=tid, kind="has")
            )
        db.commit()

    graph.invoke(
        {
            "project_id": pid,
            "ticket_id": tid,
            "repo_dir": _repo_dir(),
            "objective": obj.label if obj else "",
            "ticket_title": title,
            "steps": [],
            "current": 0,
            "decisions": [],
        },
        cfg,
    )
    return _payload(tid, graph.get_state(cfg))


@router.post("/tickets/{tid}/plan/approve", response_model=LifecycleStateOut)
def approve_plan(pid: str, tid: str, body: PlanApproveIn, db: Session = Depends(get_session)):
    graph = _build(db, pid, tid)
    cfg = _cfg(tid)
    snap = graph.get_state(cfg)
    awaiting = _awaiting(snap)
    if not (awaiting and awaiting.get("type") == "plan_approval"):
        raise HTTPException(409, "no plan awaiting approval; call /plan first")
    resume = {"approve": True}
    if body.steps is not None:
        resume["steps"] = [s.model_dump() for s in body.steps]
    graph.invoke(Command(resume=resume), cfg)
    return _payload(tid, graph.get_state(cfg))


@router.post("/steps/{sid}/review", response_model=LifecycleStateOut)
def review_step(pid: str, sid: str, action: ReviewActionIn, db: Session = Depends(get_session)):
    tid = _ticket_of_step(sid)
    graph = _build(db, pid, tid)
    cfg = _cfg(tid)
    snap = graph.get_state(cfg)
    awaiting = _awaiting(snap)
    if not (awaiting and awaiting.get("type") == "review"):
        raise HTTPException(409, "no step awaiting review")
    graph.invoke(Command(resume={"kind": action.kind, "comment": action.comment}), cfg)
    snap = graph.get_state(cfg)

    node = db.get(Node, sid)
    ticket = db.get(Node, tid)
    if action.kind == "approve":
        if node is not None:
            node.status = "done"
        if not snap.next and ticket is not None:
            ticket.status = "done"
    elif action.kind == "takeover":
        if ticket is not None:
            ticket.status = "awaiting_review"
    # changes: the step re-executes, on_step_committed resets it to awaiting_review
    db.commit()
    return _payload(tid, snap)


@router.get("/tickets/{tid}/state", response_model=LifecycleStateOut)
def ticket_state(pid: str, tid: str, db: Session = Depends(get_session)):
    graph = _build(db, pid, tid)
    return _payload(tid, graph.get_state(_cfg(tid)))
