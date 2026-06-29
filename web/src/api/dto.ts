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
