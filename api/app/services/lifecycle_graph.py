from __future__ import annotations

from typing import Callable, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .executor import Executor
from .planner import Planner


class TicketState(TypedDict, total=False):
    project_id: str
    ticket_id: str
    repo_dir: str
    objective: str
    ticket_title: str
    steps: list[dict]      # StepSpec dicts (JSON-serializable for the checkpointer)
    current: int           # index of the step being executed / reviewed
    decisions: list[str]   # decisions accreted across steps
    last_summary: str
    review_kind: str       # last review action: approve | changes | takeover


# Callback signatures (the API layer injects DB/git-backed implementations):
StepsApproved = Callable[[list[dict]], None]
StepCommitted = Callable[[int, str, str, Optional[str]], None]
CommitFn = Callable[[str, str], str]              # (repo_dir, message) -> sha
BuildPrompt = Callable[[TicketState, dict], str]  # (state, step) -> prompt


def _noop_steps(steps: list[dict]) -> None:  # pragma: no cover - trivial default
    return None


def _noop_committed(i: int, sha: str, summary: str, decision: Optional[str]) -> None:  # pragma: no cover
    return None


def build_graph(
    *,
    planner: Planner,
    executor: Executor,
    checkpointer,
    commit_fn: CommitFn,
    on_steps_approved: StepsApproved = _noop_steps,
    on_step_committed: StepCommitted = _noop_committed,
    build_prompt: Optional[BuildPrompt] = None,
):
    """Compile the per-ticket lifecycle StateGraph.

    Flow: plan -[approve]-> execute_step -> review -[approve]-> execute_step -> ... -> END.
    Both `plan` and `review` interrupt() for a human gate; resume via Command(resume=...).
    Side effects (planning the graph, committing, ingesting diffs) are injected so the
    graph stays pure and testable with SimulatedPlanner/SimulatedExecutor + MemorySaver.
    """

    def plan(state: TicketState) -> dict:
        context = "\n".join(state.get("decisions", []))
        proposed = [
            s.model_dump()
            for s in planner.propose(state["objective"], state["ticket_title"], context)
        ]
        decision = interrupt(
            {"type": "plan_approval", "ticketId": state.get("ticket_id"), "steps": proposed}
        )
        if decision.get("approve") is False and not decision.get("steps"):
            return {"steps": [], "current": 0}
        final = decision.get("steps") or proposed
        on_steps_approved(final)
        return {"steps": final, "current": 0}

    def after_plan(state: TicketState) -> str:
        return "execute_step" if state.get("steps") else END

    def execute_step(state: TicketState) -> dict:
        i = state["current"]
        step = state["steps"][i]
        prompt = build_prompt(state, step) if build_prompt else step.get("intent", "")
        res = executor.run(state["repo_dir"], prompt)
        sha = commit_fn(state["repo_dir"], f"step {i + 1}: {step.get('label', '')}")
        on_step_committed(i, sha, res.summary, res.decision)
        decisions = list(state.get("decisions", []))
        if res.decision:
            decisions.append(res.decision)
        return {"last_summary": res.summary, "decisions": decisions}

    def review(state: TicketState) -> dict:
        action = interrupt(
            {"type": "review", "step": state["current"], "summary": state.get("last_summary", "")}
        )
        kind = action.get("kind", "approve")
        if kind == "approve":
            return {"current": state["current"] + 1, "review_kind": "approve"}
        return {"review_kind": kind}  # changes/takeover: keep current index

    def after_review(state: TicketState) -> str:
        kind = state.get("review_kind")
        if kind == "changes":
            return "execute_step"      # re-run the same step
        if kind == "takeover":
            return END                 # human drives from here
        return "execute_step" if state["current"] < len(state["steps"]) else END

    g = StateGraph(TicketState)
    g.add_node("plan", plan)
    g.add_node("execute_step", execute_step)
    g.add_node("review", review)
    g.add_edge(START, "plan")
    g.add_conditional_edges("plan", after_plan, ["execute_step", END])
    g.add_edge("execute_step", "review")
    g.add_conditional_edges("review", after_review, ["execute_step", END])
    return g.compile(checkpointer=checkpointer)
