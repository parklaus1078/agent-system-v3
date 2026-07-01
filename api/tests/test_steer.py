"""CP3 — steer: NL -> intent op -> execute, appended to the channel (simulated router, sync)."""

import os

import pytest
from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app
from app.routers.memory import MEMORY
from app.services import governance
from app.services.executor import ExecResult
from app.services.intent import SimulatedIntentRouter


# ───────────────────────────── unit: simulated router ─────────────────────────────
def test_simulated_router_maps_nl_to_ops():
    r = SimulatedIntentRouter()
    assert r.classify("use Stripe", {})["op"] == "redirect"
    assert r.classify("결제는 Stripe로", {})["op"] == "redirect"
    assert r.classify("don't touch auth", {})["op"] == "constrain"
    assert r.classify("auth 건드리지 마", {})["op"] == "constrain"
    assert r.classify("pause", {})["op"] == "control"
    assert r.classify("auto로 바꿔", {})["args"]["level"] == "auto"
    # `answer` only when a question (blocked step) is pending — otherwise clarify (no guessing)
    assert r.classify("the first option is fine", {"has_blocked": True, "blocked_step": "s1"})["op"] == "answer"
    assert r.classify("the first option is fine", {})["op"] == "clarify"
    assert r.classify("???", {})["op"] == "clarify"  # bare punctuation isn't a question
    # a real question (no command) -> `ask` (conversational Q&A), not a canned clarify
    assert r.classify("이 프로젝트 상태 어때?", {})["op"] == "ask"
    assert r.classify("지금 티켓 몇 개야?", {})["op"] == "ask"


# ───────────────────────────── endpoint (sync mode) ─────────────────────────────
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


def _steps(client, slug, tid):
    g = client.get(f"/projects/{slug}/graph").json()
    kids = {e["to"] for e in g["edges"] if e["from"] == tid and e["kind"] == "has"}
    steps = [n for n in g["nodes"] if n["id"] in kids and n["kind"] == "step"]
    return sorted(steps, key=lambda n: n["id"])


def _messages(client, slug):
    return client.get(f"/projects/{slug}/messages").json()


def test_steer_records_the_user_message_and_clarifies_when_ambiguous(client):
    slug = "steer-basic"
    _make_planned(client, slug)
    r = client.post(f"/projects/{slug}/steer", json={"text": "무슨 소리인지 잘 모르겠는 문장"})
    assert r.status_code == 200 and r.json()["op"] == "clarify"
    msgs = _messages(client, slug)
    assert any(m["type"] == "steer" and m["author"] == "user" for m in msgs)  # instruction recorded
    assert any(m["type"] == "clarify" and m["author"] == "system" for m in msgs)  # asked back


def test_ask_op_answers_a_question_with_project_context(client):
    slug = "steer-ask"
    _make_planned(client, slug)
    r = client.post(f"/projects/{slug}/steer", json={"text": "이 프로젝트 상태 어때?"})
    assert r.status_code == 200 and r.json()["op"] == "ask"
    # simulated agent-message-gen -> a deterministic status summary grounded in the project
    assert "티켓" in r.json()["result"]["answer"]
    msgs = _messages(client, slug)
    assert any(m["author"] == "agent" and "티켓" in m["text"] for m in msgs)  # posted as an agent reply


def test_redirect_replans_the_target_ticket(client):
    slug = "steer-redirect"
    tid = _make_planned(client, slug)
    client.post(f"/projects/{slug}/tickets/{tid}/plan/approve", json={})
    before = [s["label"] for s in _steps(client, slug, tid)]
    r = client.post(f"/projects/{slug}/steer", json={"text": "use Stripe", "ticketId": tid})
    assert r.json()["op"] == "redirect"
    after = [s["label"] for s in _steps(client, slug, tid)]
    assert after != before and any("Stripe" in lbl for lbl in after)  # re-planned, reflects redirect
    assert any(m["type"] == "system" and "redirect" in m["text"] for m in _messages(client, slug))


def test_constrain_creates_a_decision_node_propagated_via_rag(client):
    slug = "steer-constrain"
    _make_planned(client, slug)
    r = client.post(f"/projects/{slug}/steer", json={"text": "don't touch auth"})
    assert r.json()["op"] == "constrain"
    cid = r.json()["result"]["nodeId"]
    node = next((n for n in client.get(f"/projects/{slug}/graph").json()["nodes"] if n["id"] == cid), None)
    assert node and node["kind"] == "decision" and "auth" in node["label"]
    assert any(m["type"] == "decision" and m["refs"] == [cid] for m in _messages(client, slug))
    hits = MEMORY.retrieve("don't touch auth", k=5)  # propagated via the existing RAG index
    assert any("auth" in h["text"] for h in hits)


def test_answer_unblocks_a_blocked_step(client, monkeypatch):
    class FailOnce:  # class-level counter -> fails the FIRST execution, succeeds on the re-run
        calls = 0

        def __init__(self, write):
            self.write = write

        def run(self, repo_dir, prompt):
            FailOnce.calls += 1
            self.write(repo_dir)
            return ExecResult(summary="x", decision=None, ok=FailOnce.calls > 1, output="")

    FailOnce.calls = 0
    monkeypatch.setattr(governance, "SimulatedExecutor", FailOnce)
    slug = "steer-answer"
    tid = _make_planned(client, slug)
    client.post(f"/projects/{slug}/tickets/{tid}/plan/approve", json={})  # step 1 fails -> blocked
    assert _steps(client, slug, tid)[0]["status"] == "blocked"
    r = client.post(f"/projects/{slug}/steer", json={"text": "the first option is fine"})
    assert r.json()["op"] == "answer"
    assert _steps(client, slug, tid)[0]["status"] != "blocked"  # re-ran with the answer -> unblocked


def test_throttle_does_not_overmatch_substrings():
    r = SimulatedIntentRouter()
    # regression: 'auto'/'자동' as an incidental substring must NOT flip autonomy
    assert r.classify("자동 저장으로 바꿔", {})["op"] == "redirect"  # auto-SAVE feature, not the dial
    assert r.classify("make the retry automatic", {})["op"] != "control"  # 'automatic' isn't a dial
    assert r.classify("auto로 바꿔", {})["op"] == "control"  # an explicit dial setting still works


def test_redirect_resets_checkpoint_so_the_new_plan_runs(client):
    # regression: redirect must keep the DB + LangGraph checkpoint in sync — reset to a
    # re-plannable state so re-running executes the NEW plan (not the abandoned old one).
    slug = "steer-redirect-run"
    tid = _make_planned(client, slug)
    client.post(f"/projects/{slug}/tickets/{tid}/plan/approve", json={})  # old plan gated at step 1
    client.post(f"/projects/{slug}/steer", json={"text": "use Stripe", "ticketId": tid})
    steps = _steps(client, slug, tid)
    assert all(s["status"] == "planning" for s in steps) and any("Stripe" in s["label"] for s in steps)
    # run the redirected plan via the normal flow -> the NEW step executes, no stale gate resumes
    client.post(f"/projects/{slug}/tickets/{tid}/plan", json={})
    client.post(f"/projects/{slug}/tickets/{tid}/plan/approve", json={})
    steps = _steps(client, slug, tid)
    assert steps[0]["status"] == "awaiting_review" and "Stripe" in steps[0]["label"]


def test_answer_guidance_reaches_the_rerun_prompt(client, monkeypatch):
    prompts: list[str] = []

    class CapFailOnce:
        calls = 0

        def __init__(self, write):
            self.write = write

        def run(self, repo_dir, prompt):
            CapFailOnce.calls += 1
            prompts.append(prompt)
            self.write(repo_dir)
            return ExecResult(summary="x", decision=None, ok=CapFailOnce.calls > 1, output="")

    CapFailOnce.calls = 0
    monkeypatch.setattr(governance, "SimulatedExecutor", CapFailOnce)
    slug = "steer-answer-guide"
    tid = _make_planned(client, slug)
    client.post(f"/projects/{slug}/tickets/{tid}/plan/approve", json={})  # step 1 fails -> blocked
    client.post(f"/projects/{slug}/steer", json={"text": "the first option, please"})
    # the answer text reaches the re-run's prompt as reviewer guidance (not a blind retry)
    assert any("Reviewer guidance" in p and "first option" in p for p in prompts)


def test_control_pause_then_throttle(client):
    slug = "steer-control"
    _make_planned(client, slug)
    assert client.post(f"/projects/{slug}/steer", json={"text": "pause"}).json()["op"] == "control"
    assert client.get(f"/projects/{slug}/autonomy").json()["resolved"] == "per-step"  # paused
    client.post(f"/projects/{slug}/steer", json={"text": "auto로 바꿔"})  # throttle -> auto
    assert client.get(f"/projects/{slug}/autonomy").json()["resolved"] == "auto"
