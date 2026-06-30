// Domain graph model — mirrors design spec §6.
// Two orthogonal axes drive the whole UI (see wireframe Legend):
//   node kind  -> shape / icon
//   status     -> color

export type NodeKind = 'objective' | 'ticket' | 'step' | 'code_region' | 'test' | 'decision';
export type EdgeKind = 'has' | 'subdivides' | 'touches' | 'tested_by' | 'decided' | 'produced';
export type Status = 'planning' | 'executing' | 'awaiting_review' | 'done' | 'blocked';

/** Coarse "what the backend is doing now", written by the lifecycle at each transition
 *  and read live via getGraph polling (see Phase 3). Lives on the ticket node's data. */
export interface NodeActivity {
  state: 'planning' | 'executing' | 'awaiting_review' | 'blocked' | 'done';
  detail?: string; // e.g. "step 2/5"
  since?: string; // ISO timestamp the state was entered (for an elapsed counter)
}

export interface GraphNode {
  id: string;
  kind: NodeKind;
  label: string;
  status?: Status;
  data?: Record<string, unknown>;
}

/** The node's live activity, if any (typed read of `data.activity`). */
export function nodeActivity(n: GraphNode | undefined): NodeActivity | undefined {
  const a = n?.data?.activity as NodeActivity | undefined;
  return a && a.state ? a : undefined;
}
export interface GraphEdge {
  id: string;
  from: string;
  to: string;
  kind: EdgeKind;
}
export interface ProjectGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

/** A ticket's display status reflects its active step's gate: a ticket with a
 *  step awaiting review reads as `awaiting_review` (and blocked likewise), so the
 *  badge agrees with the review banner. Otherwise it's the ticket's own status. */
export function ticketDisplayStatus(g: ProjectGraph, ticketId: string): Status {
  const t = g.nodes.find((n) => n.id === ticketId);
  const steps = neighbors(g, ticketId, 'out').filter((n) => n.kind === 'step');
  if (steps.some((s) => s.status === 'awaiting_review')) return 'awaiting_review';
  if (steps.some((s) => s.status === 'blocked')) return 'blocked';
  return t?.status ?? 'planning';
}

/** Direct neighbours of `nodeId` following edges in the given direction. */
export function neighbors(g: ProjectGraph, nodeId: string, dir: 'in' | 'out' | 'both'): GraphNode[] {
  const byId = new Map(g.nodes.map((n) => [n.id, n]));
  const ids = new Set<string>();
  for (const e of g.edges) {
    if ((dir === 'out' || dir === 'both') && e.from === nodeId) ids.add(e.to);
    if ((dir === 'in' || dir === 'both') && e.to === nodeId) ids.add(e.from);
  }
  return [...ids].map((id) => byId.get(id)!).filter(Boolean);
}
