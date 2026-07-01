from __future__ import annotations

from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Node(Base):
    __tablename__ = "nodes"

    # Unbounded: code_region ids are `cr:{path}` and can exceed any fixed VARCHAR for a deep path.
    # (Postgres enforces VARCHAR length and rejected 64+ char ids; SQLite silently ignored it —
    # so a too-small limit passed every test but broke real projects.)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # objective|ticket|step|code_region|test|decision
    label: Mapped[str] = mapped_column(String(500))
    status: Mapped[str | None] = mapped_column(String(20), default=None)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class Edge(Base):
    __tablename__ = "edges"

    # Unbounded: edge ids are composites like `tested_by:{step_id}:{path}` and `touch:{step_id}:
    # {path}` which easily pass 64 chars; src/dst hold (possibly long) node ids. See Node.id.
    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    src: Mapped[str] = mapped_column(String, index=True)
    dst: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String(20))  # has|subdivides|touches|tested_by|decided|produced


class Setting(Base):
    """Global (non-project) key/value config — the governance defaults (coding/planning
    rules + the model-routing table). A tiny key→JSON table; project-scoped overrides live
    on the Objective node's `data` instead. Deliberately has no `project_id`, so it is
    invisible to the per-project revision/ETag tracking in db.py."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class Message(Base):
    """CP2 conversation-channel message — a typed agent→human (or system/user) note posted as
    the lifecycle advances. Append-only (v1, no edit/delete). The autoincrement `id` is the
    monotonic cursor for `GET /messages?since={id}` incremental polling. Has `project_id` so a
    post bumps the per-project revision (db.py) — harmless, since a message always accompanies
    a graph change (status/decision)."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(64), index=True)
    type: Mapped[str] = mapped_column(String(20))  # assumption|blocked|decision|review
    author: Mapped[str] = mapped_column(String(10))  # agent|user|system
    text: Mapped[str] = mapped_column(String(2000))
    refs: Mapped[list] = mapped_column(JSON, default=list)  # referenced node ids
    ts: Mapped[str] = mapped_column(String(40))  # ISO-8601 created-at (display)
