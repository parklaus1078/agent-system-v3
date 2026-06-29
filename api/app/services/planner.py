from __future__ import annotations

from typing import Protocol

from ..schemas_plan import StepSpec, PlanProposal


class Planner(Protocol):
    def propose(self, objective: str, ticket_title: str, context: str) -> list[StepSpec]: ...


class SimulatedPlanner:
    """Deterministic planner (no network/quota) — used in tests and simulated mode."""

    def propose(self, objective: str, ticket_title: str, context: str) -> list[StepSpec]:
        return [
            StepSpec(label="스펙·골격", intent=f"{ticket_title} 스펙 정리", acceptance="스펙 합의"),
            StepSpec(label="구현", intent=f"{ticket_title} 핵심 구현", acceptance="동작"),
            StepSpec(label="테스트", intent="테스트 추가", acceptance="그린"),
        ]


class LangChainPlanner:
    """Real planner — the Anthropic API via LangChain, structured output forced to
    PlanProposal. opus-4-8 rejects temperature/top_p/top_k/thinking — pass none."""

    def __init__(self, model: str = "claude-opus-4-8"):
        from langchain_anthropic import ChatAnthropic  # lazy: dep/network optional in tests

        self._llm = ChatAnthropic(model=model).with_structured_output(PlanProposal)

    def propose(self, objective: str, ticket_title: str, context: str) -> list[StepSpec]:
        prompt = (
            "You are a senior engineer. Break the ticket into small, independently "
            "reviewable steps (each = one atomic agent action = one commit). Return a "
            "PlanProposal.\n\n"
            f"## Objective (pinned)\n{objective}\n\n"
            f"## Ticket\n{ticket_title}\n\n"
            f"## Context\n{context}\n"
        )
        result: PlanProposal = self._llm.invoke(prompt)
        return result.steps
