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
