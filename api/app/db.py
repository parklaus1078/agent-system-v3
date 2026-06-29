from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    pass


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")


def _make_engine(url: str):
    # In-memory SQLite is per-connection; share one connection across threads so
    # the API (request threads) and seeding (test thread) see the same database.
    if url.startswith("sqlite") and ":memory:" in url:
        return create_engine(
            url,
            future=True,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    return create_engine(url, future=True)


engine = _make_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


def init_db(eng=engine) -> None:
    from . import models  # noqa: F401  (register tables on Base.metadata)

    Base.metadata.create_all(eng)


def get_session() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


_CHECKPOINTER = None


def make_checkpointer():
    """Process-wide LangGraph checkpointer (singleton). PostgresSaver when DATABASE_URL
    is Postgres (durable across restarts), else an in-memory MemorySaver — fine for the
    SQLite demo/tests, where lifecycle state lives for the life of the server process.
    PostgresSaver is imported lazily so the SQLite path needs no libpq/psycopg."""
    global _CHECKPOINTER
    if _CHECKPOINTER is not None:
        return _CHECKPOINTER
    if DATABASE_URL.startswith("postgres"):
        from langgraph.checkpoint.postgres import PostgresSaver

        cp = PostgresSaver.from_conn_string(DATABASE_URL).__enter__()
        cp.setup()
        _CHECKPOINTER = cp
    else:
        from langgraph.checkpoint.memory import MemorySaver

        _CHECKPOINTER = MemorySaver()
    return _CHECKPOINTER
