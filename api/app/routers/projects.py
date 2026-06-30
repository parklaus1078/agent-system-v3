from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_session
from ..graph import store
from ..schemas import (
    ProjectApproveIn,
    ProjectCreatedOut,
    ProjectPlanIn,
    ProjectProposalOut,
)
from ..services.planner import (
    CliProjectPlanner,
    LangChainProjectPlanner,
    SimulatedProjectPlanner,
)

router = APIRouter(prefix="/projects", tags=["projects"])
logger = logging.getLogger("asv3.projects")


def _mode() -> str:
    return os.environ.get("ASV3_AGENT_MODE", "simulated")


def _project_planner():
    """Pick the project planner the same way lifecycle picks the step planner: real mode
    uses the CLI (Claude Code OAuth) unless an ANTHROPIC_API_KEY enables the API path."""
    if _mode() == "real":
        if os.environ.get("ANTHROPIC_API_KEY"):
            return LangChainProjectPlanner()
        return CliProjectPlanner(brain=os.environ.get("ASV3_BRAIN", "claude"))
    return SimulatedProjectPlanner()


@router.get("", response_model=list[dict])
def list_projects(db: Session = Depends(get_session)) -> list[dict]:
    """All projects (one per Objective) for the landing page."""
    return store.list_projects(db)


@router.post("/plan", response_model=ProjectProposalOut)
def plan_project(body: ProjectPlanIn, db: Session = Depends(get_session)):
    """Propose a project from a raw goal — {slug, title, tickets[]}. Persists NOTHING; the
    user edits/approves it next. The slug is pre-deduplicated so the proposed value is free."""
    logger.info("plan_project: mode=%s goal=%r", _mode(), body.goal[:80])
    proposal = _project_planner().propose_project(body.goal)
    slug = store.unique_slug(db, proposal.slug)
    return {
        "slug": slug,
        "title": proposal.title,
        "tickets": [{"title": t.title, "intent": t.intent} for t in proposal.tickets],
    }


@router.post("/approve", response_model=ProjectCreatedOut)
def approve_project(body: ProjectApproveIn, db: Session = Depends(get_session)):
    """Create the project: Objective(id=slug) + tickets (status=planning) + `has` edges.
    Normalizes the (possibly human-edited) slug, then delegates to create_project, which is
    idempotent: re-approving an existing slug is a no-op merge (not a duplicate). Uniqueness
    of a *new* slug is already ensured at /plan time."""
    from ..services.planner import slugify

    slug = slugify(body.slug or body.title)
    logger.info("approve_project: slug=%s title=%r tickets=%d", slug, body.title, len(body.tickets))
    return store.create_project(
        db,
        slug,
        body.title.strip() or slug,
        [{"title": t.title, "intent": t.intent} for t in body.tickets if t.title.strip()],
        description=body.description,
    )
