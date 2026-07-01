"""CP0 governance — rules injection + model routing (resolvers, prompts, endpoints)."""

import os

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal, init_db
from app.graph.store import seed_graph
from app.main import app
from app.models import Setting
from app.schemas_plan import StepSpec
from app.services import governance
from app.services.planner import CliPlanner, CliProjectPlanner
from app.services.prompt_build import build_step_prompt


def _seed_objective(session, pid: str) -> None:
    seed_graph(session, pid, nodes=[{"id": pid, "kind": "objective", "label": "obj"}], edges=[])


# ─────────────────────────────── unit: rules ───────────────────────────────
def test_global_rules_seed_from_file(session):
    r = governance.get_global_rules(session)
    assert "DRY" in r["coding"]  # seeded from docs/general_coding_rules.md
    assert r["planning"] == ""   # planning starts empty for the human to author


def test_resolve_rules_merges_global_and_project(session):
    governance.set_global_rules(session, coding="GLOBAL-CODE", planning="GLOBAL-PLAN")
    _seed_objective(session, "pg")
    governance.set_project_rules(session, "pg", coding="PROJ-CODE")
    res = governance.resolve_rules(session, "pg")
    assert "GLOBAL-CODE" in res["coding"] and "PROJ-CODE" in res["coding"]  # appended
    assert res["planning"] == "GLOBAL-PLAN"  # no project planning override -> global only


def test_resolve_rules_no_pid_is_global_only(session):
    governance.set_global_rules(session, coding="ONLY-GLOBAL")
    assert governance.resolve_rules(session, None)["coding"] == "ONLY-GLOBAL"


def test_set_project_rules_missing_project_returns_none(session):
    assert governance.set_project_rules(session, "nope", coding="x") is None


def test_merge_keeps_project_override_when_global_is_oversized(session):
    governance.set_global_rules(session, coding="G" * (governance.MAX_RULES_CHARS - 5))
    _seed_objective(session, "pbig")
    governance.set_project_rules(session, "pbig", coding="PROJECT-OVERRIDE-XYZ")
    resolved = governance.resolve_rules(session, "pbig")["coding"]
    assert "PROJECT-OVERRIDE-XYZ" in resolved  # override survives — global is truncated, not it
    assert len(resolved) <= governance.MAX_RULES_CHARS


# ──────────────────────── unit: rule injection into prompts ─────────────────────
def test_build_step_prompt_includes_coding_rules(session):
    seed_graph(
        session, "pi",
        nodes=[
            {"id": "pi", "kind": "objective", "label": "obj"},
            {"id": "pi-t1", "kind": "ticket", "label": "tk"},
        ],
        edges=[{"id": "h", "from": "pi", "to": "pi-t1", "kind": "has"}],
    )
    step = StepSpec(label="L", intent="I", acceptance="A")
    prompt = build_step_prompt(session, "pi", "pi-t1", step, coding_rules="MY-CODING-RULE")
    assert "# Rules (coding)" in prompt and "MY-CODING-RULE" in prompt
    # no rules -> no section
    bare = build_step_prompt(session, "pi", "pi-t1", step, coding_rules="")
    assert "# Rules (coding)" not in bare


def test_planner_prompts_include_planning_rules():
    assert "# Rules (planning)" in CliPlanner(planning_rules="MY-PLAN")._prompt("o", "t", "")
    assert "MY-PLAN" in CliPlanner(planning_rules="MY-PLAN")._prompt("o", "t", "")
    assert "PROJ-PLAN" in CliProjectPlanner(planning_rules="PROJ-PLAN")._prompt("goal")
    # no planning rules -> unchanged prompt (no section)
    assert "# Rules (planning)" not in CliPlanner()._prompt("o", "t", "")


# ─────────────────────────── unit: model routing ───────────────────────────
def test_resolve_engine_env_default_simulated(session, monkeypatch):
    monkeypatch.setenv("ASV3_AGENT_MODE", "simulated")
    assert governance.resolve_engine(session, "executor", None)["transport"] == "simulated"


def test_resolve_engine_env_default_real(session, monkeypatch):
    monkeypatch.setenv("ASV3_AGENT_MODE", "real")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert governance.resolve_engine(session, "executor", None) == {
        "transport": "claude-cli", "model": "claude-opus-4-8"
    }
    assert governance.resolve_engine(session, "ticket-planner", None)["transport"] == "claude-cli"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert governance.resolve_engine(session, "ticket-planner", None)["transport"] == "anthropic-api"


def test_resolve_engine_global_then_project_override(session):
    governance.set_global_models(session, {"executor": {"transport": "codex-cli", "model": "m1"}})
    assert governance.resolve_engine(session, "executor", None) == {"transport": "codex-cli", "model": "m1"}
    _seed_objective(session, "pm")
    governance.set_project_models(session, "pm", {"executor": {"transport": "simulated", "model": ""}})
    assert governance.resolve_engine(session, "executor", "pm")["transport"] == "simulated"  # project wins


def test_resolve_engine_unknown_transport_dropped_at_write(session, monkeypatch):
    monkeypatch.setenv("ASV3_AGENT_MODE", "simulated")
    governance.set_global_models(session, {"executor": {"transport": "bogus", "model": "m"}})
    assert governance.get_global_models(session) == {}  # _clean_models drops unknown transports
    assert governance.resolve_engine(session, "executor", None)["transport"] == "simulated"


def test_resolve_engine_unsupported_for_point_safe_fallback(session, monkeypatch):
    monkeypatch.setenv("ASV3_AGENT_MODE", "simulated")
    # anthropic-api is a real transport but has no EXECUTOR backend -> safe fallback to env default
    governance.set_global_models(session, {"executor": {"transport": "anthropic-api", "model": "m"}})
    assert governance.resolve_engine(session, "executor", None)["transport"] == "simulated"


def test_resolve_engine_codex_cli_supported_for_planner(session, monkeypatch):
    monkeypatch.setenv("ASV3_AGENT_MODE", "simulated")
    # codex-cli is now a wired planner backend (`codex exec`), so it RESOLVES (not a fallback).
    governance.set_global_models(session, {"ticket-planner": {"transport": "codex-cli", "model": "m"}})
    assert governance.resolve_engine(session, "ticket-planner", None) == {"transport": "codex-cli", "model": "m"}


def test_resolve_engine_invalid_project_override_falls_through_to_global(session, monkeypatch):
    monkeypatch.setenv("ASV3_AGENT_MODE", "simulated")
    governance.set_global_models(session, {"executor": {"transport": "codex-cli", "model": "gm"}})
    _seed_objective(session, "pfall")
    # anthropic-api is not a valid EXECUTOR transport -> skip the project tier and fall THROUGH
    # to the valid GLOBAL codex-cli (NOT straight to the env default).
    governance.set_project_models(session, "pfall", {"executor": {"transport": "anthropic-api", "model": "x"}})
    assert governance.resolve_engine(session, "executor", "pfall") == {"transport": "codex-cli", "model": "gm"}


def test_engine_factories():
    from app.services.executor import CliExecutor, SimulatedExecutor
    from app.services.planner import CliPlanner as _CP, SimulatedPlanner

    assert isinstance(
        governance.make_executor({"transport": "simulated", "model": ""}, sim_write=lambda r: None),
        SimulatedExecutor,
    )
    codex = governance.make_executor({"transport": "codex-cli", "model": "m"}, sim_write=lambda r: None)
    assert isinstance(codex, CliExecutor) and codex.brain == "codex"
    planner = governance.make_planner({"transport": "claude-cli", "model": "m"}, planning_rules="R")
    assert isinstance(planner, _CP) and planner.planning_rules == "R"
    assert isinstance(governance.make_planner({"transport": "simulated"}), SimulatedPlanner)


def test_available_engines_reports_status():
    by_t = {e["transport"]: e for e in governance.available_engines()}
    assert {"claude-cli", "codex-cli", "anthropic-api", "openai-api", "local", "simulated"} <= set(by_t)
    assert by_t["simulated"]["available"] is True and by_t["simulated"]["wired"] is True
    assert by_t["openai-api"]["wired"] is True and by_t["local"]["wired"] is True  # now wired (langchain-openai)


# ─────────────────────────────── API endpoints ──────────────────────────────
@pytest.fixture(scope="module", autouse=True)
def _env():
    os.environ["ASV3_AGENT_MODE"] = "simulated"
    init_db()


@pytest.fixture(autouse=True)
def _clean_global_settings():
    """Global rules/models live in the shared app DB and would otherwise leak into other
    test files (e.g. a global executor=codex would break the lifecycle tests). Clear them
    around each test here."""
    def _clear():
        db = SessionLocal()
        try:
            for key in ("rules.global", "models.global", "autonomy.global"):
                row = db.get(Setting, key)
                if row is not None:
                    db.delete(row)
            db.commit()
        finally:
            db.close()

    _clear()
    yield
    _clear()


@pytest.fixture()
def client():
    return TestClient(app)


def test_global_rules_endpoint_roundtrip(client):
    assert "DRY" in client.get("/rules").json()["coding"]  # seeded default
    put = client.put("/rules", json={"coding": "C-RULE", "planning": "P-RULE"})
    assert put.status_code == 200 and put.json() == {"coding": "C-RULE", "planning": "P-RULE"}
    assert client.get("/rules").json()["coding"] == "C-RULE"
    # partial update leaves the other axis intact
    client.put("/rules", json={"planning": "P2"})
    assert client.get("/rules").json() == {"coding": "C-RULE", "planning": "P2"}


def test_project_rules_endpoint_and_resolve(client):
    client.post("/projects/approve", json={"slug": "rgov", "title": "R", "tickets": [{"title": "T"}]})
    client.put("/rules", json={"coding": "GLOBAL-C"})
    body = client.put("/projects/rgov/rules", json={"coding": "PROJ-C"}).json()
    assert body["project"]["coding"] == "PROJ-C"
    assert body["global"]["coding"] == "GLOBAL-C"
    assert "GLOBAL-C" in body["resolved"]["coding"] and "PROJ-C" in body["resolved"]["coding"]
    assert client.put("/projects/nope/rules", json={"coding": "x"}).status_code == 404


def test_global_models_endpoints(client):
    g = client.get("/models").json()
    assert "executor" in g["points"] and "claude-cli" in g["transports"]
    client.put("/models", json={"models": {"executor": {"transport": "codex-cli", "model": "m"}}})
    assert client.get("/models").json()["global"]["executor"] == {"transport": "codex-cli", "model": "m"}


def test_project_models_resolve_endpoint(client):
    client.post("/projects/approve", json={"slug": "mgov", "title": "M", "tickets": [{"title": "T"}]})
    body = client.put(
        "/projects/mgov/models",
        json={"models": {"executor": {"transport": "simulated", "model": ""}}},
    ).json()
    assert body["project"]["executor"]["transport"] == "simulated"
    assert body["resolved"]["executor"]["transport"] == "simulated"
    assert client.put("/projects/nope/models", json={"models": {}}).status_code == 404


def test_models_available_endpoint(client):
    transports = {e["transport"] for e in client.get("/models/available").json()}
    assert {"claude-cli", "anthropic-api", "simulated", "openai-api", "local"} <= transports
