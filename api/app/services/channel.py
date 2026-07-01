"""CP2 conversation channel — typed agent->human messages posted as the lifecycle advances.

Append-only (v1). `post_message` appends; `list_messages(since=)` is the incremental cursor for
`GET /projects/{pid}/messages?since={id}`. `gen_text` composes the message body.

Message-text generation is the home of CP0's `agent-message-gen` routing point: an LLM-backed
generator would plug in here. v1 (and ALWAYS under simulated) uses a deterministic template, so
generation stays offline, deterministic, and adds no DB reads to the worker's hot path.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Message

logger = logging.getLogger("asv3.channel")

# agent->human (CP2): assumption/blocked/decision/review. human->agent + system (CP3 steer):
# steer (the user's instruction), system (an op's result), clarify (router asks back).
MESSAGE_TYPES = ("assumption", "blocked", "decision", "review", "steer", "system", "clarify")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_dict(m: Message) -> dict:
    return {"id": m.id, "type": m.type, "author": m.author, "text": m.text, "refs": m.refs or [], "ts": m.ts}


def post_message(
    db: Session,
    pid: str,
    type: str,
    text: str,
    refs: list[str] | None = None,
    author: str = "agent",
) -> dict:
    """Append a typed message to a project's channel (append-only). Commits and returns it."""
    msg = Message(
        project_id=pid, type=type, author=author, text=text, refs=list(refs or []), ts=_now_iso()
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    logger.info("channel[%s] +%s #%s: %s", pid, type, msg.id, text[:80])
    return to_dict(msg)


def list_messages(db: Session, pid: str, since: int | None = None) -> list[dict]:
    """A project's channel, oldest->newest. `since` returns only messages with id > since
    (the incremental poll cursor)."""
    stmt = select(Message).where(Message.project_id == pid)
    if since is not None:
        stmt = stmt.where(Message.id > since)
    return [to_dict(m) for m in db.scalars(stmt.order_by(Message.id)).all()]


def gen_text(type: str, **ctx) -> str:
    """Compose the message text (deterministic template — the agent-message-gen extension point).
    Korean, matching the cockpit UI voice."""
    step = (ctx.get("step") or "").strip()
    summary = (ctx.get("summary") or "").strip()
    if type == "blocked":
        base = f"'{step}' 실행이 막혔어요 — 검토가 필요합니다." if step else "실행이 막혔어요 — 검토가 필요합니다."
        options = [o for o in (ctx.get("options") or []) if o]
        if options:
            base += " 선택지: " + " / ".join(options)
        return base
    if type == "decision":
        return f"결정: {(ctx.get('decision') or '').strip()}"
    if type == "review":
        base = f"'{step}' 리뷰 대기 — 승인 / 수정요청 / 인수 중 선택하세요." if step else "리뷰 대기 — 승인 / 수정요청 / 인수."
        return f"{base} (요약: {summary})" if summary else base
    if type == "assumption":
        return f"가정: {(ctx.get('text') or '').strip()}"
    return (ctx.get("text") or "").strip()
