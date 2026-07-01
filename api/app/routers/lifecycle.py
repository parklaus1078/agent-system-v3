from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import SessionLocal, get_session, make_checkpointer
from ..graph import store
from ..graph.diff_ingest import apply_step_diff, parse_diff
from ..git.repo import commit_all, diff_since, head_sha
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
from ..services import channel, governance, message_gen
from ..services.lifecycle_graph import build_graph
from ..services.prompt_build import build_step_prompt, step_rag_context
from ..services.promotion import promote_project
from .memory import MEMORY

router = APIRouter(prefix="/projects/{pid}", tags=["lifecycle"])
logger = logging.getLogger("asv3.lifecycle")

_REVIEW_STATUS = {"approve": "done", "changes": "executing", "takeover": "awaiting_review"}

# Per-PROJECT execution lock. Held ONLY around the EXECUTION-bearing graph invoke (the slow
# `claude -p` step run) to serialize execution within a project — two tickets in the same
# project must not run their executors / `git commit` against the shared per-project repo at
# once. It is deliberately NOT held on the read/propose/get_state paths, so PROPOSING a plan
# for another ticket works while one ticket is mid-execution (the reported bug). Checkpoint
# safety on those lock-free paths comes from PostgresSaver's own internal lock (postgres) and
# per-thread_id isolation (memory: distinct `ticket:{tid}` keys, single user). Different
# projects use different locks (+ different repos) so they execute concurrently.
_EXEC_LOCKS: defaultdict[str, threading.Lock] = defaultdict(threading.Lock)


def _exec_lock(pid: str) -> threading.Lock:
    return _EXEC_LOCKS[pid]  # defaultdict access is atomic under the GIL
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


def _remove_repo_dir(path: str) -> bool:
    """Delete a project's repo directory (the actual files) — GUARDED: only a real existing
    directory that is not a filesystem root, the home dir, the cwd, or an ancestor of either.
    Returns True iff it was removed. Never raises — a failed rm must not strand the DB delete."""
    try:
        p = Path(path).resolve()
    except Exception:  # noqa: BLE001
        return False
    if not p.is_dir():
        return False
    cwd, home = Path.cwd().resolve(), Path.home().resolve()
    if p == p.parent or p in (cwd, home) or p in cwd.parents or p in home.parents:
        logger.warning("refusing to delete unsafe repo dir %s", p)
        return False
    shutil.rmtree(p, ignore_errors=True)
    return not p.exists()


def _cfg(tid: str) -> dict:
    return {"configurable": {"thread_id": f"ticket:{tid}"}}


def _gen_msg(db: Session, pid: str, type: str, **ctx) -> str:
    """Channel message text: the deterministic template, then naturalized via the resolved
    `agent-message-gen` engine (simulated / error -> the template unchanged, so tests stay
    deterministic and message styling never breaks the lifecycle)."""
    base = channel.gen_text(type, **ctx)
    return message_gen.naturalize(governance.resolve_engine(db, "agent-message-gen", pid), base)


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


def _resolve_governance(db: Session, pid: str, tid: str | None = None) -> dict:
    """Resolve the CP0 governance config (rules + per-point engines) for a project in ONE
    place. Done in the REQUEST thread and handed to the background worker so the worker's
    hot path issues no extra DB reads racing the UI's getGraph poll (the in-memory-SQLite
    StaticPool shares a single connection across threads)."""
    cfg = governance.resolve_all(db, pid, ("ticket-planner", "executor"))
    cfg["autonomy"] = governance.resolve_autonomy(db, pid, tid)  # CP1 + CP4 per-ticket throttle
    return cfg


def _ingest_step_diff(
    db: Session, pid: str, sid: str, repo: str, pre: str | None
) -> tuple[str | None, list[dict] | None]:
    """Capture a step's diff by HEAD MOVEMENT (pre..HEAD), not by commit_all's return — a real
    CLI executor may commit its OWN edits, leaving commit_all a clean tree while HEAD advanced.
    Returns (head, diff_blobs): diff_blobs is None when HEAD didn't move (no fresh capture, so
    the caller keeps the stored diff — a no-op re-run must NOT erase it), [] when the ingest
    failed, else the per-file patches (also persisted as code_region/test nodes)."""
    head = head_sha(repo)
    if head is None or head == pre:
        return head, None
    try:
        diff_text = diff_since(repo, pre)
        apply_step_diff(db, pid, sid, head, diff_text)
        return head, [{"path": tf.path, "patch": tf.patch} for tf in parse_diff(diff_text)]
    except Exception:  # noqa: BLE001 — a git/diff failure must not strand the step un-gated
        db.rollback()  # discard any partial ingest; the caller's status update still lands
        logger.exception("diff ingest failed for step %s (%s..%s)", sid, (pre or "-")[:8], (head or "-")[:8])
        return head, []


def _upsert_step_decision(db: Session, pid: str, sid: str, decision: str) -> bool:
    """Create or update the step's decision node (+ `decided` edge) and (re)index it into RAG so
    later steps recall it. Returns True when the decision is NEW or CHANGED — so the caller posts
    a channel message once, not on every re-run."""
    did = f"dec:{sid}"
    existing = db.get(Node, did)
    is_new = False
    if existing is None:
        db.add(Node(id=did, project_id=pid, kind="decision", label=decision))
        db.add(Edge(id=f"decided:{sid}", project_id=pid, src=sid, dst=did, kind="decided"))
        is_new = True
    elif existing.label != decision:
        existing.label = decision  # a 'changes' re-run can produce a new decision
        is_new = True
    # ALWAYS re-index the latest decision so later steps recall it via RAG (even on a re-run)
    MEMORY.index_text(decision, {"project_id": pid, "node_id": did, "kind": "decision"})
    return is_new


def _build(db: Session, pid: str, tid: str, title: str | None = None, *, gov: dict | None = None):
    _pre_sha: dict[int, str | None] = {}  # HEAD before each step ran (for robust diff capture)

    def on_steps_approved(steps: list[dict]) -> None:
        store.approve_plan(db, pid, tid, [s["label"] for s in steps], title)
        # execution begins next — surface it immediately so the board isn't a frozen blank.
        _set_activity(db, pid, tid, "executing", f"step 1/{len(steps)}")

    def on_step_start(i: int, total: int) -> None:
        # Move the step node itself to `executing` (not just the ticket activity) so a running
        # step leaves the PLANNED column for EXECUTING — otherwise it sat at `planning` the
        # whole run and looked frozen. Sole call-point for every step run (initial/next/changes).
        node = db.get(Node, f"{tid}-s{i + 1}")
        if node is not None:
            node.status = "executing"
        # Snapshot HEAD BEFORE the executor runs, so on_step_committed can diff pre..HEAD and
        # capture the step's change no matter who commits it (executor self-commit or commit_all).
        _pre_sha[i] = head_sha(_repo_dir(db, pid))
        _set_activity(db, pid, tid, "executing", f"step {i + 1}/{total}")

    def on_step_committed(
        i: int, sha: str | None, summary: str, decision: str | None, ok: bool = True
    ) -> None:
        sid = f"{tid}-s{i + 1}"
        # diff_blobs=None -> no fresh capture this run; keep the stored diff (see _ingest_step_diff)
        head, diff_blobs = _ingest_step_diff(db, pid, sid, _repo_dir(db, pid), _pre_sha.get(i))
        node = db.get(Node, sid)
        step_label = node.label if node is not None else sid
        if node is not None:
            # a failed/no-op executor must NOT masquerade as a clean awaiting_review gate
            node.status = "awaiting_review" if ok else "blocked"
            data = {**(node.data or {}), "summary": summary, "ok": ok}
            if diff_blobs is not None:  # only (re)write the diff when we actually captured one
                data["diff"] = diff_blobs
            node.data = data
        total = _total_steps(db, pid, tid) or (i + 1)
        _set_activity(
            db, pid, tid,
            "awaiting_review" if ok else "blocked",
            f"step {i + 1}/{total} {'리뷰 대기' if ok else '실패'}",
        )
        logger.info(
            "step committed: %s ok=%s head=%s files=%s", sid, ok, (head or "-")[:8],
            "keep" if diff_blobs is None else len(diff_blobs),
        )
        # only a NEW/CHANGED decision posts a channel message below (no re-run spam)
        dec_is_new = _upsert_step_decision(db, pid, sid, decision) if decision else False
        db.commit()
        # CP2 channel: surface a failed step + any newly-emerged decision as typed messages.
        if not ok:
            channel.post_message(
                db, pid, "blocked",
                _gen_msg(db, pid, "blocked", step=step_label, summary=summary), refs=[sid],
            )
        if decision and dec_is_new:
            channel.post_message(
                db, pid, "decision",
                _gen_msg(db, pid, "decision", decision=decision), refs=[f"dec:{sid}"],
            )

    # CP0 governance: rules injected into the prompts, engine chosen by the routing table
    # (project override > global > env default) — replaces the old in-line env branching.
    # Resolve once (reused if pre-resolved by the request thread, see _resolve_governance).
    gov = gov or _resolve_governance(db, pid, tid)
    rules = gov["rules"]

    def build_prompt(state, step) -> str:
        spec = StepSpec(**step)
        rag = step_rag_context(MEMORY, state.get("objective", ""), spec)
        return build_step_prompt(
            db, pid, tid, spec, rag_context=rag, coding_rules=rules["coding"],
            reviewer_note=state.get("review_comment", ""),  # CP3: guide a changes/answer re-run
        )

    planner = governance.make_planner(
        gov["engines"]["ticket-planner"], planning_rules=rules["planning"]
    )
    executor = governance.make_executor(
        gov["engines"]["executor"],
        sim_write=lambda repo_dir: _sim_write(repo_dir, tid),
    )

    return build_graph(
        planner=planner,
        executor=executor,
        checkpointer=make_checkpointer(),
        commit_fn=commit_all,
        on_steps_approved=on_steps_approved,
        on_step_start=on_step_start,
        on_step_committed=on_step_committed,
        build_prompt=build_prompt,
        autonomy=gov["autonomy"],  # CP1 throttle: per-step gate vs auto/co-pilot self-advance
    )


def _invoke_async(
    pid: str, tid: str, title: str | None, resume: dict, after=None, *, gov: dict | None = None
) -> None:
    """Run a (possibly long) graph resume in a background daemon thread so the HTTP request
    returns immediately. Uses its OWN DB session (sessions aren't thread-safe) and serializes
    EXECUTION per project behind _exec_lock(pid) (so same-project executors don't race on the
    shared repo). `after(db2)` runs post-invoke (e.g. mark the ticket done / promote).
    `gov` is the governance config resolved on the request thread (see _resolve_governance)."""

    def worker() -> None:
        db2 = SessionLocal()
        try:
            graph = _build(db2, pid, tid, title=title, gov=gov)
            with _exec_lock(pid):
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


def _initial_plan_state(db: Session, pid: str, tid: str, objective_label: str, title: str) -> dict:
    """The fresh TicketState for a propose invoke. The goal text stands in as the objective when
    the project has no Objective yet (so the planner still gets it), and re-planning seeds from
    the ticket's current steps so the plan is revised, not replaced with a generic template."""
    return {
        "project_id": pid,
        "ticket_id": tid,
        "repo_dir": _repo_dir(db, pid),
        "objective": objective_label or title,
        "ticket_title": title,
        "existing_steps": _existing_steps(db, pid, tid),
        "steps": [],
        "current": 0,
        "decisions": [],
    }


@router.post("/tickets/{tid}/plan", response_model=LifecycleStateOut)
def start_plan(pid: str, tid: str, body: PlanStartIn, db: Session = Depends(get_session)):
    graph = _build(db, pid, tid, title=body.title)
    cfg = _cfg(tid)
    snap = graph.get_state(cfg)  # read path: lock-free (see _exec_lock)
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

    # Propose runs LOCK-FREE (no execution lock) so a plan can be proposed for one ticket
    # while another is mid-execution. It only plans + writes its own checkpoint; it never
    # touches the shared repo, so it can't race an executing step.
    graph.invoke(_initial_plan_state(db, pid, tid, obj.label if obj else "", title), cfg)
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
    snap = graph.get_state(cfg)  # read path: lock-free (see _exec_lock)
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
        gov = _resolve_governance(db, pid, tid)
        # End the request session's (read-only) transaction before the worker starts, so
        # closing this session can't race the worker's writes on the shared in-memory
        # connection (sqlite "API misuse"). See _resolve_governance / the review path.
        db.commit()
        # auto/co-pilot run past the first step with no human gate, so the worker reconciles
        # the auto-advanced steps + ticket completion when its run ends (no-op for per-step).
        # Always emit a `review` channel message if the run stopped at a review gate (CP2).
        autonomy = gov["autonomy"]

        def _after(db2, snap2):
            if autonomy != "per-step":
                _finalize_run(db2, pid, tid, snap2)
            _emit_review_message(db2, pid, tid, snap2)

        _invoke_async(pid, tid, title, resume, gov=gov, after=_after)
        return _payload(tid, snap)  # pre-execution snapshot; steps appear via polling
    # Sync path (tests / async off): the graph (already throttle-injected by _build) runs
    # in-request. In auto/co-pilot it advances through several steps, so reconcile completion.
    if title != body.title:
        graph = _build(db, pid, tid, title=title)  # rebuild so on_steps_approved uses the title
    with _exec_lock(pid):  # execution-bearing: serialize per project (shared repo)
        graph.invoke(Command(resume=resume), cfg)
        snap = graph.get_state(cfg)
    if governance.resolve_autonomy(db, pid, tid) != "per-step":
        _finalize_run(db, pid, tid, snap)
    _emit_review_message(db, pid, tid, snap)  # CP2: review message if it stopped at a gate
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


def _ordered_steps(db: Session, pid: str, tid: str) -> list[Node]:
    """A ticket's step nodes in execution order (by the numeric `-s{n}` suffix)."""
    steps = [n for n in store.neighbors(db, pid, tid, "out") if n.kind == "step"]
    return sorted(steps, key=lambda n: int((re.search(r"-s(\d+)$", n.id) or [0, 0])[1] or 0))


def _finalize_run(db: Session, pid: str, tid: str, snap, action_kind: str = "approve") -> None:
    """CP1: reconcile the DB after an auto/co-pilot run, where the graph auto-advanced
    through steps with no per-step human gate. Marks every step the run advanced PAST
    (index < `current`, still awaiting_review/executing) as done; on takeover parks the
    ticket; when the run reached END with all steps done, completes + promotes the ticket.
    A no-op for per-step (current never runs ahead). Mirrors _finalize_review's end state."""
    cur = (snap.values or {}).get("current", 0) or 0
    steps = _ordered_steps(db, pid, tid)
    # An `approve` that advanced past a step completes it regardless of prior status — incl. a
    # `blocked` step the human just accepted-as-is (in auto/co-pilot the run can't advance past
    # a blocked step without a human approve, since a failure forces a stop). This matches the
    # other approve handlers (_finalize_review / _review_db_direct mark an approved step done
    # unconditionally); without "blocked" here that approve would be silently lost.
    advanced = ("awaiting_review", "executing", "blocked") if action_kind == "approve" else ("awaiting_review", "executing")
    for i, s in enumerate(steps):
        if i < cur and s.status in advanced:
            s.status = "done"
    ticket = db.get(Node, tid)
    if action_kind == "takeover" and ticket is not None:
        ticket.status = "awaiting_review"
    elif not snap.next and ticket is not None and steps and all(s.status == "done" for s in steps):
        ticket.status = "done"
        _set_activity(db, pid, tid, "done", "완료")
    db.commit()
    if action_kind != "takeover" and not snap.next and _all_tickets_done(db, pid):
        promote_project(db, pid, MEMORY)


def _emit_review_message(db: Session, pid: str, tid: str, snap) -> None:
    """CP2: when the run STOPS at a review gate for a (non-blocked) step, post a `review`
    channel message — the human's approve/changes/takeover on it is the existing review action.
    A blocked step is already covered by its `blocked` message, so it's skipped here. No-op when
    the run did not stop at a review gate (e.g. auto ran straight to END)."""
    awaiting = _awaiting(snap)
    if not (awaiting and awaiting.get("type") == "review"):
        return
    cur = (snap.values or {}).get("current", 0) or 0
    sid = f"{tid}-s{cur + 1}"
    node = db.get(Node, sid)
    if node is None or node.status != "awaiting_review":
        return  # blocked / unexpected -> covered elsewhere
    summary = (node.data or {}).get("summary", "") if node.data else ""
    # Called exactly once per gate transition (one invoke -> one emit), so a `changes` re-run
    # re-gates -> posts a FRESH review message. The channel is a conversation log; the UI marks
    # only the latest review-per-step actionable.
    channel.post_message(db, pid, "review", _gen_msg(db, pid, "review", step=node.label, summary=summary), refs=[sid])


def _prewrite_review_status(db: Session, pid: str, tid: str, sid: str, kind: str, cur: int, total: int) -> None:
    """Optimistically advance step statuses BEFORE spawning the async worker, so the board
    doesn't flicker back to PLANNED between the request returning and the worker running.
    `approve` -> this step done + the next executing; `changes` -> this step re-executing."""
    node = db.get(Node, sid)
    if kind == "approve":
        if node is not None:
            node.status = "done"  # reviewed step done now — don't wait for the next run
        nxt = db.get(Node, f"{tid}-s{cur + 2}")  # next step -> executing now (no PLANNED flicker)
        if nxt is not None:
            nxt.status = "executing"
        _set_activity(db, pid, tid, "executing", f"step {cur + 2}/{total}")
    else:  # changes -> the same step re-runs
        if node is not None:
            node.status = "executing"
        _set_activity(db, pid, tid, "executing", f"step {cur + 1}/{total}")


def _finalize_step_review(
    db: Session, pid: str, tid: str, sid: str, action: ReviewActionIn, snap, autonomy: str
) -> None:
    """Pick the right post-invoke reconciliation for a step review: per-step keeps today's
    single-step finalize; auto/co-pilot use the multi-step run reconciler (a human review of a
    co-pilot/auto stop resumes a run that may auto-advance several more steps)."""
    if autonomy == "per-step":
        _finalize_review(db, pid, tid, sid, action, snap)
    else:
        _finalize_run(db, pid, tid, snap, action.kind)


@router.post("/steps/{sid}/review", response_model=LifecycleStateOut)
def review_step(pid: str, sid: str, action: ReviewActionIn, db: Session = Depends(get_session)):
    logger.info("review_step: pid=%s sid=%s kind=%s", pid, sid, action.kind)
    tid = _ticket_of_step(db, pid, sid)
    graph = _build(db, pid, tid)
    cfg = _cfg(tid)
    snap = graph.get_state(cfg)  # read path: lock-free (see _exec_lock)
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
        # Resolve governance BEFORE the commit so the read + the status writes share one
        # transaction that we then close — leaving NO open request-session transaction on the
        # shared in-memory connection while the background worker writes (else the eventual
        # session close races the worker -> sqlite "API misuse"). See _resolve_governance.
        gov = _resolve_governance(db, pid, tid)
        _prewrite_review_status(db, pid, tid, sid, action.kind, cur, len(steps))
        db.commit()
        autonomy = gov["autonomy"]

        def _after(db2, snap2):
            _finalize_step_review(db2, pid, tid, sid, action, snap2, autonomy)
            _emit_review_message(db2, pid, tid, snap2)  # CP2: review msg if it re-gated

        _invoke_async(pid, tid, None, resume, after=_after, gov=gov)
        return _payload(tid, snap)

    # Sync path: takeover, last-step approve, or async disabled (tests). May execute a step
    # (changes / approve-of-non-last when async is off), so serialize per project. In
    # auto/co-pilot a resumed run can auto-advance several more steps (see _finalize_step_review).
    with _exec_lock(pid):
        graph.invoke(Command(resume=resume), cfg)
        snap = graph.get_state(cfg)
    _finalize_step_review(db, pid, tid, sid, action, snap, governance.resolve_autonomy(db, pid, tid))
    _emit_review_message(db, pid, tid, snap)  # CP2: review message if it stopped at a new gate
    return _payload(tid, snap)


def resume_step_review(db: Session, pid: str, sid: str, kind: str, comment: str | None = None):
    """Reusable SYNC review-gate resume — the shared core of `review_step`, exposed for the CP3
    `answer` steer op (answering a blocked step re-runs it via `changes`). Resumes the step's
    graph with the action and reconciles + emits, exactly like review_step's sync path; if there
    is no live interrupt (a DB-direct/seeded step) it applies the review straight on the DB."""
    tid = _ticket_of_step(db, pid, sid)
    action = ReviewActionIn(kind=kind, comment=comment)
    graph = _build(db, pid, tid)
    cfg = _cfg(tid)
    snap = graph.get_state(cfg)  # read path: lock-free
    awaiting = _awaiting(snap)
    if not (awaiting and awaiting.get("type") == "review"):
        _review_db_direct(db, pid, tid, sid, action)
        return snap
    with _exec_lock(pid):  # execution-bearing (a `changes` re-run) — serialize per project
        graph.invoke(Command(resume={"kind": kind, "comment": comment}), cfg)
        snap = graph.get_state(cfg)
    _finalize_step_review(db, pid, tid, sid, action, snap, governance.resolve_autonomy(db, pid, tid))
    _emit_review_message(db, pid, tid, snap)
    return snap


@router.get("/tickets/{tid}/state", response_model=LifecycleStateOut)
def ticket_state(pid: str, tid: str, db: Session = Depends(get_session)):
    graph = _build(db, pid, tid)
    snap = graph.get_state(_cfg(tid))  # read path: lock-free (see _exec_lock)
    return _payload(tid, snap)


@router.get("/info", response_model=ProjectInfoOut)
def project_info(pid: str, db: Session = Depends(get_session)):
    """The project's resolved target repo (where its executor commits) + its source."""
    path, source = _resolve_repo_path(db, pid)
    return {"projectId": pid, "repoDir": path, "repoSource": source}


@router.delete("")
def delete_project(pid: str, delete_directory: bool = False, db: Session = Depends(get_session)):
    """Delete a project: all its mapping data (nodes/edges/messages) + each ticket's LangGraph
    checkpoint thread. With `?delete_directory=true`, ALSO remove the project's target repo
    directory (the actual files the executor committed). 404 if the project doesn't exist."""
    # Resolve the repo path BEFORE the Objective (which carries the override) is deleted.
    repo_path, _ = _resolve_repo_path(db, pid)
    result = store.delete_project(db, pid)
    if result is None:
        raise HTTPException(404, "project not found")
    cp = make_checkpointer()
    for tid in result["ticketIds"]:
        try:
            cp.delete_thread(f"ticket:{tid}")
        except Exception:  # noqa: BLE001 — a missing thread / backend hiccup must not fail the delete
            logger.exception("could not delete checkpoint for ticket %s", tid)
    removed = _remove_repo_dir(repo_path) if delete_directory else False
    logger.info("delete_project pid=%s dir=%s removed=%s", pid, delete_directory, removed)
    return {
        "projectId": pid,
        "nodes": result["nodes"],
        "edges": result["edges"],
        "messages": result["messages"],
        "directoryRemoved": removed,
        "repoDir": repo_path,
    }


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
