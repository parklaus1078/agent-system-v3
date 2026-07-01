import type { GraphNode } from '../domain/graph';

export interface DiffBlob {
  path: string;
  patch: string;
}
export interface Acceptance {
  text: string;
  met: boolean;
}
export interface StepDetail {
  node: GraphNode;
  diff: DiffBlob[];
  decision?: string;
  acceptance: Acceptance[];
  createdNodeIds: string[];
  createdEdgeIds: string[];
}
export type ReviewAction =
  | { kind: 'approve' }
  | { kind: 'changes'; comment: string }
  | { kind: 'takeover' };
export interface PlanProposal {
  ticketId: string;
  steps: { label: string; intent: string; acceptance: string }[];
  title?: string; // for a new goal, the label of the ticket to create
}
export interface ProjectInfo {
  projectId: string;
  repoDir: string; // resolved target repo the project's executor commits into
  repoSource: 'override' | 'workspace' | 'legacy' | 'default';
}
export interface ProjectSummary {
  projectId: string; // the route param (/project/{projectId})
  title: string;
  description?: string | null;
  tickets: number;
  steps: number;
  awaiting: number;
}
/** A ticket in a project proposal (project planner output; no steps yet). */
export interface TicketProposal {
  title: string;
  intent?: string;
}
/** The project planner's proposal for a raw goal — edited then approved on the landing. */
export interface ProjectProposal {
  slug: string; // url id (editable, pre-deduplicated by the backend)
  title: string;
  tickets: TicketProposal[];
  description?: string;
}
/** Result of creating a project (POST /projects/approve). */
export interface ProjectCreated {
  projectId: string; // the created (or merged) slug -> route param
  title: string;
  tickets: number;
  created: boolean; // false if the slug already existed (idempotent no-op)
}
/** A project's editable metadata (title + description). */
export interface ProjectMeta {
  projectId: string;
  title: string;
  description?: string | null;
}
/** Result of deleting a project (mapping data + optionally the repo directory). */
export interface ProjectDeleted {
  projectId: string;
  nodes: number;
  edges: number;
  messages: number;
  directoryRemoved: boolean; // true only when delete_directory was requested AND the dir was removed
}

// ───────────────────────────── CP0 governance ─────────────────────────────
/** Human-managed rules text injected into prompts (coding -> executor, planning -> planners). */
export interface Rules {
  coding: string;
  planning: string;
}
/** The Rules page's three views for a project. `resolved` is what actually reaches prompts. */
export interface ProjectRules {
  project: Rules;
  global: Rules;
  resolved: Rules;
}
/** Which engine runs an intervention point. */
export interface EngineSpec {
  transport: string;
  model: string;
}
/** point id -> engine. */
export type ModelsMap = Record<string, EngineSpec>;
export interface GlobalModels {
  points: string[];
  transports: string[];
  supported: Record<string, string[]>; // per-point allow-list of transports that actually resolve
  global: ModelsMap;
}
/** The Models page's views for a project (override + global + effective + vocab). */
export interface ProjectModels {
  points: string[];
  transports: string[];
  supported: Record<string, string[]>; // per-point allow-list of transports that actually resolve
  project: ModelsMap;
  global: ModelsMap;
  resolved: ModelsMap;
}
/** Per-transport health for the Models page (no secret values, only status). */
export interface ModelAvailability {
  transport: string;
  wired: boolean; // has a real engine behind it this CP (vs. an adapter stub)
  available: boolean; // the CLI/API key it needs is present right now
  detail: string;
}

// ───────────────────────────── CP2 conversation channel ─────────────────────────────
// agent->human (CP2) + human->agent/system (CP3 steer).
export type MessageType =
  | 'assumption'
  | 'blocked'
  | 'decision'
  | 'review'
  | 'steer'
  | 'system'
  | 'clarify';
export interface ChannelMessage {
  id: number; // monotonic cursor for ?since=
  type: MessageType;
  author: 'agent' | 'user' | 'system';
  text: string;
  refs: string[]; // referenced node ids (e.g. the step a review/blocked message is about)
  ts: string;
}

// ───────────────────────────── CP1 autonomy / throttle ─────────────────────────────
export type AutonomyLevel = 'auto' | 'co-pilot' | 'per-step';
// ───────────────────────────── CP3 steer (intent router) ─────────────────────────────
export interface SteerResult {
  op: string; // redirect | constrain | answer | control | clarify
  scope: Record<string, unknown>;
  result: Record<string, unknown>; // op-specific outcome
}

/** The autonomy dial's view for a project: override, global default, and effective level. */
export interface ProjectAutonomy {
  levels: AutonomyLevel[];
  project: AutonomyLevel | null; // override, or null when inheriting global
  global: AutonomyLevel;
  resolved: AutonomyLevel; // the effective throttle driving the lifecycle
}
/** CP4 per-ticket dial: ticket override, project override, global, and effective (ticket>project>global). */
export interface TicketAutonomy {
  levels: AutonomyLevel[];
  ticket: AutonomyLevel | null;
  project: AutonomyLevel | null;
  global: AutonomyLevel;
  resolved: AutonomyLevel;
}
