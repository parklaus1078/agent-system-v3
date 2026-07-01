from __future__ import annotations

from sqlalchemy.orm import Session

from ..graph.store import get_graph, neighbors
from ..models import Node
from ..schemas_plan import StepSpec


def step_rag_context(memory, objective: str, step) -> str:
    """Semantic context packet for a step: the most relevant prior decisions/wiki pages
    for `<objective> <step.intent>`, injected via build_step_prompt(rag_context=...)."""
    if memory is None:
        return ""
    return memory.context_packet(f"{objective} {step.intent}")


def _objective(db: Session, project_id: str) -> str:
    for n in get_graph(db, project_id)["nodes"]:
        if n["kind"] == "objective":
            return n["label"]
    return ""


# The executor's standing task instruction (named so it's searchable, not a buried literal).
_TASK_INSTRUCTION = (
    "You are an autonomous coding agent working in the current git repository. "
    "Implement ONLY the step below by creating and editing the necessary files NOW. Make "
    "concrete, minimal code changes — actually write the files, do not just describe a plan. "
    "Keep changes scoped to this step. When the edits are done, stop."
)


def _owned_code_and_decisions(db: Session, project_id: str, ticket_id: str) -> tuple[list[str], list[str]]:
    """The CodeRegions the ticket already owns + its prior Decisions. Both hang off the ticket's
    STEPS (touches/decided edges have src=step), so aggregate across steps — the ticket itself
    references none. Code regions are de-duplicated + sorted for a stable prompt."""
    steps = [n for n in neighbors(db, project_id, ticket_id, "out") if n.kind == "step"]
    nbs = [nb for s in steps for nb in neighbors(db, project_id, s.id, "out")]
    owned = sorted(dict.fromkeys(nb.label for nb in nbs if nb.kind == "code_region"))
    decisions = list(dict.fromkeys(nb.label for nb in nbs if nb.kind == "decision"))
    return owned, decisions


def build_step_prompt(
    db: Session,
    project_id: str,
    ticket_id: str,
    step: StepSpec,
    rag_context: str = "",
    coding_rules: str = "",
    reviewer_note: str = "",
) -> str:
    """Scoped step prompt: the pinned Objective, the ticket, the step, the
    CodeRegions the ticket already owns and its prior Decisions — not the whole repo.
    The human-managed `coding_rules` (CP0 governance) are injected as a `# Rules (coding)`
    section; a `reviewer_note` (a changes/answer comment, CP3) guides a re-run."""
    ticket = db.get(Node, ticket_id)
    owned, decisions = _owned_code_and_decisions(db, project_id, ticket_id)
    parts = [
        f"# Task\n{_TASK_INSTRUCTION}",
        f"# Objective (pinned)\n{_objective(db, project_id)}",
        f"# Ticket\n{ticket.label if ticket else ticket_id}",
        f"# Step\n{step.label}: {step.intent}".rstrip(": ") + f"\nAcceptance: {step.acceptance}",
        "# Code you own (edit only what this step needs)\n"
        + ("\n".join(f"- {p}" for p in owned) or "- (none yet)"),
        "# Prior decisions\n" + ("\n".join(f"- {d}" for d in decisions) or "- (none)"),
    ]
    if rag_context:
        parts.append(f"# Relevant prior knowledge (RAG)\n{rag_context}")
    if (coding_rules or "").strip():
        parts.append(f"# Rules (coding)\n{coding_rules.strip()}")
    if (reviewer_note or "").strip():
        parts.append(f"# Reviewer guidance (address this in the re-run)\n{reviewer_note.strip()}")
    return "\n\n".join(parts)
