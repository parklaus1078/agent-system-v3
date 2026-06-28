from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Node, Edge


def seed_graph(db: Session, project_id: str, nodes: list[dict], edges: list[dict]) -> None:
    for n in nodes:
        db.add(
            Node(
                id=n["id"],
                project_id=project_id,
                kind=n["kind"],
                label=n["label"],
                status=n.get("status"),
                data=n.get("data", {}),
            )
        )
    for e in edges:
        db.add(Edge(id=e["id"], project_id=project_id, src=e["from"], dst=e["to"], kind=e["kind"]))
    db.commit()


def get_graph(db: Session, project_id: str) -> dict:
    nodes = db.scalars(select(Node).where(Node.project_id == project_id)).all()
    edges = db.scalars(select(Edge).where(Edge.project_id == project_id)).all()
    return {
        "nodes": [
            {"id": n.id, "kind": n.kind, "label": n.label, "status": n.status, "data": n.data}
            for n in nodes
        ],
        "edges": [{"id": e.id, "from": e.src, "to": e.dst, "kind": e.kind} for e in edges],
    }


def neighbors(db: Session, project_id: str, node_id: str, direction: str) -> list[Node]:
    ids: set[str] = set()
    edges = db.scalars(select(Edge).where(Edge.project_id == project_id)).all()
    for e in edges:
        if direction in ("out", "both") and e.src == node_id:
            ids.add(e.dst)
        if direction in ("in", "both") and e.dst == node_id:
            ids.add(e.src)
    return [db.get(Node, i) for i in ids if db.get(Node, i)]


def step_detail(db: Session, project_id: str, step_id: str) -> dict:
    node = db.get(Node, step_id)
    touched = [n for n in neighbors(db, project_id, step_id, "out") if n.kind == "code_region"]
    decision = next(
        (n.label for n in neighbors(db, project_id, step_id, "out") if n.kind == "decision"), None
    )
    return {
        "node": {
            "id": node.id,
            "kind": node.kind,
            "label": node.label,
            "status": node.status,
            "data": node.data,
        },
        "diff": [{"path": c.label, "patch": ""} for c in touched],
        "decision": decision,
        "acceptance": [{"text": f"{node.label} 확인", "met": node.status == "done"}],
        "createdNodeIds": [c.id for c in touched],
        "createdEdgeIds": [
            e.id
            for e in db.scalars(
                select(Edge).where(Edge.project_id == project_id, Edge.src == step_id)
            ).all()
        ],
    }


def owning_path(db: Session, project_id: str, node_id: str) -> list[str]:
    order = ["code_region", "step", "ticket", "objective"]
    path = [node_id]
    cur = db.get(Node, node_id)
    if cur is None:
        return path
    idx = order.index(cur.kind) if cur.kind in order else 0
    for i in range(idx, len(order) - 1):
        parents = [p for p in neighbors(db, project_id, path[-1], "in") if p.kind == order[i + 1]]
        if not parents:
            break
        path.append(parents[0].id)
    return path
