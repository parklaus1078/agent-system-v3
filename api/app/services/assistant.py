"""Conversational Q&A for the channel (`ask` op) — answer a human's question grounded in the
project's OWN context (objective, tickets + status, decisions). Uses the agent-message-gen
engine (the 'agent speaks' governance point); simulated / any error returns a deterministic
status summary, so the channel always says something useful even offline."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Node
from . import governance

logger = logging.getLogger("asv3.assistant")


def _nodes(db: Session, pid: str, kind: str) -> list[Node]:
    return list(db.scalars(select(Node).where(Node.project_id == pid, Node.kind == kind)).all())


def status_summary(db: Session, pid: str) -> str:
    """A deterministic one-line project status (the simulated/offline answer)."""
    tickets = _nodes(db, pid, "ticket")
    steps = _nodes(db, pid, "step")
    awaiting = sum(1 for s in steps if s.status == "awaiting_review")
    blocked = sum(1 for s in steps if s.status == "blocked")
    by_status: dict[str, int] = {}
    for t in tickets:
        by_status[t.status or "planning"] = by_status.get(t.status or "planning", 0) + 1
    parts = ", ".join(f"{k} {v}" for k, v in by_status.items()) or "없음"
    tail = f", 리뷰 대기 {awaiting}" if awaiting else ""
    tail += f", 막힘 {blocked}" if blocked else ""
    return f"현재 티켓 {len(tickets)}개 ({parts}), step {len(steps)}개{tail}."


def _context(db: Session, pid: str) -> str:
    obj = _nodes(db, pid, "objective")
    lines: list[str] = []
    if obj:
        lines.append(f"목표: {obj[0].label}")
        desc = (obj[0].data or {}).get("description")
        if desc:
            lines.append(f"설명: {desc}")
    tickets = _nodes(db, pid, "ticket")
    if tickets:
        lines.append("티켓:")
        lines += [f"- {t.label} [{t.status or 'planning'}]" for t in tickets]
    decisions = _nodes(db, pid, "decision")
    if decisions:
        lines.append("결정/제약:")
        lines += [f"- {d.label}" for d in decisions[:8]]
    return "\n".join(lines)


def answer(db: Session, pid: str, question: str) -> str:
    """Answer the user's question about the project. LLM (agent-message-gen engine) grounded in
    the project context; deterministic status summary when simulated or on any failure."""
    engine = governance.resolve_engine(db, "agent-message-gen", pid)
    transport = engine.get("transport")
    if not transport or transport == "simulated":
        return (
            status_summary(db, pid)
            + " — 자세한 대화형 답변을 원하면 거버넌스에서 agent-message-gen을 LLM transport로 설정하세요."
        )
    model = engine.get("model") or "claude-opus-4-8"
    prompt = (
        "You are the project's assistant inside a dev control tower. Answer the user's question "
        "in concise, friendly Korean, grounded ONLY in the project context below. If the answer "
        "is not in the context, say so briefly. Do not invent tickets or facts.\n\n"
        f"## Project context\n{_context(db, pid)}\n\n"
        f"## Question\n{question}\n"
    )
    try:
        from . import llm  # lazy

        if transport in llm.API_TRANSPORTS:
            out = llm.make_chat_model(transport, model).invoke(prompt)
            content = getattr(out, "content", out)
            text = content if isinstance(content, str) else str(content)
        else:  # claude-cli / codex-cli
            text = llm.run_cli(llm.brain_of(transport), model, prompt, what="assistant")
        return text.strip() or status_summary(db, pid)
    except Exception:  # noqa: BLE001 — an assistant error must not break the channel
        logger.exception("assistant answer failed; using status summary")
        return status_summary(db, pid)
