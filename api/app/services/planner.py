from __future__ import annotations

import json
import re
import subprocess
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


class CliPlanner:
    """Real planner over the agentic CLI (`claude -p`) — uses the SAME auth as the
    CliExecutor (Claude Code OAuth), so real mode works where there is no
    ANTHROPIC_API_KEY for the LangChain/API path."""

    def __init__(self, brain: str = "claude", model: str = "claude-opus-4-8"):
        self.brain, self.model = brain, model

    @staticmethod
    def _parse(raw: str) -> list[StepSpec]:
        """Extract the JSON array of steps from CLI stdout (with or without a code fence)."""
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if not m:
            raise ValueError(f"no JSON array in planner output: {raw[:200]!r}")
        items = json.loads(m.group(0))
        return [
            StepSpec(
                label=str(it.get("label", "")),
                intent=str(it.get("intent", "")),
                acceptance=str(it.get("acceptance", "")),
            )
            for it in items
            if it.get("label")
        ]

    def propose(self, objective: str, ticket_title: str, context: str) -> list[StepSpec]:
        prompt = (
            "Break the ticket into 2-5 small, independently reviewable steps (each = one "
            "atomic agent action = one commit). Respond with ONLY a JSON array, each element "
            'an object with keys "label","intent","acceptance". No markdown, no prose.\n\n'
            f"Objective: {objective}\nTicket: {ticket_title}\n"
            + (f"Context:\n{context}\n" if context else "")
        )
        proc = subprocess.run(  # noqa: S603
            ["claude", "-p", prompt, "--model", self.model],
            capture_output=True,
            text=True,
        )
        return self._parse(proc.stdout)
