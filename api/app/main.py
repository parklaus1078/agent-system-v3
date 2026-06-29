from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .db import init_db
from .routers import graph as graph_router
from .routers import lifecycle as lifecycle_router
from .routers import memory as memory_router

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
    init_db()
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
)
app.include_router(graph_router.router)
app.include_router(lifecycle_router.router)
app.include_router(memory_router.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
