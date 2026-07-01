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


class ProjectMetaIn(BaseModel):
    title: str | None = None  # None = leave unchanged
    description: str | None = None  # None = unchanged; "" = clear


class ProjectMetaOut(BaseModel):
    projectId: str
    title: str
    description: str | None = None


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


# ────────────────────────── CP0 governance (rules + model routing) ──────────────────────────
class RulesIn(BaseModel):
    # None = leave that axis unchanged (so the UI can save just one of coding/planning)
    coding: str | None = None
    planning: str | None = None


class RulesScope(BaseModel):
    coding: str = ""
    planning: str = ""


class ProjectRulesOut(BaseModel):
    """The Rules page's three views for a project: its own override, the global default, and
    the effective (merged) rules actually injected into prompts."""

    model_config = {"populate_by_name": True}
    project: RulesScope
    global_: RulesScope = Field(alias="global")
    resolved: RulesScope


class EngineSpec(BaseModel):
    # `model` would collide with pydantic's protected `model_` namespace — opt out.
    model_config = {"protected_namespaces": ()}
    transport: str
    model: str = ""


class ModelsIn(BaseModel):
    models: dict[str, EngineSpec] = {}


class GlobalModelsOut(BaseModel):
    model_config = {"populate_by_name": True}
    points: list[str]
    transports: list[str]
    supported: dict[str, list[str]] = {}  # per-point allow-list of transports that actually resolve
    global_: dict[str, EngineSpec] = Field(default_factory=dict, alias="global")


class ProjectModelsOut(BaseModel):
    """The Models page's views for a project: its override, the global profile, the effective
    (resolved) engine per point, plus the point/transport vocabularies for the table."""

    model_config = {"populate_by_name": True}
    points: list[str]
    transports: list[str]
    supported: dict[str, list[str]] = {}  # per-point allow-list of transports that actually resolve
    project: dict[str, EngineSpec] = {}
    global_: dict[str, EngineSpec] = Field(default_factory=dict, alias="global")
    resolved: dict[str, EngineSpec]


class ModelAvailability(BaseModel):
    transport: str
    wired: bool       # has a real engine behind it this CP (vs. an adapter stub)
    available: bool   # the CLI/API key it needs is present right now
    detail: str


# ───────────────────────────── CP1 autonomy / throttle ─────────────────────────────
class AutonomyIn(BaseModel):
    # auto | co-pilot | per-step. For the project endpoint, null/invalid CLEARS the override
    # (inherit global); for the global endpoint it falls back to the default (per-step).
    level: str | None = None


class AutonomyOut(BaseModel):
    level: str  # the (global) throttle level


class ProjectAutonomyOut(BaseModel):
    model_config = {"populate_by_name": True}
    levels: list[str]                 # the vocabulary, for the dial
    project: str | None = None        # the override, or null when inheriting global
    global_: str = Field(alias="global")
    resolved: str                     # the effective level driving the lifecycle


class TicketAutonomyOut(BaseModel):
    model_config = {"populate_by_name": True}
    levels: list[str]
    ticket: str | None = None         # the ticket override (CP4), or null
    project: str | None = None        # the project override, or null
    global_: str = Field(alias="global")
    resolved: str                     # effective: ticket -> project -> global


# ───────────────────────────── CP2 conversation channel ─────────────────────────────
class MessageOut(BaseModel):
    id: int                  # monotonic cursor for ?since=
    type: str                # assumption | blocked | decision | review | steer | system | clarify
    author: str              # agent | user | system
    text: str
    refs: list[str] = []     # referenced node ids
    ts: str                  # ISO-8601 created-at


# ───────────────────────────── CP3 steer (intent router) ─────────────────────────────
class SteerIn(BaseModel):
    text: str
    ticketId: str | None = None  # explicit scope from the UI's current selection (optional)
    stepId: str | None = None


class SteerOut(BaseModel):
    op: str                  # redirect | constrain | answer | control | clarify
    scope: dict = {}
    result: dict = {}        # op-specific outcome (e.g. new steps, node id, autonomy)
