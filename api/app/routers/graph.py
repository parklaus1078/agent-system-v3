from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from .. import db as appdb  # for the BOOT nonce (referenced at call time so tests can patch it)
from ..db import get_session
from ..graph import revision, store
from ..schemas import GraphOut, LayoutIn, LayoutOut, StepDetailOut

router = APIRouter(prefix="/projects/{pid}", tags=["graph"])


@router.get("/graph", response_model=GraphOut)
def get_graph(pid: str, request: Request, response: Response, db: Session = Depends(get_session)):
    # Conditional GET: the project's revision counter (bumped on any node/edge commit) is a
    # weak ETag. An idle poll sends If-None-Match and we answer 304 here — no DB read, no
    # serialization — instead of re-scanning + re-serializing the whole graph every 1.5s.
    etag = f'W/"{appdb.BOOT}.{pid}.{revision.get(pid)}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)  # Response instance bypasses response_model
    response.headers["ETag"] = etag
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
    detail = store.step_detail(db, pid, sid)
    if detail["node"] is None:  # unknown/stale step id -> 404 (was an unguarded 500)
        raise HTTPException(404, "step not found")
    return detail


@router.get("/owning-path/{nid:path}")
def owning_path(pid: str, nid: str, db: Session = Depends(get_session)):
    return {"path": store.owning_path(db, pid, nid)}


@router.post("/layout", response_model=LayoutOut)
def save_layout(pid: str, body: LayoutIn, db: Session = Depends(get_session)):
    """Persist dragged node positions for this project (node.data.pos); echoed back by
    /graph so the map restores them on reload / another machine."""
    positions = {nid: {"x": p.x, "y": p.y} for nid, p in body.positions.items()}
    return {"updated": store.save_layout(db, pid, positions)}
