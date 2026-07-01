from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Node, Edge, Message


def ticket_order(t: Node) -> int:
    """A ticket's backlog position (smaller = earlier). An explicit `data.order` wins; else the
    creation index from its `-{n}` id suffix — so unset tickets keep their natural order. The
    `t?` keeps reading the legacy `-t{n}` format too."""
    o = (t.data or {}).get("order")
    if isinstance(o, (int, float)):
        return int(o)
    m = re.search(r"-t?(\d+)$", t.id)
    return int(m.group(1)) if m else 0


def next_ticket_id(db: Session, project_id: str) -> str:
    """The next ticket id for a project: `{project_id}-{n}` where n = highest existing ticket
    number + 1 (auto-increment, collision-safe). Ticket ids are `{slug}-{number}` — the `t?`
    also counts any legacy `-t{n}` tickets so numbering never reuses a taken number."""
    existing = db.scalars(
        select(Node).where(Node.project_id == project_id, Node.kind == "ticket")
    ).all()
    nums = [int(m.group(1)) for t in existing if (m := re.search(r"-t?(\d+)$", t.id))]
    n = (max(nums) + 1) if nums else 1
    tid = f"{project_id}-{n}"
    while db.get(Node, tid) is not None:  # belt-and-suspenders against a gap/collision
        n += 1
        tid = f"{project_id}-{n}"
    return tid


def next_ticket(db: Session, project_id: str) -> Node | None:
    """The next ticket the autonomous loop should run: the lowest-`order` non-done ticket (CP4
    reprioritize drives this)."""
    tickets = [
        t
        for t in db.scalars(
            select(Node).where(Node.project_id == project_id, Node.kind == "ticket")
        ).all()
        if t.status != "done"
    ]
    return min(tickets, key=ticket_order) if tickets else None


def add_ticket(db: Session, project_id: str, title: str, intent: str = "") -> str | None:
    """Create a new PLANNING ticket under the project's Objective (CP4 emergent `scope`),
    appended at the end of the backlog (`order` = max+1). Returns the new ticket id, or None if
    the project has no Objective."""
    objective = db.scalars(
        select(Node).where(Node.project_id == project_id, Node.kind == "objective")
    ).first()
    if objective is None:
        return None
    existing = db.scalars(
        select(Node).where(Node.project_id == project_id, Node.kind == "ticket")
    ).all()
    tid = next_ticket_id(db, project_id)
    order = max((ticket_order(t) for t in existing), default=0) + 1
    data = {"order": order}
    if intent:
        data["intent"] = intent
    db.add(Node(id=tid, project_id=project_id, kind="ticket", label=title, status="planning", data=data))
    db.add(Edge(id=f"has-{tid}", project_id=project_id, src=objective.id, dst=tid, kind="has"))
    db.commit()
    return tid


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
        tid = f"{slug}-{i + 1}"  # ticket ids are {slug}-{number(auto-increment)}
        data = {"intent": t["intent"]} if t.get("intent") else {}
        db.add(
            Node(id=tid, project_id=slug, kind="ticket", label=t["title"], status="planning", data=data)
        )
        db.add(Edge(id=f"has-{tid}", project_id=slug, src=slug, dst=tid, kind="has"))
        created += 1
    db.commit()
    return {"projectId": slug, "title": title, "tickets": created, "created": True}


def reconcile_stale_execution(db: Session) -> list[str]:
    """Startup crash-recovery: a fresh process has NO worker threads, so any `executing` status
    or in-progress activity spinner is STALE — the server died mid-run (the async worker never
    finished, but the DB status was never reconciled). Reset each stale executing STEP — to
    `awaiting_review` if it had already produced work (`ok` set from a commit), else `planning`
    to re-run — reset each stale executing TICKET to `planning`, and clear every leftover
    planning/executing activity spinner, so the UI isn't frozen. Returns the ids of the tickets
    that were reset, so the caller can drop their now-desynced LangGraph checkpoints."""
    affected: set[str] = set()
    changed = False
    for n in db.scalars(select(Node)).all():
        data = dict(n.data or {})
        node_changed = False
        if n.kind == "step" and n.status == "executing":
            n.status = "awaiting_review" if data.get("ok") else "planning"
            m = re.search(r"^(.*)-s\d+$", n.id)  # its owning ticket
            if m:
                affected.add(m.group(1))
            changed = True
        elif n.kind == "ticket" and n.status == "executing":
            n.status = "planning"
            affected.add(n.id)
            changed = True
        act = data.get("activity")
        if act and act.get("state") in {"executing", "planning"}:  # an in-progress spinner is stale
            data.pop("activity", None)
            node_changed = True
        if node_changed:
            n.data = data
            changed = True
    if changed:
        db.commit()
    return sorted(affected)


def delete_project(db: Session, project_id: str) -> dict | None:
    """Delete ALL mapping data for a project — every Node, Edge, and Message row scoped to it
    (the graph, the channel, everything). Returns `{ticketIds, nodes, edges, messages}` so the
    caller can also drop each ticket's LangGraph checkpoint / the repo directory; returns None if
    the project (its Objective) doesn't exist."""
    objective = db.scalars(
        select(Node).where(Node.project_id == project_id, Node.kind == "objective")
    ).first()
    if objective is None:
        return None
    ticket_ids = [
        t.id
        for t in db.scalars(
            select(Node).where(Node.project_id == project_id, Node.kind == "ticket")
        ).all()
    ]
    nodes = db.scalars(select(Node).where(Node.project_id == project_id)).all()
    edges = db.scalars(select(Edge).where(Edge.project_id == project_id)).all()
    messages = db.scalars(select(Message).where(Message.project_id == project_id)).all()
    counts = {"nodes": len(nodes), "edges": len(edges), "messages": len(messages)}
    for m in messages:
        db.delete(m)
    for e in edges:
        db.delete(e)
    for n in nodes:
        db.delete(n)
    db.commit()
    return {"ticketIds": ticket_ids, **counts}


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


def set_project_meta(
    db: Session,
    project_id: str,
    title: str | None = None,
    description: str | None = None,
) -> dict | None:
    """Update a project's title (Objective.label) and/or description (Objective.data.description).
    `title=None` / `description=None` leave that field unchanged; an empty/blank string clears
    the description. Returns the updated summary, or None if the project doesn't exist."""
    obj = db.scalars(
        select(Node).where(Node.project_id == project_id, Node.kind == "objective")
    ).first()
    if obj is None:
        return None
    if title is not None and title.strip():
        obj.label = title.strip()
    if description is not None:
        data = dict(obj.data or {})
        d = description.strip()
        if d:
            data["description"] = d
        else:
            data.pop("description", None)
        obj.data = data  # reassign so SQLAlchemy tracks the JSON change
    db.commit()
    return {"projectId": project_id, "title": obj.label, "description": (obj.data or {}).get("description")}


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


def _ensure_ticket_under_objective(
    db: Session, project_id: str, ticket_id: str, title: str | None
) -> None:
    """Create the ticket if it doesn't exist yet (a new goal). A project started from a bare
    goal has no Objective either — create that (the project root, so ProjectsHome shows it) plus
    the `has` edge so the ticket has a parent. No-op when the ticket already exists."""
    if db.get(Node, ticket_id) is not None:
        return
    db.add(Node(id=ticket_id, project_id=project_id, kind="ticket",
                label=title or ticket_id, status="executing", data={}))
    objective = db.scalars(
        select(Node).where(Node.project_id == project_id, Node.kind == "objective")
    ).first()
    if objective is None:
        objective = Node(id=f"{project_id}-obj", project_id=project_id, kind="objective",
                         label=title or project_id, data={})
        db.add(objective)
        db.flush()
    db.add(Edge(id=f"has-{objective.id}-{ticket_id}", project_id=project_id,
                src=objective.id, dst=ticket_id, kind="has"))
    db.flush()


def _replace_step_children(
    db: Session, project_id: str, ticket_id: str, step_labels: list[str]
) -> list[str]:
    """Delete the ticket's existing step children, then create the approved steps + `has` edges.
    Returns the new step ids."""
    has_edges = db.scalars(
        select(Edge).where(Edge.project_id == project_id, Edge.src == ticket_id, Edge.kind == "has")
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
    return created


def approve_plan(
    db: Session, project_id: str, ticket_id: str, step_labels: list[str], title: str | None = None
) -> dict:
    """Replace a ticket's steps with the approved list and start execution.
    Persists new step nodes + `has` edges; removes the old step children. If the
    ticket doesn't exist yet (a new goal), creates it under the objective."""
    _ensure_ticket_under_objective(db, project_id, ticket_id, title)
    created = _replace_step_children(db, project_id, ticket_id, step_labels)
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
