"""Model routing: per-point `supported` transports are exposed, and an unsupported override is
silently ignored (falls back) — the root of the 'my model setting didn't apply' confusion."""

import os

import pytest
from fastapi.testclient import TestClient

from app.db import init_db
from app.main import app


@pytest.fixture(scope="module", autouse=True)
def _env():
    os.environ["ASV3_AGENT_MODE"] = "simulated"
    init_db()


@pytest.fixture()
def client():
    return TestClient(app)


def test_models_view_exposes_per_point_supported(client):
    v = client.get("/models").json()
    assert "supported" in v
    # completion points now support ALL transports; the executor stays CLI/simulated (no API executor)
    assert "codex-cli" in v["supported"]["project-planner"]
    assert "openai-api" in v["supported"]["intent-router"]
    assert "local" in v["supported"]["agent-message-gen"]
    assert set(v["supported"]["executor"]) == {"claude-cli", "codex-cli", "simulated"}


def test_supported_transport_override_actually_applies(client):
    slug = "mdl-ok"
    client.post("/projects/approve", json={"slug": slug, "title": "T", "tickets": [{"title": "a"}]})
    client.put(
        f"/projects/{slug}/models",
        json={"models": {"executor": {"transport": "claude-cli", "model": "claude-sonnet-4-5"}}},
    )
    v = client.get(f"/projects/{slug}/models").json()
    assert v["project"]["executor"] == {"transport": "claude-cli", "model": "claude-sonnet-4-5"}
    assert v["resolved"]["executor"] == {"transport": "claude-cli", "model": "claude-sonnet-4-5"}  # reflected


def test_completion_points_apply_any_transport(client):
    slug = "mdl-mtx"
    client.post("/projects/approve", json={"slug": slug, "title": "T", "tickets": [{"title": "a"}]})
    # codex-cli planner + openai-api intent-router now RESOLVE (full matrix for completion points)
    client.put(
        f"/projects/{slug}/models",
        json={"models": {
            "project-planner": {"transport": "codex-cli", "model": "o1"},
            "intent-router": {"transport": "openai-api", "model": "gpt-4o"},
            "agent-message-gen": {"transport": "local", "model": "llama3"},
        }},
    )
    v = client.get(f"/projects/{slug}/models").json()
    assert v["resolved"]["project-planner"] == {"transport": "codex-cli", "model": "o1"}
    assert v["resolved"]["intent-router"] == {"transport": "openai-api", "model": "gpt-4o"}
    assert v["resolved"]["agent-message-gen"] == {"transport": "local", "model": "llama3"}


def test_unsupported_transport_is_stored_but_resolves_to_a_fallback(client):
    slug = "mdl-fb"
    client.post("/projects/approve", json={"slug": slug, "title": "T", "tickets": [{"title": "a"}]})
    # anthropic-api is NOT an executor backend (no API file-editing) -> stored but must not resolve to it
    client.put(
        f"/projects/{slug}/models",
        json={"models": {"executor": {"transport": "anthropic-api", "model": "x"}}},
    )
    v = client.get(f"/projects/{slug}/models").json()
    assert v["project"]["executor"]["transport"] == "anthropic-api"  # stored as the user set it
    assert v["resolved"]["executor"]["transport"] == "simulated"  # ...but falls back (not applied)
    assert "anthropic-api" not in v["supported"]["executor"]  # and the UI is told why
