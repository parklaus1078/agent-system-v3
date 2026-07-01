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


class TicketSpec(BaseModel):
    """One ticket in a project proposal (project planner -> tickets, no steps yet)."""

    title: str
    intent: str = ""


class ProjectProposal(BaseModel):
    """The project planner's output: a URL slug, a human title, and the tickets the
    project decomposes into (each later sub-divided into steps via the ticket planner)."""

    slug: str
    title: str
    tickets: list[TicketSpec]


class ReviewAction(BaseModel):
    kind: Literal["approve", "changes", "takeover"]
    comment: str | None = None
