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
