"""Ticket-id numbering ({slug}-{number}) + project deletion (mapping data + optional repo dir)."""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import init_db
from app.graph import store
from app.main import app
from app.models import Node


@pytest.fixture(scope="module", autouse=True)
def _env():
    os.environ["ASV3_AGENT_MODE"] = "simulated"
    init_db()


@pytest.fixture()
def client():
    return TestClient(app)


def _tickets(client, slug):
    return [n for n in client.get(f"/projects/{slug}/graph").json()["nodes"] if n["kind"] == "ticket"]


# ── ticket id = {slug}-{number(auto-increment)} ──────────────────────────────
def test_created_ticket_ids_are_slug_dash_number(client):
    slug = "idfmt"
    client.post("/projects/approve", json={"slug": slug, "title": "T", "tickets": [{"title": "a"}, {"title": "b"}]})
    ids = sorted(t["id"] for t in _tickets(client, slug))
    assert ids == [f"{slug}-1", f"{slug}-2"]  # {slug}-{number}, no legacy 't'


def test_scope_ticket_id_auto_increments(client):
    slug = "idinc"
    client.post("/projects/approve", json={"slug": slug, "title": "T", "tickets": [{"title": "핵심"}]})
    r = client.post(f"/projects/{slug}/steer", json={"text": "결제도 추가"})  # scope -> add_ticket
    assert r.json()["op"] == "scope"
    assert f"{slug}-2" in {t["id"] for t in _tickets(client, slug)}  # next number after {slug}-1


def test_reconcile_stale_execution_recovers_a_crashed_run(session):
    # a server restart mid-run leaves 'executing' orphaned (no worker); reconcile un-freezes it.
    store.seed_graph(
        session, "rx",
        nodes=[
            {"id": "rx-1", "kind": "ticket", "label": "T", "status": "executing", "data": {"activity": {"state": "executing"}}},
            {"id": "rx-1-s1", "kind": "step", "label": "a", "status": "done", "data": {"ok": True}},
            {"id": "rx-1-s2", "kind": "step", "label": "b", "status": "executing", "data": {}},           # crashed, no work
            {"id": "rx-1-s3", "kind": "step", "label": "c", "status": "executing", "data": {"ok": True}}, # committed, not advanced
            {"id": "rx-2", "kind": "ticket", "label": "idle", "status": "planning", "data": {}},          # untouched
        ],
        edges=[],
    )
    reset = store.reconcile_stale_execution(session)
    assert reset == ["rx-1"]  # only the crashed ticket
    assert session.get(Node, "rx-1").status == "planning"            # ticket un-stuck
    assert session.get(Node, "rx-1-s2").status == "planning"         # no work -> re-run
    assert session.get(Node, "rx-1-s3").status == "awaiting_review"  # had work -> review
    assert (session.get(Node, "rx-1").data or {}).get("activity") is None  # spinner cleared
    assert session.get(Node, "rx-2").status == "planning"            # unrelated ticket untouched


def test_next_ticket_id_is_max_plus_one_and_reads_legacy(session):
    store.seed_graph(
        session, "nx",
        nodes=[
            {"id": "obj", "kind": "objective", "label": "O"},
            {"id": "nx-1", "kind": "ticket", "label": "A"},
            {"id": "nx-3", "kind": "ticket", "label": "C"},  # a gap — must not reuse 2
        ],
        edges=[],
    )
    assert store.next_ticket_id(session, "nx") == "nx-4"  # max(1,3)+1
    store.seed_graph(
        session, "lg",
        nodes=[
            {"id": "obj2", "kind": "objective", "label": "O"},
            {"id": "lg-t2", "kind": "ticket", "label": "A"},  # legacy -t{n} still counted
        ],
        edges=[],
    )
    assert store.next_ticket_id(session, "lg") == "lg-3"


# ── project deletion ─────────────────────────────────────────────────────────
def test_delete_project_removes_all_mapping_data(client):
    slug = "delme"
    client.post("/projects/approve", json={"slug": slug, "title": "T", "tickets": [{"title": "a"}]})
    client.post(f"/projects/{slug}/steer", json={"text": "auth 건드리지 마"})  # constrain -> decision node + messages
    assert client.get(f"/projects/{slug}/graph").json()["nodes"]  # non-empty before delete

    r = client.delete(f"/projects/{slug}")
    assert r.status_code == 200
    body = r.json()
    assert body["projectId"] == slug and body["nodes"] >= 2 and body["directoryRemoved"] is False

    assert not any(p["projectId"] == slug for p in client.get("/projects").json())  # gone from listing
    assert client.get(f"/projects/{slug}/graph").json() == {"nodes": [], "edges": []}  # graph wiped
    assert client.get(f"/projects/{slug}/messages").json() == []  # channel wiped


def test_delete_project_404_when_missing(client):
    assert client.delete("/projects/does-not-exist").status_code == 404


def test_delete_project_with_directory_removes_the_repo_dir(client, tmp_path, monkeypatch):
    slug = "deldir"
    monkeypatch.setenv("ASV3_WORKSPACE_DIR", str(tmp_path))
    client.post("/projects/approve", json={"slug": slug, "title": "T", "tickets": [{"title": "a"}]})
    repo = Path(client.get(f"/projects/{slug}/info").json()["repoDir"])
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "file.txt").write_text("x")
    assert repo.exists()

    r = client.delete(f"/projects/{slug}?delete_directory=true")
    assert r.status_code == 200 and r.json()["directoryRemoved"] is True
    assert not repo.exists()  # the actual project directory is gone


def test_delete_project_default_keeps_the_repo_dir(client, tmp_path, monkeypatch):
    slug = "keepdir"
    monkeypatch.setenv("ASV3_WORKSPACE_DIR", str(tmp_path))
    client.post("/projects/approve", json={"slug": slug, "title": "T", "tickets": [{"title": "a"}]})
    repo = Path(client.get(f"/projects/{slug}/info").json()["repoDir"])
    repo.mkdir(parents=True, exist_ok=True)

    assert client.delete(f"/projects/{slug}").json()["directoryRemoved"] is False
    assert repo.exists()  # mapping deleted but the files are left untouched by default
