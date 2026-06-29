from __future__ import annotations

from pydantic import BaseModel, Field


class NodeOut(BaseModel):
    id: str
    kind: str
    label: str
    status: str | None = None
    data: dict = {}


class EdgeOut(BaseModel):
    # `from` is a Python keyword; alias covers both validation and serialization.
    model_config = {"populate_by_name": True}
    id: str
    from_: str = Field(alias="from")
    to: str
    kind: str


class GraphOut(BaseModel):
    nodes: list[NodeOut]
    edges: list[EdgeOut]


class DiffBlob(BaseModel):
    path: str
    patch: str = ""


class Acceptance(BaseModel):
    text: str
    met: bool = False


class StepDetailOut(BaseModel):
    node: NodeOut
    diff: list[DiffBlob] = []
    decision: str | None = None
    acceptance: list[Acceptance] = []
    createdNodeIds: list[str] = []
    createdEdgeIds: list[str] = []


class ReviewActionIn(BaseModel):
    kind: str  # approve | changes | takeover
    comment: str | None = None


class PlanStep(BaseModel):
    label: str
    intent: str = ""
    acceptance: str = ""


class ProposeIn(BaseModel):
    goal: str


class PlanProposalOut(BaseModel):
    ticketId: str
    steps: list[PlanStep] = []


class ApproveIn(BaseModel):
    ticketId: str
    steps: list[PlanStep] = []
