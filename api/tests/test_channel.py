"""CP2 — conversation channel: typed agent messages wired to lifecycle transitions + cursor."""

import os

import pytest
from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app
from app.services import channel, governance
from app.services.executor import ExecResult


# ───────────────────────────── unit: channel service ─────────────────────────────
def test_post_and_list_messages(session):
    channel.post_message(session, "pu", "assumption", "Stripe로 가정", refs=["n1"])
    channel.post_message(session, "pu", "decision", "결정함", refs=["dec:n1"])
    out = channel.list_messages(session, "pu")
    assert [m["type"] for m in out] == ["assumption", "decision"]  # oldest -> newest
    assert out[0]["refs"] == ["n1"] and out[0]["author"] == "agent"
    # `since` returns only newer ids
    assert channel.list_messages(session, "pu", since=out[0]["id"]) == [out[1]]
    assert channel.list_messages(session, "other") == []  # per-project isolation


def test_gen_text_templates():
    assert "막혔" in channel.gen_text("blocked", step="구현")
    assert "선택지" in channel.gen_text("blocked", step="구현", options=["a", "b"])
    assert channel.gen_text("decision", decision="Stripe") == "결정: Stripe"
    assert "리뷰 대기" in channel.gen_text("review", step="구현")


# ───────────────────────────── lifecycle wiring (sync mode) ─────────────────────────────
@pytest.fixture(scope="module", autouse=True)
def _env():
    os.environ["ASV3_AGENT_MODE"] = "simulated"
    os.environ.pop("ASV3_THROTTLE", None)
    init_db()


@pytest.fixture()
def client():
    return TestClient(app)


def _make_planned(client, slug):
    client.post("/projects/approve", json={"slug": slug, "title": slug, "tickets": [{"title": "T"}]})
    tid = next(
        n["id"] for n in client.get(f"/projects/{slug}/graph").json()["nodes"] if n["kind"] == "ticket"
    )
    client.post(f"/projects/{slug}/tickets/{tid}/plan", json={})
    return tid


def _messages(client, slug, since=None):
    url = f"/projects/{slug}/messages" + (f"?since={since}" if since is not None else "")
    return client.get(url).json()


def test_per_step_gate_posts_a_review_message(client):
    slug = "chan-review"
    tid = _make_planned(client, slug)
    client.post(f"/projects/{slug}/tickets/{tid}/plan/approve", json={})  # per-step: step 1 gates
    review = [m for m in _messages(client, slug) if m["type"] == "review"]
    assert review and review[-1]["refs"] == [f"{tid}-s1"] and review[-1]["author"] == "agent"


def test_blocked_step_posts_a_blocked_message_not_a_review(client, monkeypatch):
    class FailFirst:
        def __init__(self, write):
            self.write = write

        def run(self, repo_dir, prompt):
            self.write(repo_dir)
            return ExecResult(summary="boom", decision=None, ok=False, output="")

    monkeypatch.setattr(governance, "SimulatedExecutor", FailFirst)
    slug = "chan-blocked"
    tid = _make_planned(client, slug)
    client.post(f"/projects/{slug}/tickets/{tid}/plan/approve", json={})  # step 1 fails -> blocked
    msgs = _messages(client, slug)
    blocked = [m for m in msgs if m["type"] == "blocked"]
    assert blocked and blocked[-1]["refs"] == [f"{tid}-s1"]
    # a blocked step is covered by its blocked message, NOT also a review message
    assert not [m for m in msgs if m["type"] == "review" and m["refs"] == [f"{tid}-s1"]]


def test_decision_posts_a_decision_message(client, monkeypatch):
    class Decider:
        def __init__(self, write):
            self.write = write

        def run(self, repo_dir, prompt):
            self.write(repo_dir)
            return ExecResult(summary="ok", decision="Stripe로 결제", ok=True, output="")

    monkeypatch.setattr(governance, "SimulatedExecutor", Decider)
    slug = "chan-decision"
    tid = _make_planned(client, slug)
    client.post(f"/projects/{slug}/tickets/{tid}/plan/approve", json={})  # step 1 records a decision
    dec = [m for m in _messages(client, slug) if m["type"] == "decision"]
    assert dec and "Stripe" in dec[-1]["text"] and dec[-1]["refs"] == [f"dec:{tid}-s1"]


def test_changes_rerun_posts_a_fresh_review_message(client):
    # regression: a `changes` re-run re-gates the step and must post a NEW review message
    # (the old text-dedup dropped it because the simulated summary is constant).
    slug = "chan-changes"
    tid = _make_planned(client, slug)
    client.post(f"/projects/{slug}/tickets/{tid}/plan/approve", json={})  # step 1 gates -> 1 review
    review_of = lambda: [m for m in _messages(client, slug) if m["type"] == "review" and m["refs"] == [f"{tid}-s1"]]
    assert len(review_of()) == 1
    client.post(f"/projects/{slug}/steps/{tid}-s1/review", json={"kind": "changes"})  # re-run + re-gate
    assert len(review_of()) == 2  # a fresh review prompt for the re-gated step


def test_decision_not_duplicated_on_changes_rerun(client, monkeypatch):
    class Decider:
        def __init__(self, write):
            self.write = write

        def run(self, repo_dir, prompt):
            self.write(repo_dir)
            return ExecResult(summary="ok", decision="Stripe", ok=True, output="")

    monkeypatch.setattr(governance, "SimulatedExecutor", Decider)
    slug = "chan-dec-dedup"
    tid = _make_planned(client, slug)
    client.post(f"/projects/{slug}/tickets/{tid}/plan/approve", json={})
    dec_of = lambda: [m for m in _messages(client, slug) if m["type"] == "decision"]
    assert len(dec_of()) == 1
    client.post(f"/projects/{slug}/steps/{tid}-s1/review", json={"kind": "changes"})  # same decision
    assert len(dec_of()) == 1  # unchanged decision -> NOT re-posted (no channel spam)


def test_messages_since_cursor_is_incremental(client):
    slug = "chan-since"
    tid = _make_planned(client, slug)
    client.post(f"/projects/{slug}/tickets/{tid}/plan/approve", json={})
    msgs = _messages(client, slug)
    assert msgs
    last_id = msgs[-1]["id"]
    assert _messages(client, slug, since=last_id) == []  # nothing newer yet
    client.post(f"/projects/{slug}/steps/{tid}-s1/review", json={"kind": "approve"})  # step 2 gates
    newer = _messages(client, slug, since=last_id)
    assert newer and all(m["id"] > last_id for m in newer)
    assert any(m["type"] == "review" and m["refs"] == [f"{tid}-s2"] for m in newer)
