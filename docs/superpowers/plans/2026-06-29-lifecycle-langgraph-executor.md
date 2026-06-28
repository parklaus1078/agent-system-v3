# Lifecycle (LangGraph) + Planner + Headless Executor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Use Karpathy-skill to think about how to write the actual codes.

**Goal:** Make the ticket lifecycle real: a **LangGraph StateGraph** (`plan → execute_step → review-interrupt → loop`) with a **Postgres checkpointer**, a **Planner** (LangChain `ChatAnthropic` structured output) that proposes steps, and a **headless Executor** (`claude -p` / `codex`) that does each step in the target repo, committing per step and ingesting the diff into the work graph (Plan 2). Replaces the frontend's Plan/Review mock calls with real endpoints.

**Architecture:** One StateGraph per ticket, keyed by `thread_id = "ticket:{id}"`, checkpointed in Postgres (`langgraph-checkpoint-postgres`). `interrupt()` implements the plan-approval gate and the per-step review gate; the API resumes the graph with `Command(resume=...)`. The Planner is an Anthropic API call (it only reasons, returns a validated step list). The Executor is the agentic **CLI** (it edits files) run headless in the target repo; a **SimulatedExecutor** (writes a known diff) makes the whole loop testable with zero model quota. Diff→graph reuses Plan 2's `apply_step_diff`.

**Tech Stack:** Python 3.12, LangGraph + `langgraph-checkpoint-postgres` (`PostgresSaver`), `langchain-anthropic` (`ChatAnthropic`), Pydantic v2, the Plan 2 FastAPI app + graph store + git ops. Model: `claude-opus-4-8`.

## Global Constraints

- Builds on Plan 2's `api/` package (graph store, `git/repo.py`, `apply_step_diff`, FastAPI app).
- **Model id is `claude-opus-4-8`.** Do NOT pass `temperature`/`top_p`/`top_k` to `ChatAnthropic` — they 400 on opus-4-8. Do NOT pass `thinking`/`budget_tokens`. Plain `ChatAnthropic(model="claude-opus-4-8")`.
- **Executor = agentic CLI, not the Anthropic API.** Real mode shells out to `claude -p <prompt>` (Claude Code, headless) or `codex` in the target repo with pre-authorized permissions. The Anthropic SDK/`ChatAnthropic` is the **Planner** only (§spec 5.1 boundary).
- **Determinism for tests:** `SimulatedExecutor` and `SimulatedPlanner` produce fixed output (no network, no quota). All graph/lifecycle tests use them.
- One commit per step in the target repo; `apply_step_diff` (Plan 2) turns the diff into graph edges. Idempotent.
- Every task ends green (`pytest`) and the API boots.

---

## File Structure

```
api/app/
  schemas_plan.py            # Pydantic: PlanProposal, StepSpec, ReviewAction
  services/
    planner.py              # Planner protocol + LangChainPlanner + SimulatedPlanner
    executor.py             # Executor protocol + CliExecutor + SimulatedExecutor
    prompt_build.py         # scoped prompt assembly (Objective + ticket + owned CodeRegions + decisions)
    lifecycle_graph.py      # StateGraph: plan/execute_step/review/ingest + PostgresSaver
  routers/
    lifecycle.py            # POST /tickets/{id}/plan|approve ; POST /steps/{id}/review ; GET /tickets/{id}/state
api/tests/
  test_planner.py  test_executor.py  test_prompt_build.py  test_lifecycle_graph.py  test_lifecycle_api.py
```

---

## Task 1: Plan/step/review schemas

**Files:** Create `api/app/schemas_plan.py`; Test `api/tests/test_schemas_plan.py`

**Interfaces:**
- Produces: `StepSpec(label:str, intent:str, acceptance:str)`, `PlanProposal(ticket_id:str, steps:list[StepSpec])`, `ReviewAction(kind:Literal["approve","changes","takeover"], comment:str|None=None)`.

- [ ] **Step 1: Failing test** `api/tests/test_schemas_plan.py`

```python
from app.schemas_plan import PlanProposal, ReviewAction

def test_plan_and_review_validate():
    p = PlanProposal(ticket_id="t1", steps=[{"label": "spec", "intent": "i", "acceptance": "a"}])
    assert p.steps[0].label == "spec"
    assert ReviewAction(kind="changes", comment="fix x").comment == "fix x"
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement `api/app/schemas_plan.py`**

```python
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel

class StepSpec(BaseModel):
    label: str
    intent: str
    acceptance: str

class PlanProposal(BaseModel):
    ticket_id: str
    steps: list[StepSpec]

class ReviewAction(BaseModel):
    kind: Literal["approve", "changes", "takeover"]
    comment: str | None = None
```

- [ ] **Step 4: Run, expect PASS. Commit** — `git add api/app/schemas_plan.py api/tests/test_schemas_plan.py && git commit -m "feat(api): plan/step/review schemas"`

---

## Task 2: Planner (LangChain structured output + simulated)

**Files:** Create `api/app/services/planner.py`; Test `api/tests/test_planner.py`

**Interfaces:**
- Produces: `class Planner(Protocol): def propose(self, objective:str, ticket_title:str, context:str) -> list[StepSpec]`; `SimulatedPlanner` (deterministic 3 steps); `LangChainPlanner` (real, `ChatAnthropic`).

- [ ] **Step 1: Failing test** (simulated only — no network) `api/tests/test_planner.py`

```python
from app.services.planner import SimulatedPlanner

def test_simulated_planner_returns_steps():
    steps = SimulatedPlanner().propose("Todo app", "할일 CRUD", context="")
    assert len(steps) >= 1
    assert all(s.label and s.intent and s.acceptance for s in steps)
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement `api/app/services/planner.py`**

```python
from __future__ import annotations
from typing import Protocol
from ..schemas_plan import StepSpec, PlanProposal

class Planner(Protocol):
    def propose(self, objective: str, ticket_title: str, context: str) -> list[StepSpec]: ...

class SimulatedPlanner:
    def propose(self, objective: str, ticket_title: str, context: str) -> list[StepSpec]:
        return [
            StepSpec(label="스펙·골격", intent=f"{ticket_title} 스펙 정리", acceptance="스펙 합의"),
            StepSpec(label="구현", intent=f"{ticket_title} 핵심 구현", acceptance="동작"),
            StepSpec(label="테스트", intent="테스트 추가", acceptance="그린"),
        ]

class LangChainPlanner:
    """Real planner. Anthropic API via LangChain, structured output forced to PlanProposal.
    Note: opus-4-8 rejects temperature/top_p/top_k/thinking — pass none of them."""
    def __init__(self, model: str = "claude-opus-4-8"):
        from langchain_anthropic import ChatAnthropic  # lazy import (network/dep optional in tests)
        self._llm = ChatAnthropic(model=model).with_structured_output(PlanProposal)

    def propose(self, objective: str, ticket_title: str, context: str) -> list[StepSpec]:
        prompt = (
            "You are a senior engineer. Break the ticket into small, independently reviewable steps "
            "(each = one atomic agent action = one commit). Return a PlanProposal.\n\n"
            f"## Objective (pinned)\n{objective}\n\n## Ticket\n{ticket_title}\n\n## Context\n{context}\n"
        )
        result: PlanProposal = self._llm.invoke(prompt)
        return result.steps
```

- [ ] **Step 4: Run, expect PASS. Commit** — `git add api/app/services/planner.py api/tests/test_planner.py && git commit -m "feat(api): planner (simulated + LangChain ChatAnthropic structured output)"`

---

## Task 3: Scoped prompt builder

**Files:** Create `api/app/services/prompt_build.py`; Test `api/tests/test_prompt_build.py`

**Interfaces:**
- Produces: `build_step_prompt(db, project_id, ticket_id, step: StepSpec, rag_context: str = "") -> str` → contains **only** the Objective (pinned), the ticket title/acceptance, the CodeRegions the ticket already owns, and neighbor Decisions — **not** the whole repo.

- [ ] **Step 1: Failing test** `api/tests/test_prompt_build.py`

```python
from app.graph.store import seed_graph
from app.services.prompt_build import build_step_prompt
from app.schemas_plan import StepSpec

def test_prompt_is_scoped_to_ticket_neighbors(session):
    seed_graph(session, "p1",
        nodes=[{"id":"obj","kind":"objective","label":"Todo 앱"},
               {"id":"t1","kind":"ticket","label":"게이팅","status":"executing"},
               {"id":"cr:x","kind":"code_region","label":"src/billing/flags.ts"},
               {"id":"d1","kind":"decision","label":"플래그로 분기"}],
        edges=[{"id":"e1","from":"obj","to":"t1","kind":"has"},
               {"id":"e2","from":"t1","to":"cr:x","kind":"touches"},
               {"id":"e3","from":"t1","to":"d1","kind":"decided"}])
    prompt = build_step_prompt(session, "p1", "t1", StepSpec(label="s", intent="i", acceptance="a"))
    assert "Todo 앱" in prompt and "src/billing/flags.ts" in prompt and "플래그로 분기" in prompt
    assert "전체 레포" not in prompt  # scoped, not whole-repo
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement `api/app/services/prompt_build.py`**

```python
from __future__ import annotations
from sqlalchemy.orm import Session
from ..graph.store import get_graph, neighbors
from ..models import Node
from ..schemas_plan import StepSpec

def _objective(db: Session, project_id: str) -> str:
    for n in get_graph(db, project_id)["nodes"]:
        if n["kind"] == "objective":
            return n["label"]
    return ""

def build_step_prompt(db: Session, project_id: str, ticket_id: str, step: StepSpec, rag_context: str = "") -> str:
    ticket = db.get(Node, ticket_id)
    owned = [n.label for n in neighbors(db, project_id, ticket_id, "out") if n.kind == "code_region"]
    decisions = [n.label for n in neighbors(db, project_id, ticket_id, "out") if n.kind == "decision"]
    parts = [
        f"# Objective (pinned)\n{_objective(db, project_id)}",
        f"# Ticket\n{ticket.label if ticket else ticket_id}",
        f"# Step\n{step.intent}\nAcceptance: {step.acceptance}",
        "# Code you own (edit only what this step needs)\n" + ("\n".join(f"- {p}" for p in owned) or "- (none yet)"),
        "# Prior decisions\n" + ("\n".join(f"- {d}" for d in decisions) or "- (none)"),
    ]
    if rag_context:
        parts.append(f"# Relevant prior knowledge (RAG)\n{rag_context}")
    return "\n\n".join(parts)
```

- [ ] **Step 4: Run, expect PASS. Commit** — `git add api/app/services/prompt_build.py api/tests/test_prompt_build.py && git commit -m "feat(api): scoped step-prompt builder"`

---

## Task 4: Executor (headless CLI + simulated)

**Files:** Create `api/app/services/executor.py`; Test `api/tests/test_executor.py`

**Interfaces:**
- Produces: `@dataclass ExecResult(summary:str, decision:str|None, ok:bool, output:str)`; `class Executor(Protocol): def run(self, repo_dir:str, prompt:str) -> ExecResult`; `SimulatedExecutor(write: callable)` (writes a known file via the callback, returns ok); `CliExecutor(brain, model, preset)` (real: `claude -p` / `codex` headless in `repo_dir`).

- [ ] **Step 1: Failing test** (simulated) `api/tests/test_executor.py`

```python
import subprocess
from pathlib import Path
from app.services.executor import SimulatedExecutor

def test_simulated_executor_writes_and_reports(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    def write(repo: str):
        Path(repo, "result.ts").write_text("export const ok = true;\n")
    res = SimulatedExecutor(write).run(str(tmp_path), prompt="anything")
    assert res.ok and (tmp_path / "result.ts").exists()
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement `api/app/services/executor.py`**

```python
from __future__ import annotations
import shlex
import subprocess
from dataclasses import dataclass
from typing import Callable, Protocol

@dataclass
class ExecResult:
    summary: str
    decision: str | None
    ok: bool
    output: str

class Executor(Protocol):
    def run(self, repo_dir: str, prompt: str) -> ExecResult: ...

class SimulatedExecutor:
    """Deterministic: invokes a write callback to mutate the repo, no model used."""
    def __init__(self, write: Callable[[str], None], decision: str | None = None):
        self._write, self._decision = write, decision
    def run(self, repo_dir: str, prompt: str) -> ExecResult:
        self._write(repo_dir)
        return ExecResult(summary="simulated step done", decision=self._decision, ok=True, output="")

class CliExecutor:
    """Real Executor: the agentic CLI edits files in repo_dir (headless, pre-authorized).
    Claude Code: `claude -p <prompt> --permission-mode acceptEdits`; Codex equivalent.
    The CLI flags below are the v1 baseline; verify against the installed CLI version."""
    def __init__(self, brain: str = "claude", model: str = "claude-opus-4-8", preset: str = "acceptEdits"):
        self.brain, self.model, self.preset = brain, model, preset
    def _cmd(self, prompt: str) -> list[str]:
        if self.brain == "claude":
            return ["claude", "-p", prompt, "--model", self.model, "--permission-mode", self.preset]
        return ["codex", "exec", "--model", self.model, prompt]
    def run(self, repo_dir: str, prompt: str) -> ExecResult:
        try:
            proc = subprocess.run(self._cmd(prompt), cwd=repo_dir, capture_output=True, text=True)  # noqa: S603
            return ExecResult(summary=(proc.stdout or "").strip()[:500], decision=None,
                              ok=proc.returncode == 0, output=proc.stdout + proc.stderr)
        except FileNotFoundError as exc:
            return ExecResult(summary="", decision=None, ok=False, output=str(exc))
```

- [ ] **Step 4: Run, expect PASS. Commit** — `git add api/app/services/executor.py api/tests/test_executor.py && git commit -m "feat(api): executor (simulated + headless CLI)"`

---

## Task 5: LangGraph lifecycle (StateGraph + PostgresSaver)

**Files:** Create `api/app/services/lifecycle_graph.py`; Test `api/tests/test_lifecycle_graph.py`

**Interfaces:**
- Produces: `build_graph(planner, executor, *, checkpointer=None)` → compiled StateGraph with nodes `plan`, `execute_step`, `review`, and conditional edges. State `TicketState = {project_id, ticket_id, repo_dir, objective, ticket_title, steps:list, current:int, decisions:list}`. The `plan` node `interrupt()`s for approval; the `review` node `interrupt()`s per step; `review` resumes with a `ReviewAction`-shaped dict.
- The graph calls back into the DB through injected functions (`on_steps_approved`, `on_step_committed`) so the graph stays pure-ish and testable; for tests these are in-memory recorders.

- [ ] **Step 1: Failing test** (in-memory checkpointer, simulated planner/executor, recorder callbacks) `api/tests/test_lifecycle_graph.py`

```python
from pathlib import Path
import subprocess
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from app.services.planner import SimulatedPlanner
from app.services.executor import SimulatedExecutor
from app.services.lifecycle_graph import build_graph

def test_plan_approve_then_review_each_step(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    committed = []
    ex = SimulatedExecutor(lambda repo: Path(repo, "f.ts").write_text("x\n"))
    graph = build_graph(
        planner=SimulatedPlanner(), executor=ex, checkpointer=MemorySaver(),
        on_steps_approved=lambda steps: None,
        on_step_committed=lambda i, sha, summary, decision: committed.append((i, summary)),
        commit_fn=lambda repo, msg: subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
                  or subprocess.run(["git", "commit", "-q", "-m", msg], cwd=repo, check=True)
                  or subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True).stdout.strip(),
    )
    cfg = {"configurable": {"thread_id": "ticket:1"}}
    state = {"project_id": "p1", "ticket_id": "t1", "repo_dir": str(tmp_path),
             "objective": "Todo", "ticket_title": "CRUD", "steps": [], "current": 0, "decisions": []}

    # 1) plan node interrupts for approval
    graph.invoke(state, cfg)
    snap = graph.get_state(cfg)
    assert snap.next  # interrupted (awaiting approval)

    # 2) approve decomposition → run first step → interrupt at review
    graph.invoke(Command(resume={"approve": True}), cfg)
    assert len(committed) == 1  # first step committed, now awaiting review

    # 3) approve each remaining step
    for _ in range(2):
        graph.invoke(Command(resume={"kind": "approve"}), cfg)
    assert len(committed) == 3
    assert not graph.get_state(cfg).next  # graph reached END
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement `api/app/services/lifecycle_graph.py`**

```python
from __future__ import annotations
from typing import Callable, TypedDict
from langgraph.graph import START, END, StateGraph
from langgraph.types import interrupt

class TicketState(TypedDict, total=False):
    project_id: str
    ticket_id: str
    repo_dir: str
    objective: str
    ticket_title: str
    steps: list
    current: int
    decisions: list

def build_graph(planner, executor, *, checkpointer=None,
                on_steps_approved: Callable[[list], None] = lambda s: None,
                on_step_committed: Callable[[int, str, str, str | None], None] = lambda *a: None,
                commit_fn: Callable[[str, str], str] = lambda repo, msg: "sha",
                build_prompt: Callable[[dict], str] | None = None):
    def plan(state: TicketState) -> dict:
        steps = planner.propose(state["objective"], state["ticket_title"], "")
        decision = interrupt({"type": "plan_approval", "steps": [s.model_dump() for s in steps]})
        if not decision.get("approve"):
            return {"steps": [], "current": 0}
        on_steps_approved(steps)
        return {"steps": [s.model_dump() for s in steps], "current": 0}

    def execute_step(state: TicketState) -> dict:
        i = state["current"]
        step = state["steps"][i]
        prompt = build_prompt(state) if build_prompt else f"{state['objective']}\n{step['intent']}"
        res = executor.run(state["repo_dir"], prompt)
        sha = commit_fn(state["repo_dir"], f"step {i + 1}: {step['label']}")
        on_step_committed(i, sha, res.summary, res.decision)
        return {}

    def review(state: TicketState) -> dict:
        action = interrupt({"type": "review", "step": state["current"]})
        kind = action.get("kind", "approve")
        if kind == "approve":
            return {"current": state["current"] + 1}
        if kind == "changes":
            return {}  # re-run same step (current unchanged)
        return {}  # takeover: stay for re-review

    def after_review(state: TicketState) -> str:
        return "execute_step" if state["current"] < len(state["steps"]) else END

    def after_plan(state: TicketState) -> str:
        return "execute_step" if state["steps"] else END

    g = StateGraph(TicketState)
    g.add_node("plan", plan)
    g.add_node("execute_step", execute_step)
    g.add_node("review", review)
    g.add_edge(START, "plan")
    g.add_conditional_edges("plan", after_plan, {"execute_step": "execute_step", END: END})
    g.add_edge("execute_step", "review")
    g.add_conditional_edges("review", after_review, {"execute_step": "execute_step", END: END})
    return g.compile(checkpointer=checkpointer)
```

- [ ] **Step 4: Run, expect PASS.**

- [ ] **Step 5: Commit** — `git add api/app/services/lifecycle_graph.py api/tests/test_lifecycle_graph.py && git commit -m "feat(api): LangGraph ticket lifecycle (plan/execute/review interrupts)"`

---

## Task 6: Lifecycle API + PostgresSaver wiring

**Files:** Create `api/app/routers/lifecycle.py`; Modify `api/app/main.py` (include router), `api/app/db.py` (provide checkpointer factory); Test `api/tests/test_lifecycle_api.py`

**Interfaces:**
- Endpoints (driving one graph per ticket via `thread_id="ticket:{id}"`):
  - `POST /tickets/{id}/plan` → start graph → returns the proposed steps (interrupt payload).
  - `POST /tickets/{id}/plan/approve` `{approve, steps?}` → resume → runs step 1 → returns review payload.
  - `POST /steps/{id}/review` `{kind, comment?}` → resume → next step or done.
  - `GET /tickets/{id}/state` → current graph state (which node, current step).
- Production checkpointer: `PostgresSaver.from_conn_string(DATABASE_URL)`; tests inject `MemorySaver`. The router uses simulated planner/executor when `ASV3_AGENT_MODE != "real"`, wiring `on_step_committed` → `apply_step_diff` (Plan 2) + `git.repo.diff_of_commit`.

- [ ] **Step 1: Failing test** `api/tests/test_lifecycle_api.py` (simulated mode, MemorySaver, real git temp repo)

```python
import subprocess
from fastapi.testclient import TestClient
from app.main import app
from app.db import init_db, SessionLocal
from app.graph.store import seed_graph

def setup_module():
    init_db()
    db = SessionLocal()
    seed_graph(db, "p1", nodes=[{"id":"obj","kind":"objective","label":"Todo"},
                                {"id":"t1","kind":"ticket","label":"CRUD","status":"planning"}],
                          edges=[{"id":"e1","from":"obj","to":"t1","kind":"has"}])
    db.close()

def test_plan_approve_review_cycle(tmp_path, monkeypatch):
    monkeypatch.setenv("ASV3_AGENT_MODE", "simulated")
    monkeypatch.setenv("ASV3_TARGET_REPO_p1_t1", str(tmp_path))
    subprocess.run(["git","init","-q"], cwd=tmp_path, check=True)
    subprocess.run(["git","config","user.email","t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git","config","user.name","t"], cwd=tmp_path, check=True)
    c = TestClient(app)
    plan = c.post("/tickets/t1/plan").json()
    assert len(plan["steps"]) >= 1
    r = c.post("/tickets/t1/plan/approve", json={"approve": True}).json()
    assert r["type"] in ("review", "done")
    # approve all remaining steps
    for _ in range(len(plan["steps"])):
        c.post("/steps/t1/review", json={"kind": "approve"})
    assert c.get("/tickets/t1/state").json()["done"] is True
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement `api/app/routers/lifecycle.py`** — one module-level dict of compiled graphs keyed by ticket id (built lazily). On build, inject `SimulatedPlanner`/`SimulatedExecutor` (or `LangChainPlanner`/`CliExecutor` when `ASV3_AGENT_MODE=real`), `commit_fn = git.repo.commit_all`, and `on_step_committed` that calls `git.repo.diff_of_commit` + `apply_step_diff` to update the work graph. `POST /tickets/{id}/plan` invokes the graph to the first interrupt and returns `graph.get_state(cfg).tasks[0].interrupts[0].value`. `approve`/`review` call `graph.invoke(Command(resume=...), cfg)` and return the next interrupt payload (or `{"type":"done"}`). `GET .../state` returns `{"done": not graph.get_state(cfg).next, "current": ...}`.

- [ ] **Step 4: Wire `main.py`** to include `lifecycle.router`. Provide `checkpointer()` in `db.py`: `PostgresSaver` for Postgres URLs, else `MemorySaver` (tests). Call `.setup()` on the PostgresSaver once at startup.

- [ ] **Step 5: Run, expect PASS.** Boot check: `uvicorn app.main:app`; `/docs` lists the lifecycle endpoints.

- [ ] **Step 6: Commit** — `git add api/app && git commit -m "feat(api): lifecycle endpoints driving the LangGraph (Postgres checkpointer)"`

---

## Task 7: Point the frontend Plan/Review at real endpoints

**Files:** Modify `web/src/api/http/HttpApiClient.ts` (implement `proposePlan`/`approvePlan`/`reviewStep`); Test `web/src/api/http/HttpApiClient.plan.test.ts`

**Interfaces:**
- `HttpApiClient.proposePlan(goal)` → `POST /tickets/{ticketId}/plan` (ticket created server-side from the goal — or pass an existing ticket id). `approvePlan` → `POST /tickets/{id}/plan/approve`. `reviewStep(stepId, action)` → `POST /steps/{id}/review`.

- [ ] **Step 1: Failing test** (mock fetch) asserting `reviewStep` POSTs the action body to `/steps/{id}/review`.

```ts
import { HttpApiClient } from './HttpApiClient';
test('reviewStep posts the action', async () => {
  const calls: any[] = [];
  vi.stubGlobal('fetch', vi.fn(async (url: string, init: any) => { calls.push([url, init]); return new Response('{}'); }));
  await new HttpApiClient('http://api', 'p1').reviewStep('s4', { kind: 'approve' });
  expect(calls[0][0]).toContain('/steps/s4/review');
  expect(JSON.parse(calls[0][1].body)).toEqual({ kind: 'approve' });
});
```

- [ ] **Step 2: Run, expect FAIL → implement the three methods (replace the `NotImplemented` throws from Plan 2) → PASS.**

- [ ] **Step 3: Manual E2E** — run api (simulated mode) + web (`VITE_API_BASE=...`): create goal → approve plan → review each step → map updates from real diffs. Compare to the wireframe.

- [ ] **Step 4: Commit** — `git add web/src/api && git commit -m "feat(web): wire plan/approve/review to the lifecycle API"`

---

## Self-Review (done at write time)

- **Spec coverage:** §7 StateGraph(T5) with interrupt=plan/review gates + cycle (changes re-runs same step) + PostgresSaver(T6); Planner=LangChain structured output(T2); Executor=headless CLI, NOT LangChain(T4); scoped context(T3); diff→graph reuse on commit(T6); frontend wired(T7). RAG/promotion = Plan 4.
- **Boundary honored:** `ChatAnthropic` only in `LangChainPlanner`; the Executor shells out to the CLI. ✔
- **Model constraints:** `ChatAnthropic(model="claude-opus-4-8")` with no temperature/thinking. ✔
- **Determinism:** all graph/API tests use `SimulatedPlanner`/`SimulatedExecutor` + a real temp git repo; zero quota. ✔
- **Type consistency:** `StepSpec`/`PlanProposal`/`ReviewAction` (T1) reused in planner/graph/router; `ExecResult`/`Executor` (T4) consumed by the graph (T5). ✔

## Notes for Plan 4

- `build_step_prompt` already accepts `rag_context` — Plan 4 fills it from the retriever.
- `on_step_committed` records `decision`; Plan 4 promotes `Decision` nodes to the cross-project wiki on completion.
- Real-mode `claude -p` permission flags are a v1 baseline (Task 4) — verify against the installed Claude Code version; pre-authorization detail lives in the spec's permission section.
