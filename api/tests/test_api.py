from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal, init_db
from app.graph.store import seed_graph


def setup_module():
    init_db()
    db = SessionLocal()
    seed_graph(
        db,
        "p1",
        nodes=[
            {"id": "obj", "kind": "objective", "label": "O"},
            {"id": "t1", "kind": "ticket", "label": "T", "status": "executing"},
            {"id": "s1", "kind": "step", "label": "S", "status": "awaiting_review"},
            {"id": "cr:x", "kind": "code_region", "label": "src/x.ts"},
            {"id": "d1", "kind": "decision", "label": "플래그로"},
        ],
        edges=[
            {"id": "e1", "from": "obj", "to": "t1", "kind": "has"},
            {"id": "e2", "from": "t1", "to": "s1", "kind": "has"},
            {"id": "e3", "from": "s1", "to": "cr:x", "kind": "touches"},
            {"id": "e4", "from": "s1", "to": "d1", "kind": "decided"},
        ],
    )
    db.close()


def test_graph_endpoint():
    c = TestClient(app)
    g = c.get("/projects/p1/graph").json()
    assert {n["id"] for n in g["nodes"]} >= {"obj", "t1", "s1"}
    assert g["edges"][0].keys() >= {"id", "from", "to", "kind"}


def test_step_detail_and_owning_path():
    c = TestClient(app)
    sd = c.get("/projects/p1/steps/s1").json()
    assert sd["decision"] == "플래그로"
    assert any(b["path"] == "src/x.ts" for b in sd["diff"])
    op = c.get("/projects/p1/owning-path/cr:x").json()
    assert op["path"] == ["cr:x", "s1", "t1", "obj"]
