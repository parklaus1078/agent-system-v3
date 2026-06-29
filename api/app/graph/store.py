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


_REVIEW_NEXT = {"approve": "done", "changes": "executing", "takeover": "awaiting_review"}


def review_step(db: Session, project_id: str, step_id: str, kind: str) -> dict:
    """Apply a review decision to a step and persist the new status."""
    node = db.get(Node, step_id)
    if node is None or node.project_id != project_id:
        return {"ok": False}
    node.status = _REVIEW_NEXT.get(kind, node.status)
    db.commit()
    return {"ok": True, "status": node.status}


def approve_plan(db: Session, project_id: str, ticket_id: str, step_labels: list[str]) -> dict:
    """Replace a ticket's steps with the approved list and start execution.
    Persists new step nodes + `has` edges; removes the old step children."""
    has_edges = db.scalars(
        select(Edge).where(
            Edge.project_id == project_id, Edge.src == ticket_id, Edge.kind == "has"
        )
    ).all()
    for e in has_edges:
        child = db.get(Node, e.dst)
        if child is not None and child.kind == "step":
            db.delete(child)
            db.delete(e)
    db.flush()

    created: list[str] = []
    for i, label in enumerate(step_labels):
        sid = f"{ticket_id}-s{i + 1}"
        db.add(Node(id=sid, project_id=project_id, kind="step", label=label, status="planning"))
        db.add(Edge(id=f"has-{ticket_id}-{i + 1}", project_id=project_id, src=ticket_id, dst=sid, kind="has"))
        created.append(sid)

    ticket = db.get(Node, ticket_id)
    if ticket is not None:
        ticket.status = "executing"
    db.commit()
    return {"ticketId": ticket_id, "stepIds": created}


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
