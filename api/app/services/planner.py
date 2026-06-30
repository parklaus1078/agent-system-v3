from __future__ import annotations

import json
import logging
import re
import subprocess
import time
from typing import Protocol

from ..schemas_plan import StepSpec, PlanProposal, ProjectProposal, TicketSpec

logger = logging.getLogger("asv3.planner")


def slugify(text: str, fallback: str = "project") -> str:
    """A URL-safe slug from arbitrary text. Non-ascii (e.g. Korean) collapses away, so a
    fallback keeps the slug non-empty; uniqueness is enforced separately at persist time."""
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:40].strip("-") or fallback


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
        logger.info(
            "planner[%s] spawn: model=%s objective=%r ticket=%r prompt=%dch",
            self.brain, self.model, objective[:60], ticket_title[:60], len(prompt),
        )
        t0 = time.monotonic()
        proc = subprocess.run(  # noqa: S603
            ["claude", "-p", prompt, "--model", self.model],
            capture_output=True,
            text=True,
        )
        ms = int((time.monotonic() - t0) * 1000)
        logger.info("planner[%s] exit: rc=%d %dms out=%dch", self.brain, proc.returncode, ms, len(proc.stdout or ""))
        if proc.returncode != 0:
            logger.warning("planner[%s] stderr: %s", self.brain, (proc.stderr or "")[-400:])
            raise RuntimeError(f"claude planner failed (exit {proc.returncode}): {proc.stderr[:300]}")
        steps = self._parse(proc.stdout)
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
    """Real project planner — Anthropic API via LangChain, structured output forced to
    ProjectProposal (mirrors LangChainPlanner; needs ANTHROPIC_API_KEY)."""

    def __init__(self, model: str = "claude-opus-4-8"):
        from langchain_anthropic import ChatAnthropic  # lazy: dep/network optional in tests

        self._llm = ChatAnthropic(model=model).with_structured_output(ProjectProposal)

    def propose_project(self, goal: str) -> ProjectProposal:
        prompt = (
            "You are a senior tech lead. Turn the raw goal into a project: a short url-safe "
            "slug (lowercase, hyphens), a human title, and 2-5 tickets (each a coherent unit "
            "of work, later sub-divided into steps). Return a ProjectProposal.\n\n"
            f"## Goal\n{goal}\n"
        )
        return self._llm.invoke(prompt)


class CliProjectPlanner:
    """Real project planner over the agentic CLI (`claude -p`) — same Claude Code OAuth as
    the executor, so real mode works with no ANTHROPIC_API_KEY (mirrors CliPlanner)."""

    def __init__(self, brain: str = "claude", model: str = "claude-opus-4-8"):
        self.brain, self.model = brain, model

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
        prompt = (
            "Turn this raw goal into a project. Respond with ONLY a JSON object with keys "
            '"slug" (lowercase, hyphenated, url-safe), "title" (short human title), and '
            '"tickets" (array of 2-5 objects, each {"title","intent"}). No markdown, no prose.\n\n'
            f"Goal: {goal}\n"
        )
        logger.info("project-planner[%s] spawn: model=%s goal=%r", self.brain, self.model, goal[:80])
        t0 = time.monotonic()
        proc = subprocess.run(  # noqa: S603
            ["claude", "-p", prompt, "--model", self.model],
            capture_output=True,
            text=True,
        )
        ms = int((time.monotonic() - t0) * 1000)
        logger.info("project-planner[%s] exit: rc=%d %dms", self.brain, proc.returncode, ms)
        if proc.returncode != 0:
            logger.warning("project-planner[%s] stderr: %s", self.brain, (proc.stderr or "")[-400:])
            raise RuntimeError(f"claude project-planner failed (exit {proc.returncode}): {proc.stderr[:300]}")
        proposal = self._parse(proc.stdout, goal)
        logger.info("project-planner[%s] proposed slug=%s tickets=%d", self.brain, proposal.slug, len(proposal.tickets))
        return proposal
