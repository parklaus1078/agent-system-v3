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
from ..services.promotion import promote_project
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
        on_step_committed=on_step_committed,
        build_prompt=build_prompt,
    )


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
            # re-planning an existing ticket seeds the proposal from its current steps so
            # the plan is revised, not silently replaced with a generic 3-step template.
            "existing_steps": _existing_steps(db, pid, tid),
            "steps": [],
            "current": 0,
            "decisions": [],
        },
        cfg,
    )
    return _payload(tid, graph.get_state(cfg))


@router.post("/tickets/{tid}/plan/approve", response_model=LifecycleStateOut)
def approve_plan(pid: str, tid: str, body: PlanApproveIn, db: Session = Depends(get_session)):
    graph = _build(db, pid, tid, title=body.title)
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
    db.commit()
    if action.kind == "approve" and _all_tickets_done(db, pid):
        promote_project(db, pid, MEMORY)


@router.post("/steps/{sid}/review", response_model=LifecycleStateOut)
def review_step(pid: str, sid: str, action: ReviewActionIn, db: Session = Depends(get_session)):
    tid = _ticket_of_step(db, pid, sid)
    graph = _build(db, pid, tid)
    cfg = _cfg(tid)
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
        return _payload(tid, graph.get_state(cfg))

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
        # leave the step awaiting_review so a later approve (now via the DB-direct path,
        # since the graph has ended) can complete it — no dead end after takeover.
    # changes: the step re-executes, on_step_committed resets it to awaiting_review
    db.commit()

    # project complete (this approve finished its last ticket) -> distill its Decisions
    # into the personal ~/llm_wiki + index them for cross-project recall.
    if action.kind == "approve" and not snap.next and _all_tickets_done(db, pid):
        promote_project(db, pid, MEMORY)

    return _payload(tid, snap)


@router.get("/tickets/{tid}/state", response_model=LifecycleStateOut)
def ticket_state(pid: str, tid: str, db: Session = Depends(get_session)):
    graph = _build(db, pid, tid)
    return _payload(tid, graph.get_state(_cfg(tid)))
