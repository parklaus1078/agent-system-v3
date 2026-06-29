from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal, init_db
from app.graph.store import seed_graph
from app.models import Node


def setup_module():
    init_db()
    db = SessionLocal()
    seed_graph(
        db,
        "pw",
        nodes=[
            {"id": "obj2", "kind": "objective", "label": "O"},
            {"id": "t2", "kind": "ticket", "label": "T", "status": "planning"},
            {"id": "sw", "kind": "step", "label": "S", "status": "awaiting_review"},
        ],
        edges=[
            {"id": "ea", "from": "obj2", "to": "t2", "kind": "has"},
            {"id": "eb", "from": "t2", "to": "sw", "kind": "has"},
        ],
    )
    db.close()


def test_review_endpoint_persists_to_db():
    c = TestClient(app)
    r = c.post("/projects/pw/steps/sw/review", json={"kind": "approve"})
    assert r.status_code == 200
    db = SessionLocal()
    assert db.get(Node, "sw").status == "done"
    db.close()


def test_propose_plan_endpoint():
    c = TestClient(app)
    p = c.post("/projects/pw/plan/propose", json={"goal": "구독 결제 붙이기"}).json()
    assert p["ticketId"]
    assert len(p["steps"]) >= 1 and "label" in p["steps"][0]


def test_approve_plan_endpoint_persists_steps():
    c = TestClient(app)
    r = c.post(
        "/projects/pw/plan/approve",
        json={"ticketId": "t2", "steps": [{"label": "A"}, {"label": "B"}]},
    )
    assert r.status_code == 200
    db = SessionLocal()
    labels = {n.label for n in db.query(Node).filter(Node.project_id == "pw", Node.kind == "step").all()}
    assert {"A", "B"} <= labels
    assert db.get(Node, "t2").status == "executing"
    db.close()
