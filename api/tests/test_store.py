from app.graph.store import (
    seed_graph,
    get_graph,
    owning_path,
    review_step,
    approve_plan,
    neighbors,
)
from app.graph.diff_ingest import apply_step_diff, _is_test_path
from app.models import Node, Edge

DIFF = "diff --git a/src/x.ts b/src/x.ts\n--- a/src/x.ts\n+++ b/src/x.ts\n@@ -0,0 +1 @@\n+x\n"

# a diff touching a production file AND several test files (Tests-pane classification)
MIXED_DIFF = (
    "diff --git a/src/x.ts b/src/x.ts\n--- a/src/x.ts\n+++ b/src/x.ts\n@@ -0,0 +1 @@\n+x\n"
    "diff --git a/tests/test_foo.py b/tests/test_foo.py\n--- /dev/null\n+++ b/tests/test_foo.py\n@@ -0,0 +1 @@\n+y\n"
    "diff --git a/web/src/Shell.test.tsx b/web/src/Shell.test.tsx\n--- /dev/null\n+++ b/web/src/Shell.test.tsx\n@@ -0,0 +1 @@\n+z\n"
)


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


def test_is_test_path_classification():
    for p in ["tests/test_foo.py", "__tests__/x.ts", "test_x.py", "x_test.py", "a/b.test.tsx", "c.spec.ts"]:
        assert _is_test_path(p), p
    for p in ["contests/x.py", "detest_thing.py", "src/test_helpers/util.py", "src/app.ts", "generated/t1/step_1.ts"]:
        assert not _is_test_path(p), p


def test_apply_step_diff_classifies_test_files_as_test_nodes(session):
    _seed(session)
    apply_step_diff(session, "p1", "s1", "sha1", MIXED_DIFF)
    g = get_graph(session, "p1")
    nodes = {n["id"]: n for n in g["nodes"]}
    # production file -> code_region; test files -> test nodes (and NOT code_region)
    assert nodes["cr:src/x.ts"]["kind"] == "code_region"
    assert nodes["test:tests/test_foo.py"]["kind"] == "test"
    assert nodes["test:web/src/Shell.test.tsx"]["kind"] == "test"
    assert "cr:tests/test_foo.py" not in nodes
    # tested_by edges link the step to each test node
    by_kind = [(e["from"], e["to"], e["kind"]) for e in g["edges"]]
    assert ("s1", "test:tests/test_foo.py", "tested_by") in by_kind
    assert ("s1", "test:web/src/Shell.test.tsx", "tested_by") in by_kind
    assert ("s1", "cr:src/x.ts", "touches") in by_kind


def test_apply_step_diff_test_classification_is_idempotent(session):
    _seed(session)
    r1 = apply_step_diff(session, "p1", "s1", "sha1", MIXED_DIFF)
    r2 = apply_step_diff(session, "p1", "s1", "sha1", MIXED_DIFF)
    assert r1 == r2
    assert sum(1 for n in get_graph(session, "p1")["nodes"] if n["kind"] == "test") == 2


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
