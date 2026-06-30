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
    title: str | None = None


class PlanStartIn(BaseModel):
    title: str | None = None  # for a new goal: the ticket title/objective text


class PlanApproveIn(BaseModel):
    # optional human-edited steps; omit to accept the proposed plan verbatim
    steps: list[PlanStep] | None = None
    title: str | None = None  # optional edited ticket title (persisted if the ticket is new)


class ProjectPlanIn(BaseModel):
    goal: str


class TicketProposal(BaseModel):
    title: str
    intent: str = ""


class ProjectProposalOut(BaseModel):
    slug: str
    title: str
    tickets: list[TicketProposal] = []


class ProjectApproveIn(BaseModel):
    slug: str
    title: str
    tickets: list[TicketProposal] = []
    description: str | None = None


class ProjectCreatedOut(BaseModel):
    projectId: str
    title: str
    tickets: int  # number of tickets created
    created: bool  # False if the slug already existed (idempotent no-op)


class ProjectInfoOut(BaseModel):
    projectId: str
    repoDir: str
    repoSource: str  # override | workspace | legacy | default — where repoDir came from


class ProjectRepoIn(BaseModel):
    repoDir: str | None = None  # set the project's target repo; null/empty -> revert to default


class Pos(BaseModel):
    x: float
    y: float


class LayoutIn(BaseModel):
    # node id -> position; drag&drop persistence (Phase 4)
    positions: dict[str, Pos]


class LayoutOut(BaseModel):
    updated: int


class LifecycleStateOut(BaseModel):
    ticketId: str
    next: list[str] = []
    done: bool = False
    current: int | None = None
    steps: list[PlanStep] = []
    awaiting: dict | None = None  # the pending interrupt payload (plan_approval | review)
