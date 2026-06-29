from __future__ import annotations

import os

from ..db import DATABASE_URL
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
