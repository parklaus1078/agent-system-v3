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


def unique_slug(db: Session, base: str) -> str:
    """A project id free in the DB: `base`, else `base-2`, `base-3`, … (collision-safe)."""
    base = base or "project"
    if db.get(Node, base) is None:
        return base
    i = 2
    while db.get(Node, f"{base}-{i}") is not None:
        i += 1
    return f"{base}-{i}"


def create_project(
    db: Session,
    slug: str,
    title: str,
    tickets: list[dict],
    description: str | None = None,
) -> dict:
    """Create a project = Objective(id=slug) + its tickets (status=planning, no steps yet)
    + `has` edges, in one transaction. Idempotent: if `slug` is already an Objective, this
    is a no-op merge (returns the existing summary, created=False) so a re-submit can't
    duplicate. Tickets are decomposed into steps later via the ticket planner (Part B)."""
    existing = db.get(Node, slug)
    if existing is not None and existing.kind == "objective":
        n = len(
            db.scalars(
                select(Node).where(Node.project_id == slug, Node.kind == "ticket")
            ).all()
        )
        return {"projectId": slug, "title": existing.label, "tickets": n, "created": False}

    db.add(
        Node(
            id=slug,
            project_id=slug,
            kind="objective",
            label=title,
            data={"description": description} if description else {},
        )
    )
    created = 0
    for i, t in enumerate(tickets):
        tid = f"{slug}-t{i + 1}"
        data = {"intent": t["intent"]} if t.get("intent") else {}
        db.add(
            Node(id=tid, project_id=slug, kind="ticket", label=t["title"], status="planning", data=data)
        )
        db.add(Edge(id=f"has-{tid}", project_id=slug, src=slug, dst=tid, kind="has"))
        created += 1
    db.commit()
    return {"projectId": slug, "title": title, "tickets": created, "created": True}


def list_projects(db: Session) -> list[dict]:
    """One summary row per project (= per Objective node) for the landing page."""
    objectives = db.scalars(select(Node).where(Node.kind == "objective")).all()
    out: list[dict] = []
    for o in objectives:
        tickets = db.scalars(
            select(Node).where(Node.project_id == o.project_id, Node.kind == "ticket")
        ).all()
        steps = db.scalars(
            select(Node).where(Node.project_id == o.project_id, Node.kind == "step")
        ).all()
        out.append(
            {
                "projectId": o.project_id,  # the route param (/project/{projectId})
                "title": o.label,
                "description": (o.data or {}).get("description"),
                "tickets": len(tickets),
                "steps": len(steps),
                "awaiting": sum(1 for s in steps if s.status == "awaiting_review"),
            }
        )
    return out


def save_layout(db: Session, project_id: str, positions: dict[str, dict]) -> int:
    """Persist map node positions (drag&drop) as each node's `data.pos = {x, y}`, per
    project. Ignores unknown/foreign node ids and malformed coords. Returns #updated."""
    updated = 0
    for node_id, p in positions.items():
        node = db.get(Node, node_id)
        if node is None or node.project_id != project_id:
            continue
        try:
            x, y = float(p["x"]), float(p["y"])
        except (KeyError, TypeError, ValueError):
            continue
        node.data = {**(node.data or {}), "pos": {"x": x, "y": y}}
        updated += 1
    db.commit()
    return updated


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


def approve_plan(
    db: Session, project_id: str, ticket_id: str, step_labels: list[str], title: str | None = None
) -> dict:
    """Replace a ticket's steps with the approved list and start execution.
    Persists new step nodes + `has` edges; removes the old step children. If the
    ticket doesn't exist yet (a new goal), creates it under the objective."""
    ticket = db.get(Node, ticket_id)
    if ticket is None:
        ticket = Node(
            id=ticket_id,
            project_id=project_id,
            kind="ticket",
            label=title or ticket_id,
            status="executing",
            data={},
        )
        db.add(ticket)
        objective = db.scalars(
            select(Node).where(Node.project_id == project_id, Node.kind == "objective")
        ).first()
        if objective is None:
            # A project started from a bare goal has no Objective yet — create one (the
            # project root) so ProjectsHome shows the project and the ticket has a parent.
            objective = Node(
                id=f"{project_id}-obj",
                project_id=project_id,
                kind="objective",
                label=title or project_id,
                data={},
            )
            db.add(objective)
            db.flush()
        db.add(
            Edge(
                id=f"has-{objective.id}-{ticket_id}",
                project_id=project_id,
                src=objective.id,
                dst=ticket_id,
                kind="has",
            )
        )
        db.flush()

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
    if node is None:  # stale/deleted step id (e.g. a re-planned ticket) -> 404, not a 500
        return {"node": None, "diff": [], "decision": None, "acceptance": [],
                "createdNodeIds": [], "createdEdgeIds": []}
    touched = [n for n in neighbors(db, project_id, step_id, "out") if n.kind == "code_region"]
    decision = next(
        (n.label for n in neighbors(db, project_id, step_id, "out") if n.kind == "decision"), None
    )
    # Prefer the real per-file patches captured at commit time (stored on the step node);
    # fall back to the touched-file paths with empty patches (seeded/legacy steps).
    stored = (node.data or {}).get("diff")
    diff = stored if stored else [{"path": c.label, "patch": ""} for c in touched]
    return {
        "node": {
            "id": node.id,
            "kind": node.kind,
            "label": node.label,
            "status": node.status,
            "data": node.data,
        },
        "diff": diff,
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
