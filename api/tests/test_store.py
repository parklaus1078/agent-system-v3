from app.graph.store import (
    seed_graph,
    get_graph,
    owning_path,
    review_step,
    approve_plan,
    neighbors,
)
from app.graph.diff_ingest import apply_step_diff
from app.models import Node

DIFF = "diff --git a/src/x.ts b/src/x.ts\n--- a/src/x.ts\n+++ b/src/x.ts\n@@ -0,0 +1 @@\n+x\n"


def _seed(db):
    seed_graph(
        db,
        "p1",
        nodes=[
            {"id": "obj", "kind": "objective", "label": "O"},
            {"id": "t1", "kind": "ticket", "label": "T", "status": "executing"},
            {"id": "s1", "kind": "step", "label": "S", "status": "awaiting_review"},
        ],
        edges=[
            {"id": "e1", "from": "obj", "to": "t1", "kind": "has"},
            {"id": "e2", "from": "t1", "to": "s1", "kind": "has"},
        ],
    )


def test_get_graph_roundtrip(session):
    _seed(session)
    g = get_graph(session, "p1")
    assert {n["id"] for n in g["nodes"]} == {"obj", "t1", "s1"}
    assert {e["from"] for e in g["edges"]} == {"obj", "t1"}


def test_apply_step_diff_is_idempotent(session):
    _seed(session)
    r1 = apply_step_diff(session, "p1", "s1", "sha1", DIFF)
    r2 = apply_step_diff(session, "p1", "s1", "sha1", DIFF)
    g = get_graph(session, "p1")
    assert sum(n["kind"] == "code_region" for n in g["nodes"]) == 1  # no duplicate
    assert sum(e["kind"] == "touches" for e in g["edges"]) == 1
    assert r1 == r2


def test_owning_path(session):
    _seed(session)
    apply_step_diff(session, "p1", "s1", "sha1", DIFF)
    assert owning_path(session, "p1", "cr:src/x.ts") == ["cr:src/x.ts", "s1", "t1", "obj"]


def test_review_step_persists_status(session):
    _seed(session)  # s1 is awaiting_review
    review_step(session, "p1", "s1", "approve")
    assert session.get(Node, "s1").status == "done"
    review_step(session, "p1", "s1", "changes")
    assert session.get(Node, "s1").status == "executing"


def test_approve_plan_persists_steps(session):
    _seed(session)  # t1 has step s1
    approve_plan(session, "p1", "t1", ["새 step A", "새 step B"])
    g = get_graph(session, "p1")
    labels = {n["label"] for n in g["nodes"] if n["kind"] == "step"}
    assert {"새 step A", "새 step B"} <= labels
    # ticket moves to executing once a plan is approved
    assert session.get(Node, "t1").status == "executing"


def test_approve_plan_creates_new_ticket_under_objective(session):
    _seed(session)  # has objective "obj"
    approve_plan(session, "p1", "t-new", ["스펙", "구현"], title="결제 붙이기")
    nt = session.get(Node, "t-new")
    assert nt is not None and nt.kind == "ticket" and nt.label == "결제 붙이기"
    # linked to the objective
    parents = [p.id for p in neighbors(session, "p1", "t-new", "in")]
    assert "obj" in parents
