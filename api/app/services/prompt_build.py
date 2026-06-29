from __future__ import annotations

from sqlalchemy.orm import Session

from ..graph.store import get_graph, neighbors
from ..models import Node
from ..schemas_plan import StepSpec


def _objective(db: Session, project_id: str) -> str:
    for n in get_graph(db, project_id)["nodes"]:
        if n["kind"] == "objective":
            return n["label"]
    return ""


def build_step_prompt(
    db: Session, project_id: str, ticket_id: str, step: StepSpec, rag_context: str = ""
) -> str:
    """Scoped step prompt: the pinned Objective, the ticket, the step, the
    CodeRegions the ticket already owns and its prior Decisions — not the whole repo."""
    ticket = db.get(Node, ticket_id)
    owned = [n.label for n in neighbors(db, project_id, ticket_id, "out") if n.kind == "code_region"]
    decisions = [n.label for n in neighbors(db, project_id, ticket_id, "out") if n.kind == "decision"]
    parts = [
        f"# Objective (pinned)\n{_objective(db, project_id)}",
        f"# Ticket\n{ticket.label if ticket else ticket_id}",
        f"# Step\n{step.intent}\nAcceptance: {step.acceptance}",
        "# Code you own (edit only what this step needs)\n"
        + ("\n".join(f"- {p}" for p in owned) or "- (none yet)"),
        "# Prior decisions\n" + ("\n".join(f"- {d}" for d in decisions) or "- (none)"),
    ]
    if rag_context:
        parts.append(f"# Relevant prior knowledge (RAG)\n{rag_context}")
    return "\n\n".join(parts)
