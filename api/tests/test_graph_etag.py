"""Night-bug #4 — conditional GET /graph (revision counter + ETag/304) replaces wasteful polling."""

import os

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal, init_db
from app.graph import revision, store
from app.main import app
from app.routers import graph as graph_router


@pytest.fixture(scope="module", autouse=True)
def _env():
    os.environ["ASV3_AGENT_MODE"] = "simulated"
    init_db()


@pytest.fixture()
def client():
    return TestClient(app)


def test_revision_bumps_only_the_committed_project(client):
    pid = "rev-unit"
    before = revision.get(pid)
    db = SessionLocal()
    try:
        store.create_project(db, pid, "R", [{"title": "T"}])  # commits -> after_commit bumps
    finally:
        db.close()
    assert revision.get(pid) == before + 1
    snap = revision.get(pid)
    db = SessionLocal()
    try:
        store.create_project(db, "rev-other", "O", [{"title": "T"}])  # different pid
    finally:
        db.close()
    assert revision.get(pid) == snap  # unaffected


def test_graph_returns_etag_then_304_then_200_after_write(client):
    client.post("/projects/approve", json={"slug": "etag1", "title": "E", "tickets": [{"title": "T"}]})
    r1 = client.get("/projects/etag1/graph")
    assert r1.status_code == 200
    etag = r1.headers.get("ETag")
    assert etag

    r2 = client.get("/projects/etag1/graph", headers={"If-None-Match": etag})
    assert r2.status_code == 304 and r2.content == b""

    # a real node write bumps the revision -> the stale ETag now returns 200 + a new ETag
    tid = next(n["id"] for n in r1.json()["nodes"] if n["kind"] == "ticket")
    client.post("/projects/etag1/layout", json={"positions": {tid: {"x": 1, "y": 2}}})
    r3 = client.get("/projects/etag1/graph", headers={"If-None-Match": etag})
    assert r3.status_code == 200 and r3.headers.get("ETag") != etag


def test_304_path_does_no_db_read(client, monkeypatch):
    client.post("/projects/approve", json={"slug": "etag2", "title": "E", "tickets": [{"title": "T"}]})
    etag = client.get("/projects/etag2/graph").headers.get("ETag")
    calls = []
    real = store.get_graph
    monkeypatch.setattr(store, "get_graph", lambda *a, **k: (calls.append(1), real(*a, **k))[1])
    assert client.get("/projects/etag2/graph", headers={"If-None-Match": etag}).status_code == 304
    assert calls == []  # 304 short-circuited before any DB read/serialize
    client.get("/projects/etag2/graph")  # a normal GET still reads
    assert calls == [1]


def test_restart_nonce_invalidates_old_etag(client, monkeypatch):
    client.post("/projects/approve", json={"slug": "etag3", "title": "E", "tickets": [{"title": "T"}]})
    etag = client.get("/projects/etag3/graph").headers.get("ETag")
    monkeypatch.setattr(graph_router.appdb, "BOOT", "deadbeef")  # simulate a server restart
    assert client.get("/projects/etag3/graph", headers={"If-None-Match": etag}).status_code == 200
