"""CP3 steer — route a human's free-form NL into a fixed graph op and execute it.

`POST /projects/{pid}/steer` records the user's instruction as a channel message, classifies it
via the CP0 `intent-router` engine, and dispatches to one of the core ops (redirect / constrain
/ answer / control), or `clarify` when ambiguous (never guesses). Each op reuses existing
machinery — re-plan/persist, decision nodes + RAG, the review gate, and the CP1 throttle — and
appends a system/decision/clarify message for auditability (which node changed, by whose
instruction). Reads/proposes stay lock-free; the only executor-bearing op (answer) serializes on
the per-project exec lock via `resume_step_review`.
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session, make_checkpointer
from ..graph import store
from ..models import Edge, Node
from ..schemas import SteerIn, SteerOut
from ..services import assistant, channel, governance
from . import lifecycle
from .memory import MEMORY

router = APIRouter(tags=["steer"])
logger = logging.getLogger("asv3.steer")


def _tickets(db: Session, pid: str) -> list[Node]:
    return db.scalars(select(Node).where(Node.project_id == pid, Node.kind == "ticket")).all()


def _steer_context(db: Session, pid: str, body: SteerIn) -> dict:
    """Resolve the steer's scope (which ticket/step) + whether an agent question is pending.
    Explicit UI selection wins; otherwise the currently-active ticket / the blocked step."""
    tickets = _tickets(db, pid)
    active = next((t for t in tickets if t.status in ("executing", "awaiting_review")), None)
    active = active or (tickets[0] if tickets else None)
    ticket_id = body.ticketId or (active.id if active else None)
    # Resolve the pending question (blocked step) DETERMINISTICALLY and scoped to the ticket the
    # user is actually on — an explicit blocked selection wins, else the first blocked step of
    # the resolved ticket (not an arbitrary blocked step from a different ticket).
    if _is_blocked(db, body.stepId):
        blocked_sid = body.stepId
    elif ticket_id:
        blocked_sid = next(
            (s.id for s in _ordered_steps(db, pid, ticket_id) if s.status == "blocked"), None
        )
    else:
        blocked_sid = None
    return {
        "scope": {"ticket": ticket_id, "step": body.stepId},
        "ticket": ticket_id,
        "has_blocked": blocked_sid is not None,
        "blocked_step": blocked_sid,
    }


def _is_blocked(db: Session, sid: str | None) -> bool:
    if not sid:
        return False
    n = db.get(Node, sid)
    return n is not None and n.status == "blocked"


def _ordered_steps(db: Session, pid: str, tid: str) -> list[Node]:
    steps = [n for n in store.neighbors(db, pid, tid, "out") if n.kind == "step"]
    return sorted(steps, key=lambda n: int((re.search(r"-s(\d+)$", n.id) or [0, 0])[1] or 0))


def _clarify(db: Session, pid: str, text: str) -> dict:
    channel.post_message(db, pid, "clarify", text, author="system")
    return {"op": "clarify", "scope": {}, "result": {"clarify": text}}


def _match_ticket(db: Session, pid: str, text: str) -> Node | None:
    """Resolve which ticket an instruction refers to: the ticket whose label shares the MOST
    tokens with the text (case-insensitive), tie-broken by the longest label. So '결제 알림 먼저'
    picks '결제 알림' (2 shared) over '결제 연동' (1 shared) instead of first-token-wins, and
    'prioritize payment' matches 'Payment Gateway' despite the case difference. Returns None
    only when no label shares a token — the caller then falls back to the ambient ticket."""
    tl = text.lower()
    best: Node | None = None
    best_key = (0, 0)  # (shared-token count, label length) — higher wins
    for t in _tickets(db, pid):
        words = [w for w in re.split(r"[\s,]+", t.label) if len(w) >= 2]
        score = sum(1 for w in words if w.lower() in tl)
        if score and (score, len(t.label)) > best_key:
            best, best_key = t, (score, len(t.label))
    return best


def _scope_title(text: str) -> str:
    t = text
    for kw in ("추가해줘", "추가해", "추가", "새 티켓", "새 일감", "도 만들어줘", "도 만들어", "also add", "add ", "scope"):
        t = t.replace(kw, " ")
    t = t.strip().strip(" ,.").rstrip("도을를이가").strip()
    return t or "새 일감"


# ───────────────────────────────── op executors ─────────────────────────────────
def _op_redirect(db: Session, pid: str, text: str, intent: dict, ctx: dict) -> dict:
    tid = (intent.get("scope") or {}).get("ticket") or ctx.get("ticket")
    ticket = db.get(Node, tid) if tid else None
    if ticket is None:
        return _clarify(db, pid, "어느 티켓을 재계획할지 알 수 없어요 — 티켓을 선택하고 다시 지시해 주세요.")
    target = (intent.get("args") or {}).get("target") or text.strip()
    old = [s.label for s in _ordered_steps(db, pid, tid)]
    # Deterministic re-plan reflecting the redirect (open Q#3 v1: replace the plan; abort of a
    # running step is a follow-up). Persist the new steps via store.approve_plan, then...
    new_labels = [f"'{target}'(으)로 방향 전환", f"{target} 반영 재구현", "재검증 테스트"]
    store.approve_plan(db, pid, tid, new_labels, ticket.label)
    # ...keep the DB and the LangGraph checkpoint in sync: reset the ticket to a re-plannable
    # PLANNING state and DELETE the stale checkpoint (old steps + any live review interrupt), so
    # a later review can't resume the ABANDONED plan against the new node ids. The human runs the
    # redirected plan through the normal /plan -> /approve flow (the channel shows the diff).
    ticket.status = "planning"
    for s in _ordered_steps(db, pid, tid):
        s.status = "planning"
    db.commit()
    try:
        make_checkpointer().delete_thread(f"ticket:{tid}")
    except Exception:  # noqa: BLE001 — a checkpoint-reset failure must not strand the redirect
        logger.exception("could not reset checkpoint for %s after redirect", tid)
    channel.post_message(
        db, pid, "system",
        f"redirect → '{ticket.label}' 재계획: [{', '.join(old) or '없음'}] → [{', '.join(new_labels)}] "
        "(승인하면 새 계획으로 진행)",
        refs=[tid], author="system",
    )
    return {"op": "redirect", "scope": {"ticket": tid}, "result": {"ticketId": tid, "steps": new_labels, "old": old}}


def _op_constrain(db: Session, pid: str, text: str, intent: dict, ctx: dict) -> dict:
    tid = (intent.get("scope") or {}).get("ticket") or ctx.get("ticket")
    existing = db.scalars(
        select(Node).where(Node.project_id == pid, Node.kind == "decision")
    ).all()
    n = 1 + sum(1 for x in existing if x.id.startswith(f"constraint:{pid}:"))
    cid = f"constraint:{pid}:{n}"
    db.add(Node(id=cid, project_id=pid, kind="decision", label=text,
                data={"kind": "constraint", "source": "steer"}))
    if tid and db.get(Node, tid) is not None:  # attach to the ticket for map visibility
        db.add(Edge(id=f"constrains:{cid}", project_id=pid, src=tid, dst=cid, kind="decided"))
    db.commit()
    # Propagate to future steps via the EXISTING RAG mechanism (prompt_build recalls decisions).
    MEMORY.index_text(text, {"project_id": pid, "node_id": cid, "kind": "decision"})
    channel.post_message(db, pid, "decision", f"제약 고정: {text}", refs=[cid], author="system")
    return {"op": "constrain", "scope": {"ticket": tid}, "result": {"nodeId": cid}}


def _op_answer(db: Session, pid: str, text: str, intent: dict, ctx: dict) -> dict:
    sid = (intent.get("scope") or {}).get("step") or ctx.get("blocked_step")
    node = db.get(Node, sid) if sid else None
    if node is None or node.status != "blocked":
        return _clarify(db, pid, "지금 답변을 기다리는 막힌 step이 없어요.")
    # Unblock by resuming the step's review as a `changes` re-run with the answer as guidance —
    # reuses the exact review-gate machinery (no new lifecycle).
    lifecycle.resume_step_review(db, pid, sid, "changes", text)
    after = db.get(Node, sid)
    status = after.status if after is not None else None
    if status == "blocked":
        # No live interrupt to resume (e.g. taken-over / seeded step) — the re-run didn't happen,
        # so don't falsely claim resumption.
        return _clarify(db, pid, "이 step은 재실행할 컨텍스트가 없어 답변을 반영하지 못했어요 — 실행을 먼저 재개해 주세요.")
    channel.post_message(
        db, pid, "system", f"답변 반영 → '{node.label}' 재개 (상태: {status})", refs=[sid], author="system"
    )
    return {"op": "answer", "scope": {"step": sid}, "result": {"stepId": sid, "status": status}}


def _op_control(db: Session, pid: str, text: str, intent: dict, ctx: dict) -> dict:
    args = intent.get("args") or {}
    action = args.get("action")
    if action == "throttle":
        level = args.get("level", "per-step")
        governance.set_project_autonomy(db, pid, level)
        summary = f"자율도 → {level}"
    elif action == "pause":
        governance.set_project_autonomy(db, pid, "per-step")  # pause = stop auto-advancing
        summary = "일시정지 (자율도 = 매 step)"
    elif action == "resume":
        # resume CLEARS the project override -> inherit the global default (not a blanket 'auto'
        # downgrade that would silently disable the review gate for a co-pilot baseline).
        governance.set_project_autonomy(db, pid, None)
        summary = f"재개 (자율도 = {governance.resolve_autonomy(db, pid)})"
    else:
        return _clarify(db, pid, "어떤 제어를 원하는지 모르겠어요 (pause / resume / 자율도 변경).")
    channel.post_message(db, pid, "system", f"control → {summary}", author="system")
    return {"op": "control", "scope": {}, "result": {"action": action, "autonomy": governance.resolve_autonomy(db, pid)}}


def _op_reprioritize(db: Session, pid: str, text: str, intent: dict, ctx: dict) -> dict:
    # reprioritize names the target in the TEXT ("동기화 먼저"), so a label match wins over the
    # ambient active ticket; fall back to an explicit selection only if the text names none.
    ticket = _match_ticket(db, pid, text)
    if ticket is None:
        sid_ticket = (intent.get("scope") or {}).get("ticket")
        ticket = db.get(Node, sid_ticket) if sid_ticket else None
    if ticket is None:
        return _clarify(db, pid, "어느 티켓을 우선할지 알 수 없어요 — 티켓 이름을 함께 지시해 주세요.")
    tickets = _tickets(db, pid)
    ticket.data = {**(ticket.data or {}), "order": min(store.ticket_order(t) for t in tickets) - 1}
    db.commit()
    channel.post_message(db, pid, "system", f"reprioritize → '{ticket.label}' 을 맨 앞으로", refs=[ticket.id], author="system")
    return {"op": "reprioritize", "scope": {"ticket": ticket.id}, "result": {"ticketId": ticket.id, "order": store.ticket_order(ticket)}}


def _op_scope(db: Session, pid: str, text: str, intent: dict, ctx: dict) -> dict:
    title = _scope_title(text)
    tid = store.add_ticket(db, pid, title)
    if tid is None:
        return _clarify(db, pid, "프로젝트가 없어 새 티켓을 만들 수 없어요.")
    channel.post_message(db, pid, "system", f"scope → 새 티켓 '{title}' 생성 (계획 대기)", refs=[tid], author="system")
    return {"op": "scope", "scope": {"ticket": tid}, "result": {"ticketId": tid, "title": title}}


def _op_ask(db: Session, pid: str, text: str, intent: dict, ctx: dict) -> dict:
    """Conversational Q&A: answer the user's question grounded in the project context and post
    the reply as an agent message (the channel actually converses, not just routes commands)."""
    reply = assistant.answer(db, pid, text)
    channel.post_message(db, pid, "system", reply, author="agent")
    return {"op": "ask", "scope": {}, "result": {"answer": reply}}


_DISPATCH = {
    "redirect": _op_redirect,
    "constrain": _op_constrain,
    "reprioritize": _op_reprioritize,
    "scope": _op_scope,
    "answer": _op_answer,
    "control": _op_control,
    "ask": _op_ask,
}


@router.post("/projects/{pid}/steer", response_model=SteerOut)
def steer(pid: str, body: SteerIn, db: Session = Depends(get_session)):
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(400, "empty steer")
    logger.info("steer[%s]: %r", pid, text[:100])
    channel.post_message(db, pid, "steer", text, author="user")  # record the human instruction
    ctx = _steer_context(db, pid, body)
    intent_router = governance.make_intent_router(governance.resolve_engine(db, "intent-router", pid))
    intent = intent_router.classify(text, ctx)
    op = intent.get("op", "clarify")
    result = _DISPATCH.get(op, lambda *_: _clarify(
        db, pid, "무엇을 원하는지 모르겠어요 — 예: 'use Stripe', 'auth 건드리지 마', 'pause'."
    ))(db, pid, text, intent, ctx)
    return result
