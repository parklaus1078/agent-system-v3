"""CP4 — backlog reprioritize/scope steer ops + per-ticket throttle."""

import os

import pytest
from fastapi.testclient import TestClient

from app.db import init_db
from app.graph import store
from app.main import app
from app.models import Node
from app.services.intent import SimulatedIntentRouter


def test_router_classifies_reprioritize_and_scope():
    r = SimulatedIntentRouter()
    assert r.classify("결제 먼저 해줘", {})["op"] == "reprioritize"
    assert r.classify("prioritize the sync ticket", {})["op"] == "reprioritize"
    assert r.classify("다국어도 추가", {})["op"] == "scope"
    assert r.classify("add i18n support", {})["op"] == "scope"


@pytest.fixture(scope="module", autouse=True)
def _env():
    os.environ["ASV3_AGENT_MODE"] = "simulated"
    os.environ.pop("ASV3_THROTTLE", None)
    init_db()


@pytest.fixture()
def client():
    return TestClient(app)


def _tickets(client, slug):
    return [n for n in client.get(f"/projects/{slug}/graph").json()["nodes"] if n["kind"] == "ticket"]


def test_reprioritize_moves_a_ticket_to_the_front(client):
    slug = "bl-repri"
    client.post("/projects/approve", json={"slug": slug, "title": "B", "tickets": [{"title": "결제"}, {"title": "동기화"}]})
    r = client.post(f"/projects/{slug}/steer", json={"text": "동기화 먼저"})
    assert r.json()["op"] == "reprioritize" and r.json()["scope"]["ticket"].endswith("-2")
    tks = {t["label"]: t for t in _tickets(client, slug)}
    assert tks["동기화"]["data"].get("order", 99) < tks["결제"]["data"].get("order", 99)  # 동기화 now first


def test_reprioritize_resolves_the_target_from_the_text_not_the_first_token(client):
    # Two tickets share a token ('결제'); the instruction names the more specific one. The match
    # must score by overlap, not return whichever ticket is iterated first (CP4 review, medium).
    slug = "bl-repri-specific"
    client.post(
        "/projects/approve",
        json={"slug": slug, "title": "B", "tickets": [{"title": "결제 연동"}, {"title": "결제 알림"}]},
    )
    r = client.post(f"/projects/{slug}/steer", json={"text": "결제 알림 먼저"})
    assert r.json()["op"] == "reprioritize" and r.json()["scope"]["ticket"].endswith("-2")  # 결제 알림, not 결제 연동


def test_reprioritize_matches_case_insensitively(client):
    # 'prioritize payment' must resolve the 'Payment Gateway' ticket despite the capital P
    # (the old raw substring compare was case-sensitive and silently fell back to the ambient).
    slug = "bl-repri-case"
    client.post(
        "/projects/approve",
        json={"slug": slug, "title": "B", "tickets": [{"title": "Payment Gateway"}, {"title": "Stripe Integration"}]},
    )
    r = client.post(f"/projects/{slug}/steer", json={"text": "prioritize payment"})
    assert r.json()["op"] == "reprioritize" and r.json()["scope"]["ticket"].endswith("-1")  # Payment Gateway


def test_get_ticket_autonomy_404s_for_a_missing_or_non_ticket_node(client):
    # GET must guard like PUT: no ticket-level view for a node that isn't a ticket / doesn't exist.
    slug = "bl-auto-404"
    client.post("/projects/approve", json={"slug": slug, "title": "B", "tickets": [{"title": "T"}]})
    assert client.get(f"/projects/{slug}/tickets/does-not-exist/autonomy").status_code == 404
    obj = next(n for n in client.get(f"/projects/{slug}/graph").json()["nodes"] if n["kind"] == "objective")
    assert client.get(f"/projects/{slug}/tickets/{obj['id']}/autonomy").status_code == 404  # objective is not a ticket


def test_next_ticket_selects_lowest_order_non_done(session):
    # store.next_ticket is the autonomous-loop next-select that reprioritize's data.order drives.
    store.seed_graph(
        session, "nx",
        nodes=[
            {"id": "obj", "kind": "objective", "label": "O"},
            {"id": "nx-t1", "kind": "ticket", "label": "A", "status": "executing"},
            {"id": "nx-t2", "kind": "ticket", "label": "B", "status": "planning", "data": {"order": -1}},
            {"id": "nx-t3", "kind": "ticket", "label": "C", "status": "done", "data": {"order": -5}},
        ],
        edges=[],
    )
    # lowest order among NON-done tickets: nx-t2 (order -1) beats nx-t1 (id index 1); done nx-t3 skipped
    assert store.next_ticket(session, "nx").id == "nx-t2"
    # once every ticket is done, there is nothing to run next
    for t in session.query(Node).filter(Node.kind == "ticket").all():
        t.status = "done"
    session.commit()
    assert store.next_ticket(session, "nx") is None


def test_scope_creates_a_new_planning_ticket(client):
    slug = "bl-scope"
    client.post("/projects/approve", json={"slug": slug, "title": "B", "tickets": [{"title": "핵심"}]})
    before = len(_tickets(client, slug))
    r = client.post(f"/projects/{slug}/steer", json={"text": "다국어도 추가"})
    assert r.json()["op"] == "scope"
    tks = _tickets(client, slug)
    assert len(tks) == before + 1
    new = next(t for t in tks if "다국어" in t["label"])
    assert new["status"] == "planning"
    # the emergent ticket appears after the objective in the graph + gets a channel message
    msgs = client.get(f"/projects/{slug}/messages").json()
    assert any(m["type"] == "system" and m["refs"] == [new["id"]] for m in msgs)


def test_per_ticket_throttle_resolves_ticket_over_project_over_global(client):
    slug = "bl-throttle"
    client.post("/projects/approve", json={"slug": slug, "title": "B", "tickets": [{"title": "T"}]})
    tid = _tickets(client, slug)[0]["id"]
    a = f"/projects/{slug}/tickets/{tid}/autonomy"
    assert client.get(a).json()["resolved"] == "per-step"  # global default
    client.put(f"/projects/{slug}/autonomy", json={"level": "co-pilot"})  # project override
    assert client.get(a).json()["resolved"] == "co-pilot"
    body = client.put(a, json={"level": "auto"}).json()  # ticket override wins
    assert body["ticket"] == "auto" and body["project"] == "co-pilot" and body["resolved"] == "auto"
    client.put(a, json={"level": None})  # clear ticket -> back to project
    assert client.get(a).json()["resolved"] == "co-pilot"
    assert client.put(f"/projects/{slug}/tickets/nope/autonomy", json={"level": "auto"}).status_code == 404


def test_ticket_level_autonomy_drives_the_lifecycle(client):
    slug = "bl-ticket-auto"
    client.post("/projects/approve", json={"slug": slug, "title": "B", "tickets": [{"title": "T"}]})
    tid = _tickets(client, slug)[0]["id"]
    client.put(f"/projects/{slug}/tickets/{tid}/autonomy", json={"level": "auto"})  # ticket-level auto
    client.post(f"/projects/{slug}/tickets/{tid}/plan", json={})
    client.post(f"/projects/{slug}/tickets/{tid}/plan/approve", json={})  # auto -> runs the ticket to done
    steps = [
        n for n in client.get(f"/projects/{slug}/graph").json()["nodes"]
        if n["kind"] == "step" and n["id"].startswith(f"{tid}-s")
    ]
    assert steps and all(s["status"] == "done" for s in steps)
