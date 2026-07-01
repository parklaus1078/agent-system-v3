"""CP0 governance: the two human-managed config axes for every AI call.

  * Rules  — *what* conventions are injected (coding rules -> executor prompt,
             planning rules -> planner prompts).
  * Models — *who* runs each intervention point (the {transport, model} routing table
             that replaces the old `ASV3_AGENT_MODE`/`ASV3_BRAIN` + "key? then API" branch).

Both axes are **global default + per-project override**. Global lives in the `settings`
table; the per-project override lives on the Objective node's `data` (`data.rules`,
`data.models`). Resolution merges them. Secret API keys are NEVER stored here — they stay in
the environment (open question #8); only availability/status is surfaced.
"""

from __future__ import annotations

import logging
import os
import shutil
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Node, Setting
from .executor import CliExecutor, SimulatedExecutor
from .intent import CliIntentRouter, LangChainIntentRouter, SimulatedIntentRouter
from .llm import API_TRANSPORTS, brain_of
from .planner import (
    CliPlanner,
    CliProjectPlanner,
    LangChainPlanner,
    LangChainProjectPlanner,
    SimulatedPlanner,
    SimulatedProjectPlanner,
)

logger = logging.getLogger("asv3.governance")

# ── Intervention points (the "who" axis). project-planner/ticket-planner/executor are
# wired this CP; intent-router (CP3) and agent-message-gen (CP2) get a routing slot now
# even though nothing calls them yet, so the table is already shaped for them. ──
POINTS: tuple[str, ...] = (
    "project-planner",
    "ticket-planner",
    "executor",
    "intent-router",
    "agent-message-gen",
)

# transport values the routing table understands.
TRANSPORTS: tuple[str, ...] = (
    "claude-cli",
    "codex-cli",
    "anthropic-api",
    "openai-api",
    "local",
    "simulated",
)

# Which transports each point can actually run on. Every LLM-*completion* point (planners,
# intent-router, agent-message-gen) runs on ANY transport — CLI (claude/codex), API
# (anthropic/openai), a local OpenAI-compatible endpoint, or the deterministic simulated stub.
# The EXECUTOR is the exception: it edits files as an agentic CLI, so it stays CLI/simulated
# (an anthropic/openai/local executor would need a full agentic file-editing loop — out of scope).
_COMPLETION_ALL = frozenset(
    {"claude-cli", "codex-cli", "anthropic-api", "openai-api", "local", "simulated"}
)
SUPPORTED: dict[str, frozenset[str]] = {
    "project-planner": _COMPLETION_ALL,
    "ticket-planner": _COMPLETION_ALL,
    "executor": frozenset({"claude-cli", "codex-cli", "simulated"}),
    "intent-router": _COMPLETION_ALL,
    "agent-message-gen": _COMPLETION_ALL,
}


def supported_map() -> dict[str, list[str]]:
    """Per-point allow-list of transports that actually resolve — the Models page uses this to
    only offer valid transports per point (a transport outside this set is silently ignored by
    _resolve_one and falls through, which reads as 'my setting didn't apply')."""
    return {p: sorted(SUPPORTED.get(p, WIRED_TRANSPORTS)) for p in POINTS}

# Transports with a real engine behind them. openai-api + local (OpenAI-compatible) are now
# wired via langchain-openai for every completion point; only their env config (key / base_url)
# gates real availability, reported by available_engines().
WIRED_TRANSPORTS: frozenset[str] = frozenset(
    {"claude-cli", "codex-cli", "anthropic-api", "openai-api", "local", "simulated"}
)

DEFAULT_MODEL = "claude-opus-4-8"

# Rules size guard (open question #7 default: full-text injection + a size guard). Past this
# the merged rules text is truncated with a marker + a WARNING — a token-cost backstop, not a
# hard limit. RAG-selected injection is a follow-up TODO.
MAX_RULES_CHARS = 20_000

_RULES_KEY = "rules.global"
_MODELS_KEY = "models.global"
_AUTONOMY_KEY = "autonomy.global"

# CP1 throttle levels (the autonomy dial). Default = per-step (= today's forced review gate).
AUTONOMY_LEVELS: tuple[str, ...] = ("auto", "co-pilot", "per-step")
DEFAULT_AUTONOMY = "per-step"
# api/app/services/governance.py -> parents[3] == repo root
_CODING_SEED_PATH = Path(__file__).resolve().parents[3] / "docs" / "general_coding_rules.md"

_EMPTY_RULES = {"coding": "", "planning": ""}


# ──────────────────────────────────────────────────────────────────────────────
# settings table helpers
# ──────────────────────────────────────────────────────────────────────────────
def _get_setting(db: Session, key: str) -> dict | None:
    row = db.get(Setting, key)
    return dict(row.value) if row and row.value else None


def _put_setting(db: Session, key: str, value: dict) -> None:
    row = db.get(Setting, key)
    if row is None:
        db.add(Setting(key=key, value=value))
    else:
        row.value = value
    db.commit()


def _objective(db: Session, pid: str) -> Node | None:
    return db.scalars(
        select(Node).where(Node.project_id == pid, Node.kind == "objective")
    ).first()


# ──────────────────────────────────────────────────────────────────────────────
# A. Rules
# ──────────────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=1)
def _seed_coding_rules() -> str:
    """The shipped general_coding_rules.md, imported as the global coding-rules default.
    Cached: it's a static repo file, read at most once per process."""
    try:
        return _CODING_SEED_PATH.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):  # missing OR mis-encoded -> degrade, don't 500
        logger.warning("coding-rules seed unreadable at %s", _CODING_SEED_PATH)
        return ""


def get_global_rules(db: Session) -> dict:
    """Global {coding, planning}. When nothing has been saved yet, coding defaults to the
    shipped general_coding_rules.md (planning empty) so the Rules page opens pre-populated.
    This is a PURE READ — the default is computed, not persisted (avoids a write on every
    resolve/read path); `set_global_rules` (the explicit PUT) is what persists."""
    stored = _get_setting(db, _RULES_KEY)
    if stored is None:
        return {"coding": _seed_coding_rules(), "planning": ""}
    return {"coding": stored.get("coding", ""), "planning": stored.get("planning", "")}


def set_global_rules(
    db: Session, coding: str | None = None, planning: str | None = None
) -> dict:
    """Update global rules. A `None` field is left unchanged (so the UI can save one axis)."""
    cur = get_global_rules(db)
    if coding is not None:
        cur["coding"] = coding
    if planning is not None:
        cur["planning"] = planning
    _put_setting(db, _RULES_KEY, cur)
    return cur


def get_project_rules(db: Session, pid: str) -> dict:
    """The project's rules override (stored on Objective.data.rules); empty strings = none."""
    obj = _objective(db, pid)
    r = (obj.data or {}).get("rules") if obj else None
    r = r or {}
    return {"coding": r.get("coding", ""), "planning": r.get("planning", "")}


def set_project_rules(
    db: Session, pid: str, coding: str | None = None, planning: str | None = None
) -> dict | None:
    """Set the project's rules override. Returns None if the project (Objective) is absent."""
    obj = _objective(db, pid)
    if obj is None:
        return None
    data = dict(obj.data or {})
    rules = dict(data.get("rules") or {})
    if coding is not None:
        rules["coding"] = coding
    if planning is not None:
        rules["planning"] = planning
    data["rules"] = rules
    obj.data = data  # reassign so SQLAlchemy tracks the JSON change
    db.commit()
    return {"coding": rules.get("coding", ""), "planning": rules.get("planning", "")}


def _guard(text: str) -> str:
    if len(text) > MAX_RULES_CHARS:
        logger.warning(
            "rules text %d chars exceeds guard %d — truncating", len(text), MAX_RULES_CHARS
        )
        return text[:MAX_RULES_CHARS] + "\n\n[... rules truncated: exceeded size guard ...]"
    return text


def _merge_rule(global_text: str, project_text: str) -> str:
    """Global default + project override appended (both apply), size-guarded. The project
    override is the POINT of the feature, so it is never the first thing dropped: when the
    merged text exceeds the guard it is the GLOBAL segment that gets truncated, not the
    override (only an override that alone exceeds the guard is itself truncated)."""
    g = (global_text or "").strip()
    p = (project_text or "").strip()
    if not (g and p):
        return _guard(g or p)
    header = "\n\n# Project-specific rules\n"
    budget = MAX_RULES_CHARS - len(header) - len(p)
    if budget <= 0:
        return _guard(p)  # the override alone is over budget -> guard the override itself
    if len(g) > budget:
        marker = "\n…[global rules truncated to preserve the project override]"
        logger.warning(
            "global rules truncated to preserve project override (guard=%d)", MAX_RULES_CHARS
        )
        g = g[: max(0, budget - len(marker))] + marker
    return f"{g}{header}{p}"


def resolve_rules(db: Session, pid: str | None) -> dict:
    """Effective {coding, planning} for a project: global default with the project override
    appended. `pid=None` (e.g. project-level planning, before a project exists) -> global
    only. This is what gets injected into prompts."""
    g = get_global_rules(db)
    p = get_project_rules(db, pid) if pid else dict(_EMPTY_RULES)
    return {
        "coding": _merge_rule(g["coding"], p["coding"]),
        "planning": _merge_rule(g["planning"], p["planning"]),
    }


# ──────────────────────────────────────────────────────────────────────────────
# C. Autonomy / throttle (CP1) — same global-default + project-override storage as rules
# ──────────────────────────────────────────────────────────────────────────────
def _valid_level(level: str | None) -> str | None:
    return level if level in AUTONOMY_LEVELS else None


def get_global_autonomy(db: Session) -> str:
    """Global throttle default: a saved Setting, else `ASV3_THROTTLE` env, else per-step."""
    stored = _get_setting(db, _AUTONOMY_KEY)
    if stored and _valid_level(stored.get("level")):
        return stored["level"]
    return _valid_level(os.environ.get("ASV3_THROTTLE")) or DEFAULT_AUTONOMY


def set_global_autonomy(db: Session, level: str) -> str:
    level = _valid_level(level) or DEFAULT_AUTONOMY
    _put_setting(db, _AUTONOMY_KEY, {"level": level})
    return level


def get_project_autonomy(db: Session, pid: str) -> str | None:
    """The project's throttle override (Objective.data.autonomy), or None to inherit global."""
    obj = _objective(db, pid)
    return _valid_level((obj.data or {}).get("autonomy")) if obj else None


def set_project_autonomy(db: Session, pid: str, level: str | None) -> str | None:
    """Set/clear the project's throttle override. A null/invalid level CLEARS it (inherit
    global). Returns the EFFECTIVE level, or None if the project (Objective) is absent."""
    obj = _objective(db, pid)
    if obj is None:
        return None
    data = dict(obj.data or {})
    valid = _valid_level(level)
    if valid:
        data["autonomy"] = valid
    else:
        data.pop("autonomy", None)
    obj.data = data  # reassign so SQLAlchemy tracks the JSON change
    db.commit()
    return resolve_autonomy(db, pid)


def get_ticket_autonomy(db: Session, pid: str, tid: str) -> str | None:
    """A ticket's throttle override (Node.data.autonomy), or None to inherit project/global."""
    t = db.get(Node, tid)
    if t is None or t.project_id != pid or t.kind != "ticket":
        return None
    return _valid_level((t.data or {}).get("autonomy"))


def set_ticket_autonomy(db: Session, pid: str, tid: str, level: str | None) -> str | None:
    """Set/clear a ticket's throttle override. Null/invalid CLEARS it (inherit project/global).
    Returns the EFFECTIVE level, or None if the ticket is absent."""
    t = db.get(Node, tid)
    if t is None or t.project_id != pid or t.kind != "ticket":
        return None
    data = dict(t.data or {})
    valid = _valid_level(level)
    if valid:
        data["autonomy"] = valid
    else:
        data.pop("autonomy", None)
    t.data = data  # reassign so SQLAlchemy tracks the JSON change
    db.commit()
    return resolve_autonomy(db, pid, tid)


def resolve_autonomy(db: Session, pid: str | None, tid: str | None = None) -> str:
    """Effective throttle: ticket override (CP4) -> project override -> global default.
    Unset ticket/project cleanly fall back (no CP1 regression)."""
    if pid and tid:
        lvl = get_ticket_autonomy(db, pid, tid)
        if lvl:
            return lvl
    return (get_project_autonomy(db, pid) if pid else None) or get_global_autonomy(db)


# ──────────────────────────────────────────────────────────────────────────────
# B. Model routing
# ──────────────────────────────────────────────────────────────────────────────
def _env_default_engine(point: str) -> dict:
    """The engine today's env logic picks — the back-compat default used when no global/
    project routing is configured. Preserves the `ASV3_AGENT_MODE=simulated` path and the
    "ANTHROPIC_API_KEY? then API, else CLI" behavior, now made explicit."""
    mode = os.environ.get("ASV3_AGENT_MODE", "simulated")
    if mode != "real":
        return {"transport": "simulated", "model": ""}
    brain = os.environ.get("ASV3_BRAIN", "claude")
    if point in ("project-planner", "ticket-planner"):
        if os.environ.get("ANTHROPIC_API_KEY"):
            return {"transport": "anthropic-api", "model": DEFAULT_MODEL}
        return {"transport": "claude-cli", "model": DEFAULT_MODEL}
    if point == "executor":
        return {
            "transport": "codex-cli" if brain == "codex" else "claude-cli",
            "model": DEFAULT_MODEL,
        }
    # intent-router / agent-message-gen: nothing calls them yet -> simulated placeholder.
    return {"transport": "simulated", "model": ""}


def _clean_models(models: dict) -> dict:
    """Keep only known points with a known transport; coerce model to a string. Unknown
    points/transports are dropped (input validation — never trust the payload)."""
    out: dict[str, dict] = {}
    for point, spec in (models or {}).items():
        if point not in POINTS:
            continue
        transport = (spec or {}).get("transport")
        if transport not in TRANSPORTS:
            continue
        out[point] = {"transport": transport, "model": str((spec or {}).get("model") or "")}
    return out


def get_global_models(db: Session) -> dict:
    return _get_setting(db, _MODELS_KEY) or {}


def set_global_models(db: Session, models: dict) -> dict:
    cleaned = _clean_models(models)
    _put_setting(db, _MODELS_KEY, cleaned)
    return cleaned


def get_project_models(db: Session, pid: str) -> dict:
    obj = _objective(db, pid)
    return dict((obj.data or {}).get("models") or {}) if obj else {}


def set_project_models(db: Session, pid: str, models: dict) -> dict | None:
    obj = _objective(db, pid)
    if obj is None:
        return None
    data = dict(obj.data or {})
    data["models"] = _clean_models(models)
    obj.data = data  # reassign so SQLAlchemy tracks the JSON change
    db.commit()
    return data["models"]


def _resolve_one(point: str, project_models: dict, global_models: dict) -> dict:
    """Resolve {transport, model} for a point from already-fetched project/global tables.
    Precedence: project override > global config > env-derived default. Each tier is SKIPPED
    if its transport is unknown / not supported-or-wired for this point, so an invalid project
    override falls THROUGH to a valid global engine (not straight to the env default), and an
    unsupported transport never strands a run."""
    supported = SUPPORTED.get(point, WIRED_TRANSPORTS)
    for chosen in (project_models.get(point), global_models.get(point)):
        if not chosen:
            continue
        transport = chosen.get("transport")
        if transport not in supported:
            logger.warning(
                "engine[%s]: transport %r not supported/wired for this point -> next tier",
                point, transport,
            )
            continue
        model = chosen.get("model") or ("" if transport == "simulated" else DEFAULT_MODEL)
        return {"transport": transport, "model": model}
    return _env_default_engine(point)


def resolve_engine(db: Session, point: str, pid: str | None = None) -> dict:
    """Resolve {transport, model} for one intervention point (see _resolve_one)."""
    return _resolve_one(
        point, get_project_models(db, pid) if pid else {}, get_global_models(db)
    )


def resolve_all(db: Session, pid: str | None, points: tuple[str, ...]) -> dict:
    """Resolve rules + engines for several points with the MINIMUM number of queries — the
    project Objective fetched ONCE and the two global Settings ONCE — instead of re-querying
    per point. Used on the request hot path so governance resolution adds little DB
    contention to the shared in-memory connection during background execution.
    Returns {"rules": {coding, planning}, "engines": {point: {transport, model}}}."""
    obj = _objective(db, pid) if pid else None
    obj_data = (obj.data or {}) if obj else {}
    proj_rules = obj_data.get("rules") or {}
    proj_models = obj_data.get("models") or {}
    g_rules = get_global_rules(db)
    g_models = get_global_models(db)
    rules = {
        "coding": _merge_rule(g_rules["coding"], proj_rules.get("coding", "")),
        "planning": _merge_rule(g_rules["planning"], proj_rules.get("planning", "")),
    }
    return {
        "rules": rules,
        "engines": {p: _resolve_one(p, proj_models, g_models) for p in points},
    }


def available_engines() -> list[dict]:
    """Per-transport health for the Models page: is the CLI on PATH / the API key present?
    Never returns the secret values themselves — only presence/status (open question #8)."""
    have_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))
    have_openai = bool(os.environ.get("OPENAI_API_KEY"))
    local_base = os.environ.get("ASV3_LOCAL_BASE_URL")
    claude_cli = shutil.which("claude") is not None
    codex_cli = shutil.which("codex") is not None
    return [
        {"transport": "simulated", "wired": True, "available": True, "detail": "deterministic offline stub"},
        {"transport": "claude-cli", "wired": True, "available": claude_cli,
         "detail": "`claude` on PATH" if claude_cli else "`claude` CLI not found on PATH"},
        {"transport": "codex-cli", "wired": True, "available": codex_cli,
         "detail": "`codex` on PATH" if codex_cli else "`codex` CLI not found on PATH"},
        {"transport": "anthropic-api", "wired": True, "available": have_anthropic,
         "detail": "ANTHROPIC_API_KEY set" if have_anthropic else "ANTHROPIC_API_KEY not set"},
        {"transport": "openai-api", "wired": True, "available": have_openai,
         "detail": "OPENAI_API_KEY set" if have_openai else "OPENAI_API_KEY not set"},
        {"transport": "local", "wired": True, "available": bool(local_base),
         "detail": f"OpenAI-compatible endpoint {local_base}" if local_base
                   else "set ASV3_LOCAL_BASE_URL (OpenAI-compatible / ollama)"},
    ]


# ──────────────────────────────────────────────────────────────────────────────
# Engine factories — transport -> concrete planner/executor (the only place the routing
# table meets the implementation classes, so lifecycle.py / projects.py stay declarative).
# ──────────────────────────────────────────────────────────────────────────────
# Completion points (planners / intent-router) build across ALL transports: API
# (anthropic/openai/local) via LangChain, CLI (claude/codex) via subprocess, else simulated.
# The executor stays CLI/simulated (no API file-editing backend).
def make_project_planner(engine: dict, *, planning_rules: str = ""):
    transport = engine["transport"]
    model = engine.get("model") or DEFAULT_MODEL
    if transport in API_TRANSPORTS:
        return LangChainProjectPlanner(model=model, planning_rules=planning_rules, transport=transport)
    if transport in ("claude-cli", "codex-cli"):
        return CliProjectPlanner(brain=brain_of(transport), model=model, planning_rules=planning_rules)
    return SimulatedProjectPlanner()


def make_planner(engine: dict, *, planning_rules: str = ""):
    transport = engine["transport"]
    model = engine.get("model") or DEFAULT_MODEL
    if transport in API_TRANSPORTS:
        return LangChainPlanner(model=model, planning_rules=planning_rules, transport=transport)
    if transport in ("claude-cli", "codex-cli"):
        return CliPlanner(brain=brain_of(transport), model=model, planning_rules=planning_rules)
    return SimulatedPlanner()


def make_intent_router(engine: dict):
    """Intent router for the `intent-router` point across all transports: API (anthropic/openai/
    local) via LangChain, CLI (claude/codex) via subprocess, else the deterministic rule router."""
    transport = engine["transport"]
    model = engine.get("model") or DEFAULT_MODEL
    if transport in API_TRANSPORTS:
        return LangChainIntentRouter(model=model, transport=transport)
    if transport in ("claude-cli", "codex-cli"):
        return CliIntentRouter(brain=brain_of(transport), model=model)
    return SimulatedIntentRouter()


def make_executor(engine: dict, *, sim_write):
    transport = engine["transport"]
    model = engine.get("model") or DEFAULT_MODEL
    if transport == "simulated":
        return SimulatedExecutor(sim_write)
    if transport == "codex-cli":
        return CliExecutor(brain="codex", model=model)
    if transport == "claude-cli":
        return CliExecutor(brain="claude", model=model)
    # anthropic-api/openai-api/local have no executor backend; resolve_engine already
    # restricts executor to CLI/simulated, but guard anyway so a stray spec can't crash.
    logger.warning("executor transport %r has no backend -> claude-cli", transport)
    return CliExecutor(brain="claude", model=model)
