from __future__ import annotations

import logging
from typing import Callable, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .executor import Executor
from .planner import Planner

logger = logging.getLogger("asv3.lifecycle.graph")


class TicketState(TypedDict, total=False):
    project_id: str
    ticket_id: str
    repo_dir: str
    objective: str
    ticket_title: str
    existing_steps: list[dict]  # a re-planned ticket's current steps (seeds the proposal)
    proposed: list[dict]   # the proposed plan (computed once, before the approval gate)
    steps: list[dict]      # StepSpec dicts (JSON-serializable for the checkpointer)
    current: int           # index of the step being executed / reviewed
    decisions: list[str]   # decisions accreted across steps
    last_summary: str
    last_ok: bool          # did the most recent step's executor succeed (co-pilot stops if not)
    review_needed: bool    # an explicit "stop & ask" signal from a step (CP2/CP3 hook; unset v1)
    autonomy: str          # throttle in effect for this run — checkpointed so the review gate
                           # decision is stable across an interrupt/resume (the dial can change)
    review_comment: str    # a changes/answer comment — injected into the NEXT re-run's prompt
    review_kind: str       # last review action: approve | changes | takeover


# Callback signatures (the API layer injects DB/git-backed implementations):
StepsApproved = Callable[[list[dict]], None]
StepStart = Callable[[int, int], None]            # (index, total) — about to execute a step
StepCommitted = Callable[[int, Optional[str], str, Optional[str], bool], None]
CommitFn = Callable[[str, str], str]              # (repo_dir, message) -> sha
BuildPrompt = Callable[[TicketState, dict], str]  # (state, step) -> prompt


def _noop_steps(steps: list[dict]) -> None:  # pragma: no cover - trivial default
    return None


def _noop_start(i: int, total: int) -> None:  # pragma: no cover - trivial default
    return None


def _noop_committed(i: int, sha, summary: str, decision: Optional[str], ok: bool = True) -> None:  # pragma: no cover
    return None


def build_graph(
    *,
    planner: Planner,
    executor: Executor,
    checkpointer,
    commit_fn: CommitFn,
    on_steps_approved: StepsApproved = _noop_steps,
    on_step_start: StepStart = _noop_start,
    on_step_committed: StepCommitted = _noop_committed,
    build_prompt: Optional[BuildPrompt] = None,
    autonomy: str = "per-step",
):
    """Compile the per-ticket lifecycle StateGraph.

    Flow: propose -> approve(gate) -> execute_step -> review(gate) -> execute_step -> ... -> END.
    `approve` always interrupt()s; `review` interrupts only when the `autonomy` throttle says to
    stop (CP1): `per-step` stops every step (today); `auto` never stops on success and runs the
    whole ticket in one invoke; `co-pilot` auto-advances but stops on a failed step or the final
    step. A stop is the same human gate as before — resume via Command(resume=...).
    `propose` is a SEPARATE node from `approve` so the (possibly expensive, real-Claude)
    planner runs exactly ONCE: on resume LangGraph re-runs only the interrupting node, and
    the proposal is already checkpointed in state — so the executed plan is the approved plan.
    Side effects (planning the graph, committing, ingesting diffs) are injected so the
    graph stays pure and testable with SimulatedPlanner/SimulatedExecutor + MemorySaver.
    """

    def propose(state: TicketState) -> dict:
        # Re-planning an existing ticket: surface its current steps for editing rather
        # than discarding them for a fresh generic proposal (matches the mock client).
        existing = state.get("existing_steps")
        if existing:
            return {"proposed": list(existing)}
        context = "\n".join(state.get("decisions", []))
        proposed = [
            s.model_dump()
            for s in planner.propose(state["objective"], state["ticket_title"], context)
        ]
        return {"proposed": proposed}

    def approve(state: TicketState) -> dict:
        proposed = state.get("proposed", [])
        decision = interrupt(
            {"type": "plan_approval", "ticketId": state.get("ticket_id"), "steps": proposed}
        )
        if decision.get("approve") is False and not decision.get("steps"):
            return {"steps": [], "current": 0}
        final = decision.get("steps") or proposed
        on_steps_approved(final)
        return {"steps": final, "current": 0}

    def after_approve(state: TicketState) -> str:
        return "execute_step" if state.get("steps") else END

    def execute_step(state: TicketState) -> dict:
        i = state["current"]
        step = state["steps"][i]
        on_step_start(i, len(state["steps"]))  # mark "executing step i+1/n" before the (slow) run
        prompt = build_prompt(state, step) if build_prompt else step.get("intent", "")
        res = executor.run(state["repo_dir"], prompt)
        logger.info(
            "execute_step %d (%s): ok=%s repo=%s%s",
            i + 1, step.get("label", ""), res.ok, state["repo_dir"],
            "" if res.ok else f" — executor failed: {(res.output or '')[-300:]}",
        )
        sha = commit_fn(state["repo_dir"], f"step {i + 1}: {step.get('label', '')}")
        on_step_committed(i, sha, res.summary, res.decision, res.ok)
        decisions = list(state.get("decisions", []))
        if res.decision:
            decisions.append(res.decision)
        # Persist the throttle in effect so review()'s gate decision is reproduced exactly on
        # resume (LangGraph re-runs the node from the top; the closure `autonomy` could differ
        # if the dial was changed mid-stop, which would drop the human's resumed action).
        return {
            "last_summary": res.summary, "decisions": decisions, "last_ok": res.ok,
            "autonomy": autonomy, "review_comment": "",  # consumed by this run's prompt; clear it
        }

    def review(state: TicketState) -> dict:
        i = state["current"]
        last_ok = state.get("last_ok", True)
        is_last = i + 1 >= len(state["steps"])
        eff_autonomy = state.get("autonomy", autonomy)  # checkpointed -> stable across resume
        # CP1 throttle: decide whether this step needs a human gate. per-step always stops; a
        # failed step or an explicit review-needed signal always stops; co-pilot also stops on
        # the final step; otherwise auto/co-pilot auto-advance with NO interrupt.
        must_stop = (
            eff_autonomy == "per-step"
            or not last_ok
            or state.get("review_needed", False)
            or (eff_autonomy == "co-pilot" and is_last)
        )
        if not must_stop:
            return {"current": i + 1, "review_kind": "approve"}  # auto-advance (no human gate)
        action = interrupt({"type": "review", "step": i, "summary": state.get("last_summary", "")})
        kind = action.get("kind", "approve")
        if kind == "approve":
            return {"current": i + 1, "review_kind": "approve"}
        # changes/takeover: keep the current index; carry the comment so a `changes` re-run's
        # prompt gets the reviewer's/answerer's guidance (consumed + cleared by execute_step).
        return {"review_kind": kind, "review_comment": action.get("comment") or ""}

    def after_review(state: TicketState) -> str:
        kind = state.get("review_kind")
        if kind == "changes":
            return "execute_step"      # re-run the same step
        if kind == "takeover":
            return END                 # human drives from here
        return "execute_step" if state["current"] < len(state["steps"]) else END

    g = StateGraph(TicketState)
    g.add_node("propose", propose)
    g.add_node("approve", approve)
    g.add_node("execute_step", execute_step)
    g.add_node("review", review)
    g.add_edge(START, "propose")
    g.add_edge("propose", "approve")
    g.add_conditional_edges("approve", after_approve, ["execute_step", END])
    g.add_edge("execute_step", "review")
    g.add_conditional_edges("review", after_review, ["execute_step", END])
    return g.compile(checkpointer=checkpointer)
