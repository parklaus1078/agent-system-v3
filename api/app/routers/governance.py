"""CP0 governance endpoints — the human-managed Rules + Model-routing config.

Global config lives under no project prefix (`/rules`, `/models`); per-project overrides are
`/projects/{pid}/rules` and `/projects/{pid}/models`. `GET /models/available` reports
per-transport health (CLI on PATH / API key present) without ever exposing secret values.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Node
from ..schemas import (
    AutonomyIn,
    AutonomyOut,
    GlobalModelsOut,
    ModelAvailability,
    ModelsIn,
    ProjectAutonomyOut,
    ProjectModelsOut,
    ProjectRulesOut,
    RulesIn,
    RulesScope,
    TicketAutonomyOut,
)
from ..services import governance

router = APIRouter(tags=["governance"])
logger = logging.getLogger("asv3.governance")


# ────────────────────────────────── Rules ──────────────────────────────────
@router.get("/rules", response_model=RulesScope)
def get_global_rules(db: Session = Depends(get_session)):
    return governance.get_global_rules(db)


@router.put("/rules", response_model=RulesScope)
def put_global_rules(body: RulesIn, db: Session = Depends(get_session)):
    return governance.set_global_rules(db, coding=body.coding, planning=body.planning)


def _project_rules_view(db: Session, pid: str) -> dict:
    return {
        "project": governance.get_project_rules(db, pid),
        "global": governance.get_global_rules(db),
        "resolved": governance.resolve_rules(db, pid),
    }


@router.get("/projects/{pid}/rules", response_model=ProjectRulesOut)
def get_project_rules(pid: str, db: Session = Depends(get_session)):
    return _project_rules_view(db, pid)


@router.put("/projects/{pid}/rules", response_model=ProjectRulesOut)
def put_project_rules(pid: str, body: RulesIn, db: Session = Depends(get_session)):
    if governance.set_project_rules(db, pid, coding=body.coding, planning=body.planning) is None:
        raise HTTPException(404, "project not found")
    return _project_rules_view(db, pid)


# ────────────────────────────────── Models ─────────────────────────────────
def _global_models_view(db: Session) -> dict:
    return {
        "points": list(governance.POINTS),
        "transports": list(governance.TRANSPORTS),
        "supported": governance.supported_map(),
        "global": governance.get_global_models(db),
    }


@router.get("/models", response_model=GlobalModelsOut)
def get_global_models(db: Session = Depends(get_session)):
    return _global_models_view(db)


@router.put("/models", response_model=GlobalModelsOut)
def put_global_models(body: ModelsIn, db: Session = Depends(get_session)):
    governance.set_global_models(db, {k: v.model_dump() for k, v in body.models.items()})
    return _global_models_view(db)


@router.get("/models/available", response_model=list[ModelAvailability])
def get_models_available():
    """Per-transport health for the Models page (CLI present? key set?). Never returns the
    secret values themselves — only presence/status (open question #8)."""
    return governance.available_engines()


def _project_models_view(db: Session, pid: str) -> dict:
    return {
        "points": list(governance.POINTS),
        "transports": list(governance.TRANSPORTS),
        "supported": governance.supported_map(),
        "project": governance.get_project_models(db, pid),
        "global": governance.get_global_models(db),
        "resolved": {p: governance.resolve_engine(db, p, pid) for p in governance.POINTS},
    }


@router.get("/projects/{pid}/models", response_model=ProjectModelsOut)
def get_project_models(pid: str, db: Session = Depends(get_session)):
    return _project_models_view(db, pid)


@router.put("/projects/{pid}/models", response_model=ProjectModelsOut)
def put_project_models(pid: str, body: ModelsIn, db: Session = Depends(get_session)):
    models = {k: v.model_dump() for k, v in body.models.items()}
    if governance.set_project_models(db, pid, models) is None:
        raise HTTPException(404, "project not found")
    return _project_models_view(db, pid)


# ──────────────────────────── Autonomy / throttle (CP1) ────────────────────────────
@router.get("/autonomy", response_model=AutonomyOut)
def get_global_autonomy(db: Session = Depends(get_session)):
    return {"level": governance.get_global_autonomy(db)}


@router.put("/autonomy", response_model=AutonomyOut)
def put_global_autonomy(body: AutonomyIn, db: Session = Depends(get_session)):
    return {"level": governance.set_global_autonomy(db, body.level or governance.DEFAULT_AUTONOMY)}


def _project_autonomy_view(db: Session, pid: str) -> dict:
    return {
        "levels": list(governance.AUTONOMY_LEVELS),
        "project": governance.get_project_autonomy(db, pid),
        "global": governance.get_global_autonomy(db),
        "resolved": governance.resolve_autonomy(db, pid),
    }


@router.get("/projects/{pid}/autonomy", response_model=ProjectAutonomyOut)
def get_project_autonomy(pid: str, db: Session = Depends(get_session)):
    return _project_autonomy_view(db, pid)


@router.put("/projects/{pid}/autonomy", response_model=ProjectAutonomyOut)
def put_project_autonomy(pid: str, body: AutonomyIn, db: Session = Depends(get_session)):
    # set_project_autonomy returns None ONLY when the project is absent (a successful set —
    # including a null/clear — always returns the effective level string).
    if governance.set_project_autonomy(db, pid, body.level) is None:
        raise HTTPException(404, "project not found")
    return _project_autonomy_view(db, pid)


def _ticket_autonomy_view(db: Session, pid: str, tid: str) -> dict:
    return {
        "levels": list(governance.AUTONOMY_LEVELS),
        "ticket": governance.get_ticket_autonomy(db, pid, tid),
        "project": governance.get_project_autonomy(db, pid),
        "global": governance.get_global_autonomy(db),
        "resolved": governance.resolve_autonomy(db, pid, tid),
    }


@router.get("/projects/{pid}/tickets/{tid}/autonomy", response_model=TicketAutonomyOut)
def get_ticket_autonomy(pid: str, tid: str, db: Session = Depends(get_session)):
    # Mirror the PUT guard: reject a missing or non-ticket node so a UI can't render
    # ticket-level controls for something that isn't a ticket (get_ticket_autonomy returns
    # None both for "no override" and "not a ticket", so guard here explicitly).
    node = db.get(Node, tid)
    if node is None or node.project_id != pid or node.kind != "ticket":
        raise HTTPException(404, "ticket not found")
    return _ticket_autonomy_view(db, pid, tid)


@router.put("/projects/{pid}/tickets/{tid}/autonomy", response_model=TicketAutonomyOut)
def put_ticket_autonomy(pid: str, tid: str, body: AutonomyIn, db: Session = Depends(get_session)):
    if governance.set_ticket_autonomy(db, pid, tid, body.level) is None:
        raise HTTPException(404, "ticket not found")
    return _ticket_autonomy_view(db, pid, tid)
