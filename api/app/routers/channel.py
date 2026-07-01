"""CP2 conversation-channel endpoint — incremental message polling per project."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_session
from ..schemas import MessageOut
from ..services import channel

router = APIRouter(tags=["channel"])


@router.get("/projects/{pid}/messages", response_model=list[MessageOut])
def get_messages(pid: str, since: int | None = None, db: Session = Depends(get_session)):
    """A project's channel, oldest->newest. Pass `?since={id}` (the last seen message id) to
    fetch only newer messages — the cheap incremental poll the channel panel uses."""
    return channel.list_messages(db, pid, since=since)
