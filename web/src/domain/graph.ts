// Domain graph model — mirrors design spec §6.
// Two orthogonal axes drive the whole UI (see wireframe Legend):
//   node kind  -> shape / icon
//   status     -> color

export type NodeKind = 'objective' | 'ticket' | 'step' | 'code_region' | 'test' | 'decision';
export type EdgeKind = 'has' | 'subdivides' | 'touches' | 'tested_by' | 'decided' | 'produced';
export type Status = 'planning' | 'executing' | 'awaiting_review' | 'done' | 'blocked';

export interface GraphNode {
  id: string;
  kind: NodeKind;
  label: string;
  status?: Status;
  data?: Record<string, unknown>;
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
