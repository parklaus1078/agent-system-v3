from __future__ import annotations

import os

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import DATABASE_URL, get_session
from ..models import Node
from ..services.embeddings import make_embeddings
from ..services.memory import MemoryStore


def _make_store(embeddings):
    """Real mode (real embeddings + Postgres) backs memory with PGVector so it persists;
    otherwise None -> in-memory store (demo/tests, no Postgres needed). Gated on the SAME
    condition as make_embeddings (== 'huggingface') so demo embeddings are never persisted."""
    if os.getenv("ASV3_EMBEDDINGS") == "huggingface" and DATABASE_URL.startswith("postgres"):
        from langchain_postgres import PGVector  # lazy: real-mode only

        return PGVector(
            embeddings=embeddings,
            collection_name="asv3_memory",
            connection=DATABASE_URL,
            use_jsonb=True,
        )
    return None


def _build_memory() -> MemoryStore:
    emb = make_embeddings()
    return MemoryStore(emb, _make_store(emb))


class _LazyMemory:
    """The single process-wide memory, built on FIRST use rather than at import — so a
    real embedding model (HuggingFace) is only downloaded when memory is actually used,
    not eagerly at module import (which would block app startup)."""

    _inst: MemoryStore | None = None

    def _store(self) -> MemoryStore:
        if _LazyMemory._inst is None:
            _LazyMemory._inst = _build_memory()
        return _LazyMemory._inst

    def __getattr__(self, name):
        return getattr(self._store(), name)


MEMORY = _LazyMemory()

router = APIRouter(tags=["memory"])


@router.get("/memory/search")
def search(q: str, k: int = 4):
    return MEMORY.retrieve(q, k)


@router.post("/memory/reindex/{project_id}")
def reindex(project_id: str, db: Session = Depends(get_session)):
    nodes = db.scalars(
        select(Node).where(Node.project_id == project_id, Node.kind == "decision")
    ).all()
    n = sum(MEMORY.index_decision(db, project_id, node.id) for node in nodes)
    return {"indexed": n}
