from app.services.embeddings import DeterministicEmbeddings
from app.services.memory import MemoryStore


def test_index_and_retrieve_packet():
    m = MemoryStore(DeterministicEmbeddings())
    m.index_text(
        "Gate features with flags, not by branching on subscription tier.",
        {"node_id": "d1", "kind": "decision"},
    )
    m.index_text("Use Alembic for schema migrations.", {"node_id": "d2", "kind": "decision"})
    # DeterministicEmbeddings is exact bag-of-words, so the query must share a real
    # token with d1 ("flags") to rank it over the unrelated d2.
    hits = m.retrieve("feature flags gating", k=1)
    assert hits and hits[0]["metadata"]["node_id"] == "d1"
    packet = m.context_packet("feature flags gating", k=1)
    assert "flags" in packet


def test_index_decision_reads_node_label(session):
    from app.graph.store import seed_graph

    seed_graph(
        session,
        "p1",
        nodes=[{"id": "d1", "kind": "decision", "label": "Gate by entitlement flag, not plan name."}],
        edges=[],
    )
    m = MemoryStore(DeterministicEmbeddings())
    assert m.index_decision(session, "p1", "d1") >= 1
    assert m.index_decision(session, "p1", "missing") == 0
    assert m.retrieve("entitlement flag", k=1)[0]["metadata"]["node_id"] == "d1"
