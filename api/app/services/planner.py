from __future__ import annotations

import json
import logging
import re
from typing import Protocol

from ..schemas_plan import StepSpec, PlanProposal, ProjectProposal, TicketSpec

logger = logging.getLogger("asv3.planner")


def slugify(text: str, fallback: str = "project") -> str:
    """A URL-safe slug from arbitrary text. Non-ascii (e.g. Korean) collapses away, so a
    fallback keeps the slug non-empty; uniqueness is enforced separately at persist time."""
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:40].strip("-") or fallback


def with_planning_rules(prompt: str, planning_rules: str) -> str:
    """Prepend the human-managed `# Rules (planning)` section (CP0 governance) to a planner
    prompt. No rules -> the prompt is returned unchanged."""
    rules = (planning_rules or "").strip()
    if not rules:
        return prompt
    return f"# Rules (planning)\n{rules}\n\n{prompt}"


class Planner(Protocol):
    def propose(self, objective: str, ticket_title: str, context: str) -> list[StepSpec]: ...


class ProjectPlanner(Protocol):
    """Project-level planner: a raw goal -> {slug, title, tickets[]} (no steps yet)."""

    def propose_project(self, goal: str) -> ProjectProposal: ...


class SimulatedPlanner:
    """Deterministic planner (no network/quota) — used in tests and simulated mode."""

    def propose(self, objective: str, ticket_title: str, context: str) -> list[StepSpec]:
        return [
            StepSpec(label="스펙·골격", intent=f"{ticket_title} 스펙 정리", acceptance="스펙 합의"),
            StepSpec(label="구현", intent=f"{ticket_title} 핵심 구현", acceptance="동작"),
            StepSpec(label="테스트", intent="테스트 추가", acceptance="그린"),
        ]


class LangChainPlanner:
    """Real planner over an API transport (anthropic-api / openai-api / local) via LangChain,
    structured output forced to PlanProposal."""

    def __init__(
        self, model: str = "claude-opus-4-8", planning_rules: str = "", transport: str = "anthropic-api"
    ):
        from . import llm  # lazy: provider SDKs optional in tests/offline

        self.planning_rules = planning_rules
        self._llm = llm.make_chat_model(transport, model).with_structured_output(PlanProposal)

    def _prompt(self, objective: str, ticket_title: str, context: str) -> str:
        base = (
            "You are a senior engineer. Break the ticket into small, independently "
            "reviewable steps (each = one atomic agent action = one commit). Return a "
            "PlanProposal.\n\n"
            f"## Objective (pinned)\n{objective}\n\n"
            f"## Ticket\n{ticket_title}\n\n"
            f"## Context\n{context}\n"
        )
        return with_planning_rules(base, self.planning_rules)

    def propose(self, objective: str, ticket_title: str, context: str) -> list[StepSpec]:
        result: PlanProposal = self._llm.invoke(self._prompt(objective, ticket_title, context))
        return result.steps


class CliPlanner:
    """Real planner over an agentic CLI (`claude -p` or `codex exec`) — uses the SAME auth as the
    CliExecutor (Claude Code / Codex OAuth), so real mode works where there is no
    ANTHROPIC_API_KEY for the LangChain/API path."""

    def __init__(
        self, brain: str = "claude", model: str = "claude-opus-4-8", planning_rules: str = ""
    ):
        self.brain, self.model, self.planning_rules = brain, model, planning_rules

    def _prompt(self, objective: str, ticket_title: str, context: str) -> str:
        base = (
            "Break the ticket into 2-5 small, independently reviewable steps (each = one "
            "atomic agent action = one commit). Respond with ONLY a JSON array, each element "
            'an object with keys "label","intent","acceptance". No markdown, no prose.\n\n'
            f"Objective: {objective}\nTicket: {ticket_title}\n"
            + (f"Context:\n{context}\n" if context else "")
        )
        return with_planning_rules(base, self.planning_rules)

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
        from . import llm  # lazy

        prompt = self._prompt(objective, ticket_title, context)
        steps = self._parse(llm.run_cli(self.brain, self.model, prompt, what="planner"))
        logger.info("planner[%s] proposed %d steps", self.brain, len(steps))
        return steps


class SimulatedProjectPlanner:
    """Deterministic project planner (no network/quota) — used in tests and simulated mode.
    Derives a slug+title from the goal and proposes a small, generic ticket breakdown."""

    def propose_project(self, goal: str) -> ProjectProposal:
        title = (goal or "").strip().splitlines()[0][:60] if (goal or "").strip() else "새 프로젝트"
        return ProjectProposal(
            slug=slugify(title),
            title=title,
            tickets=[
                TicketSpec(title="핵심 기능 구현", intent=f"{title} 핵심 동작"),
                TicketSpec(title="데이터·저장", intent="영속/스토리지 계층"),
                TicketSpec(title="테스트·검증", intent="테스트 추가 및 수용 기준 확인"),
            ],
        )


class LangChainProjectPlanner:
    """Real project planner over an API transport via LangChain, structured output forced to
    ProjectProposal (mirrors LangChainPlanner)."""

    def __init__(
        self, model: str = "claude-opus-4-8", planning_rules: str = "", transport: str = "anthropic-api"
    ):
        from . import llm  # lazy: provider SDKs optional in tests/offline

        self.planning_rules = planning_rules
        self._llm = llm.make_chat_model(transport, model).with_structured_output(ProjectProposal)

    def _prompt(self, goal: str) -> str:
        base = (
            "You are a senior tech lead. Turn the raw goal into a project: a short url-safe "
            "slug (lowercase, hyphens), a human title, and 2-5 tickets (each a coherent unit "
            "of work, later sub-divided into steps). Return a ProjectProposal.\n\n"
            f"## Goal\n{goal}\n"
        )
        return with_planning_rules(base, self.planning_rules)

    def propose_project(self, goal: str) -> ProjectProposal:
        return self._llm.invoke(self._prompt(goal))


class CliProjectPlanner:
    """Real project planner over the agentic CLI (`claude -p`) — same Claude Code OAuth as
    the executor, so real mode works with no ANTHROPIC_API_KEY (mirrors CliPlanner)."""

    def __init__(
        self, brain: str = "claude", model: str = "claude-opus-4-8", planning_rules: str = ""
    ):
        self.brain, self.model, self.planning_rules = brain, model, planning_rules

    def _prompt(self, goal: str) -> str:
        base = (
            "Turn this raw goal into a project. Respond with ONLY a JSON object with keys "
            '"slug" (lowercase, hyphenated, url-safe), "title" (short human title), and '
            '"tickets" (array of 2-5 objects, each {"title","intent"}). No markdown, no prose.\n\n'
            f"Goal: {goal}\n"
        )
        return with_planning_rules(base, self.planning_rules)

    @staticmethod
    def _parse(raw: str, goal: str) -> ProjectProposal:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            raise ValueError(f"no JSON object in project-planner output: {raw[:200]!r}")
        obj = json.loads(m.group(0))
        title = str(obj.get("title") or goal).strip()[:60] or "새 프로젝트"
        tickets = [
            TicketSpec(title=str(t.get("title", "")), intent=str(t.get("intent", "")))
            for t in (obj.get("tickets") or [])
            if t.get("title")
        ]
        if not tickets:
            raise ValueError("project-planner produced no tickets")
        return ProjectProposal(slug=slugify(str(obj.get("slug") or title)), title=title, tickets=tickets)

    def propose_project(self, goal: str) -> ProjectProposal:
        from . import llm  # lazy

        prompt = self._prompt(goal)
        proposal = self._parse(llm.run_cli(self.brain, self.model, prompt, what="project-planner"), goal)
        logger.info("project-planner[%s] proposed slug=%s tickets=%d", self.brain, proposal.slug, len(proposal.tickets))
        return proposal
