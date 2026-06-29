from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_session
from ..graph import store
from ..schemas import (
    GraphOut,
    StepDetailOut,
    ReviewActionIn,
    ProposeIn,
    ApproveIn,
    PlanProposalOut,
)

router = APIRouter(prefix="/projects/{pid}", tags=["graph"])


@router.get("/graph", response_model=GraphOut)
def get_graph(pid: str, db: Session = Depends(get_session)):
    g = store.get_graph(db, pid)
    return {
        "nodes": g["nodes"],
        "edges": [
            {"id": e["id"], "from": e["from"], "to": e["to"], "kind": e["kind"]}
            for e in g["edges"]
        ],
    }


@router.get("/steps/{sid}", response_model=StepDetailOut)
def step_detail(pid: str, sid: str, db: Session = Depends(get_session)):
    return store.step_detail(db, pid, sid)


@router.get("/owning-path/{nid:path}")
def owning_path(pid: str, nid: str, db: Session = Depends(get_session)):
    return {"path": store.owning_path(db, pid, nid)}


@router.post("/steps/{sid}/review")
def review_step(pid: str, sid: str, action: ReviewActionIn, db: Session = Depends(get_session)):
    return store.review_step(db, pid, sid, action.kind)


@router.post("/plan/propose", response_model=PlanProposalOut)
def propose_plan(pid: str, body: ProposeIn):
    goal = body.goal
    return {
        "ticketId": "t-new",
        "steps": [
            {"label": "스펙·골격", "intent": f"{goal} 스펙 정리", "acceptance": "스펙 합의"},
            {"label": "구현", "intent": "핵심 구현", "acceptance": "동작"},
            {"label": "테스트", "intent": "테스트 추가", "acceptance": "그린"},
        ],
    }


@router.post("/plan/approve")
def approve_plan(pid: str, body: ApproveIn, db: Session = Depends(get_session)):
    return store.approve_plan(db, pid, body.ticketId, [s.label for s in body.steps], body.title)
