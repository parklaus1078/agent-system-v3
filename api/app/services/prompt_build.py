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
    # Code regions and decisions hang off the ticket's STEPS (touches/decided edges
    # have src=step), so aggregate across the steps — querying the ticket directly
    # finds nothing. This is the prior context that scopes the current step.
    steps = [n for n in neighbors(db, project_id, ticket_id, "out") if n.kind == "step"]
    owned: list[str] = []
    decisions: list[str] = []
    for s in steps:
        for nb in neighbors(db, project_id, s.id, "out"):
            if nb.kind == "code_region":
                owned.append(nb.label)
            elif nb.kind == "decision":
                decisions.append(nb.label)
    owned = sorted(dict.fromkeys(owned))
    decisions = list(dict.fromkeys(decisions))
    parts = [
        "# Task\nYou are an autonomous coding agent working in the current git repository. "
        "Implement ONLY the step below by creating and editing the necessary files NOW. Make "
        "concrete, minimal code changes — actually write the files, do not just describe a plan. "
        "Keep changes scoped to this step. When the edits are done, stop.",
        f"# Objective (pinned)\n{_objective(db, project_id)}",
        f"# Ticket\n{ticket.label if ticket else ticket_id}",
        f"# Step\n{step.label}: {step.intent}".rstrip(": ") + f"\nAcceptance: {step.acceptance}",
        "# Code you own (edit only what this step needs)\n"
        + ("\n".join(f"- {p}" for p in owned) or "- (none yet)"),
        "# Prior decisions\n" + ("\n".join(f"- {d}" for d in decisions) or "- (none)"),
    ]
    if rag_context:
        parts.append(f"# Relevant prior knowledge (RAG)\n{rag_context}")
    return "\n\n".join(parts)
