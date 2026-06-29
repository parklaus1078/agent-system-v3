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
    """Real mode (Postgres + a real embedding model) backs memory with PGVector so it
    persists; otherwise None -> in-memory store (demo/tests, no Postgres needed)."""
    if os.getenv("ASV3_EMBEDDINGS") and DATABASE_URL.startswith("postgres"):
        from langchain_postgres import PGVector  # lazy: real-mode only

        return PGVector(
            embeddings=embeddings,
            collection_name="asv3_memory",
            connection=DATABASE_URL,
            use_jsonb=True,
        )
    return None


# The single process-wide memory the lifecycle router and the memory API both use.
_EMB = make_embeddings()
MEMORY = MemoryStore(_EMB, _make_store(_EMB))

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
