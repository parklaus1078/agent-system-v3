from app.models import Node, Edge


def test_insert_node_and_edge(session):
    session.add(Node(id="t1", project_id="p1", kind="ticket", label="CRUD", status="executing"))
    session.add(Node(id="s1", project_id="p1", kind="step", label="form", status="done"))
    session.add(Edge(id="e1", project_id="p1", src="t1", dst="s1", kind="has"))
    session.commit()
    assert session.get(Node, "t1").label == "CRUD"
    assert session.get(Edge, "e1").kind == "has"
