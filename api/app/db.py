from __future__ import annotations

import logging
import os
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

logger = logging.getLogger("asv3.db")


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


def _libpq_url(url: str) -> str:
    """psycopg/PostgresSaver want a bare libpq URI, not SQLAlchemy's `+driver` form."""
    for sa in ("postgresql+psycopg://", "postgresql+psycopg2://", "postgres+psycopg://"):
        if url.startswith(sa):
            return "postgresql://" + url[len(sa):]
    return url


_CHECKPOINTER = None
_PG_CONN = None  # long-lived Postgres connection kept alive for the process lifetime


def make_checkpointer():
    """Process-wide LangGraph checkpointer (singleton).

    `ASV3_CHECKPOINTER`: `memory` (default for SQLite, and the robust default for the
    container — lifecycle state lives for the server process), `postgres` (durable
    across restarts), or `auto` (postgres iff DATABASE_URL is Postgres). PostgresSaver
    is imported lazily and falls back to MemorySaver if it can't connect, so a missing
    libpq/psycopg or DB never takes the API down."""
    global _CHECKPOINTER, _PG_CONN
    if _CHECKPOINTER is not None:
        return _CHECKPOINTER
    mode = os.getenv("ASV3_CHECKPOINTER", "auto")
    use_pg = mode == "postgres" or (mode == "auto" and DATABASE_URL.startswith("postgres"))
    if use_pg:
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
            from psycopg import Connection
            from psycopg.rows import dict_row

            # Open a LONG-LIVED connection and keep a module reference to it. Do NOT use
            # PostgresSaver.from_conn_string(...).__enter__(): that returns a context
            # manager which, once unreferenced, is garbage-collected and CLOSES the
            # connection — causing "the connection is closed" at setup()/first use.
            _PG_CONN = Connection.connect(
                _libpq_url(DATABASE_URL),
                autocommit=True,        # required by PostgresSaver
                prepare_threshold=0,
                row_factory=dict_row,
            )
            cp = PostgresSaver(_PG_CONN)
            cp.setup()
            _CHECKPOINTER = cp
            logger.info("checkpointer: PostgresSaver (durable)")
            return _CHECKPOINTER
        except Exception:  # libpq/psycopg/DB missing -> degrade, don't crash the API
            logger.exception("PostgresSaver unavailable; using in-memory checkpointer")
    from langgraph.checkpoint.memory import MemorySaver

    _CHECKPOINTER = MemorySaver()
    return _CHECKPOINTER
