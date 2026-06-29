from pathlib import Path

from app.graph.store import seed_graph
from app.services.embeddings import DeterministicEmbeddings
from app.services.memory import MemoryStore
from app.services.promotion import promote_project


def test_promote_writes_wiki_and_indexes(session, tmp_path):
    seed_graph(
        session,
        "p1",
        nodes=[
            {"id": "obj", "kind": "objective", "label": "Todo"},
            {"id": "d1", "kind": "decision", "label": "Gate features with flags, not tier branching."},
        ],
        edges=[{"id": "e1", "from": "obj", "to": "d1", "kind": "decided"}],
    )
    mem = MemoryStore(DeterministicEmbeddings())
    paths = promote_project(session, "p1", mem, wiki_root=str(tmp_path))
    assert len(paths) == 1 and Path(paths[0]).exists()
    assert "flags" in Path(paths[0]).read_text()
    # now retrievable across projects via the personal wiki layer, with consistent metadata
    meta = mem.retrieve("feature flags gating", k=1)[0]["metadata"]
    assert meta["kind"] == "decision" and meta["node_id"] == "d1" and meta["wiki_path"]


def test_promote_is_idempotent(session, tmp_path):
    seed_graph(
        session,
        "p2",
        nodes=[{"id": "d9", "kind": "decision", "label": "Prefer composition over inheritance."}],
        edges=[],
    )
    mem = MemoryStore(DeterministicEmbeddings())
    a = promote_project(session, "p2", mem, wiki_root=str(tmp_path))
    b = promote_project(session, "p2", mem, wiki_root=str(tmp_path))
    assert a == b  # same node -> same file path (overwrite, no duplicate files)
