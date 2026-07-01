from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .db import init_db
from .routers import channel as channel_router
from .routers import governance as governance_router
from .routers import graph as graph_router
from .routers import lifecycle as lifecycle_router
from .routers import memory as memory_router
from .routers import projects as projects_router
from .routers import steer as steer_router

logger = logging.getLogger("asv3.main")


class _CatchAllMiddleware(BaseHTTPMiddleware):
    """Convert an unhandled exception into a 500 JSONResponse. Registered INSIDE
    CORSMiddleware so the error response still flows out through the CORS layer and
    keeps Access-Control-Allow-Origin — otherwise a browser cross-origin fetch to a
    failing endpoint gets an opaque 'Failed to fetch' and can't read the error."""

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception:  # noqa: BLE001 — last-resort handler; log + return JSON
            logger.exception("unhandled error on %s %s", request.method, request.url.path)
            return JSONResponse({"detail": "internal server error"}, status_code=500)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Configure logging so the app's INFO logs (asv3.*: planner/executor 'claude -p'
    # invocations, lifecycle transitions) actually reach stdout — without this they
    # propagate to Python's root WARNING lastResort handler and are dropped.
    logging.basicConfig(
        level=os.getenv("ASV3_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    logging.getLogger("asv3").setLevel(os.getenv("ASV3_LOG_LEVEL", "INFO"))
    init_db()
    # Crash recovery: a restart mid-execution leaves the async worker's `executing` status
    # orphaned (the thread is gone). Reset it so the UI isn't frozen. Only in async mode — the
    # sync test path (ASV3_ASYNC_EXEC=0) has no background workers, so `executing` is transient.
    if os.getenv("ASV3_ASYNC_EXEC", "1") != "0":
        from .db import SessionLocal, make_checkpointer
        from .graph.store import reconcile_stale_execution

        db = SessionLocal()
        try:
            reset_tickets = reconcile_stale_execution(db)
        finally:
            db.close()
        if reset_tickets:
            # the reset tickets' checkpoints are now desynced from the DB (they point mid-run) —
            # drop them so a re-plan/approve starts clean instead of resuming an abandoned run.
            cp = make_checkpointer()
            for tid in reset_tickets:
                try:
                    cp.delete_thread(f"ticket:{tid}")
                except Exception:  # noqa: BLE001 — a missing/undeletable thread must not block startup
                    logger.exception("could not drop checkpoint for reset ticket %s", tid)
            logger.info("startup: recovered %d ticket(s) stuck 'executing' from a prior crash/restart", len(reset_tickets))
    yield


app = FastAPI(title="Control Tower API", lifespan=lifespan)
# add_middleware adds OUTERMOST-last: CatchAll first => inner, CORS last => outer, so a
# 500 produced by CatchAll passes back through CORS and gets the CORS headers.
app.add_middleware(_CatchAllMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    # so a cross-origin browser (VITE_API_BASE) can READ the ETag and send If-None-Match
    expose_headers=["ETag"],
)
app.include_router(graph_router.router)
app.include_router(projects_router.router)
app.include_router(lifecycle_router.router)
app.include_router(memory_router.router)
app.include_router(governance_router.router)
app.include_router(channel_router.router)
app.include_router(steer_router.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
