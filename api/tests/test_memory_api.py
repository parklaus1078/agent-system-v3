from fastapi.testclient import TestClient

from app.db import SessionLocal, init_db
from app.graph.store import seed_graph
from app.main import app
from app.models import Node
from app.routers.memory import MEMORY


def test_search_endpoint_returns_indexed_text():
    MEMORY.index_text("Gate features with flags.", {"node_id": "d1", "kind": "decision"})
    hits = TestClient(app).get("/memory/search", params={"q": "feature flags", "k": 1}).json()
    assert hits and "flags" in hits[0]["text"]


def test_reindex_endpoint_indexes_project_decisions():
    init_db()
    db = SessionLocal()
    if db.get(Node, "pmem-d1") is None:
        seed_graph(
            db,
            "pmem",
            nodes=[
                {"id": "pmem-d1", "kind": "decision", "label": "Cache entitlements per request."}
            ],
            edges=[],
        )
    db.close()
    r = TestClient(app).post("/memory/reindex/pmem").json()
    assert r["indexed"] >= 1
    hits = TestClient(app).get("/memory/search", params={"q": "cache entitlements", "k": 1}).json()
    assert hits and hits[0]["metadata"]["node_id"] == "pmem-d1"
