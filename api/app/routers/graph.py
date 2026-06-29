from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_session
from ..graph import store
from ..schemas import GraphOut, StepDetailOut

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
