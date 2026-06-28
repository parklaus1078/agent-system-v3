import { useMemo, useState } from 'react';
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  BackgroundVariant,
  Panel,
  type Node,
  type Edge,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useStore } from '../../store/useStore';
import { neighbors, type ProjectGraph, type GraphNode, type EdgeKind, type Status } from '../../domain/graph';
import { nodeTypes } from './nodeTypes';
import { LayersIcon, PlusIcon } from '../icons';
import './ProjectMap.css';

const OBJ_W = 280;
const TICKET_W = 200;
const CODE_W = 196;
const COL_GAP = 56;
const ROW_TICKET = 150;
const ROW_DECISION = 290;
const ROW_CODE = 384;
const CODE_STEP = 44;

const EDGE_STYLE: Record<EdgeKind, React.CSSProperties> = {
  has: { stroke: '#c4cad4', strokeWidth: 1.5 },
  subdivides: { stroke: '#cdd3db', strokeWidth: 1.5 },
  touches: { stroke: '#2f6fed', strokeWidth: 1.6 },
  tested_by: { stroke: '#28a866', strokeWidth: 1.5, strokeDasharray: '5 4' },
  decided: { stroke: '#7c6bd6', strokeWidth: 1.5, strokeDasharray: '2 4' },
  produced: { stroke: '#9aa3b4', strokeWidth: 1.5, strokeDasharray: '1 5' },
};

const KIND_PRIORITY: GraphNode['kind'][] = ['ticket', 'step', 'code_region', 'objective', 'test', 'decision'];

function ownerTicketId(g: ProjectGraph, id: string): string | null {
  let cur = id;
  for (let i = 0; i < 8; i++) {
    const node = g.nodes.find((n) => n.id === cur);
    if (!node) return null;
    if (node.kind === 'ticket') return cur;
    const parents = neighbors(g, cur, 'in');
    if (parents.length === 0) return null;
    parents.sort((a, b) => KIND_PRIORITY.indexOf(a.kind) - KIND_PRIORITY.indexOf(b.kind));
    cur = parents[0].id;
  }
  return null;
}

interface TicketMeta {
  done: number;
  total: number;
  hint: { text: string; tone: Status } | null;
}
function ticketMeta(g: ProjectGraph, ticket: GraphNode): TicketMeta {
  const steps = neighbors(g, ticket.id, 'out').filter((n) => n.kind === 'step');
  const done = steps.filter((s) => s.status === 'done').length;
  const pad = (i: number) => String(i + 1).padStart(2, '0');
  let hint: TicketMeta['hint'] = null;
  const awaitingIdx = steps.findIndex((s) => s.status === 'awaiting_review');
  const blockedIdx = steps.findIndex((s) => s.status === 'blocked');
  if (awaitingIdx >= 0) hint = { text: `step ${pad(awaitingIdx)} 대기`, tone: 'awaiting_review' };
  else if (blockedIdx >= 0) hint = { text: `step ${pad(blockedIdx)} 실패`, tone: 'blocked' };
  else if (ticket.status === 'planning') hint = { text: 'plan 검토', tone: 'planning' };
  return { done, total: steps.length, hint };
}

export interface ProjectMapProps {
  highlightIds?: string[];
  onNewGoal?: () => void;
}

function MapInner({ highlightIds, onNewGoal }: ProjectMapProps) {
  const graph = useStore((s) => s.graph);
  const selectTicket = useStore((s) => s.selectTicket);
  const [showCode, setShowCode] = useState(false);

  const active = !!highlightIds && highlightIds.length > 0;
  const dim = (id: string) => (active ? !highlightIds!.includes(id) : false);
  // a trace onto a code/test region auto-reveals the code layer so its node shows
  const codeHighlighted =
    active &&
    !!graph &&
    highlightIds!.some((id) => {
      const n = graph.nodes.find((nn) => nn.id === id);
      return n?.kind === 'code_region' || n?.kind === 'test';
    });
  const effectiveShowCode = showCode || codeHighlighted;

  const { nodes, edges, banner } = useMemo(() => {
    if (!graph) return { nodes: [] as Node[], edges: [] as Edge[], banner: null as string | null };

    const objective = graph.nodes.find((n) => n.kind === 'objective');
    const tickets = graph.nodes.filter((n) => n.kind === 'ticket');
    const decisions = graph.nodes.filter((n) => n.kind === 'decision');
    const codes = graph.nodes.filter((n) => n.kind === 'code_region' || n.kind === 'test');

    // layered positions
    const pos = new Map<string, { x: number; y: number }>();
    const col = TICKET_W + COL_GAP;
    const totalW = tickets.length * TICKET_W + (tickets.length - 1) * COL_GAP;
    const startX = -totalW / 2;
    const centerOf = (id: string) => (pos.get(id)?.x ?? 0) + TICKET_W / 2;
    tickets.forEach((t, i) => pos.set(t.id, { x: startX + i * col, y: ROW_TICKET }));
    if (objective) pos.set(objective.id, { x: -OBJ_W / 2, y: 0 });

    const ticketHasDecision = new Set(
      decisions.map((d) => ownerTicketId(graph, d.id)).filter(Boolean) as string[],
    );
    decisions.forEach((d) => {
      const owner = ownerTicketId(graph, d.id);
      pos.set(d.id, { x: (owner ? centerOf(owner) : 0) - 118, y: ROW_DECISION });
    });
    // code/test stacked below their owner ticket (only matters when showCode)
    const codeIdxByOwner = new Map<string, number>();
    codes.forEach((c) => {
      const owner = ownerTicketId(graph, c.id);
      const baseY = owner && ticketHasDecision.has(owner) ? ROW_CODE : ROW_DECISION;
      const idx = codeIdxByOwner.get(owner ?? '') ?? 0;
      codeIdxByOwner.set(owner ?? '', idx + 1);
      pos.set(c.id, { x: (owner ? centerOf(owner) : 0) - CODE_W / 2, y: baseY + idx * CODE_STEP });
    });

    const visible = new Set<string>();
    if (objective) visible.add(objective.id);
    tickets.forEach((t) => visible.add(t.id));
    decisions.forEach((d) => visible.add(d.id));
    if (effectiveShowCode) codes.forEach((c) => visible.add(c.id));

    const rfNodes: Node[] = [];
    if (objective)
      rfNodes.push({
        id: objective.id,
        type: 'objective',
        position: pos.get(objective.id)!,
        data: { label: objective.label, live: true },
        draggable: false,
        selectable: false,
      });
    tickets.forEach((t) => {
      const meta = ticketMeta(graph, t);
      rfNodes.push({
        id: t.id,
        type: 'ticket',
        position: pos.get(t.id)!,
        data: {
          tag: (t.data?.tag as string) ?? t.label.slice(0, 4).toUpperCase(),
          label: t.label,
          status: t.status ?? 'planning',
          done: meta.done,
          total: meta.total,
          hint: meta.hint,
          dimmed: dim(t.id),
        },
        draggable: false,
        selectable: true, // tickets receive pointer events (others stay inert)
      });
    });
    decisions.forEach((d) =>
      rfNodes.push({
        id: d.id,
        type: 'decision',
        position: pos.get(d.id)!,
        data: { label: d.label, dimmed: dim(d.id) },
        draggable: false,
        selectable: false,
      }),
    );
    if (effectiveShowCode)
      codes.forEach((c) =>
        rfNodes.push({
          id: c.id,
          type: c.kind === 'test' ? 'test' : 'code_region',
          position: pos.get(c.id)!,
          data: { label: c.label, dimmed: dim(c.id) },
          draggable: false,
          selectable: false,
        }),
      );

    // collapse steps to their owning ticket so edges stay coherent without step nodes
    const rep = (id: string): string | null => {
      const node = graph.nodes.find((n) => n.id === id);
      if (!node) return null;
      return node.kind === 'step' ? ownerTicketId(graph, id) : id;
    };
    const rfEdges: Edge[] = [];
    const seen = new Set<string>();
    for (const e of graph.edges) {
      const a = rep(e.from);
      const b = rep(e.to);
      if (!a || !b || a === b) continue;
      if (!visible.has(a) || !visible.has(b)) continue;
      const key = `${a}->${b}:${e.kind}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const faded = active ? !(highlightIds!.includes(a) && highlightIds!.includes(b)) : false;
      rfEdges.push({
        id: key,
        source: a,
        target: b,
        type: 'default',
        style: { ...EDGE_STYLE[e.kind], opacity: faded ? 0.12 : 1 },
      });
    }

    // awaiting-review banner names the step that awaits your review (the amber
    // status belongs to the step, not its still-executing ticket)
    const awaitingStep = graph.nodes.find((n) => n.kind === 'step' && n.status === 'awaiting_review');
    const bannerStep = awaitingStep?.label ?? null;

    return { nodes: rfNodes, edges: rfEdges, banner: bannerStep };
  }, [graph, effectiveShowCode, highlightIds]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      fitView
      fitViewOptions={{ padding: 0.26, maxZoom: 0.9 }}
      minZoom={0.4}
      maxZoom={1.5}
      nodesDraggable={false}
      nodesConnectable={false}
      onNodeClick={(_, node) => {
        if (node.type === 'ticket') selectTicket(node.id);
      }}
      panOnDrag={false}
      zoomOnDoubleClick={false}
      proOptions={{ hideAttribution: true }}
    >
      <Background variant={BackgroundVariant.Dots} gap={23} size={1.1} color="#dde2e9" />
      <Panel position="top-left">
        <div className="map-controls">
          <button
            className="map-toggle"
            aria-pressed={effectiveShowCode}
            onClick={() => setShowCode((v) => !v)}
          >
            <LayersIcon size={15} />
            CodeRegion 레이어
          </button>
          {banner && (
            <span className="map-banner">
              <span className="map-banner__dot" />
              지금 <b>{banner}</b> 가 당신의 리뷰를 기다리는 중
            </span>
          )}
        </div>
      </Panel>
      <Panel position="top-right">
        <button className="map-add" onClick={() => onNewGoal?.()}>
          <PlusIcon size={15} />
          목표 · 티켓
        </button>
      </Panel>
    </ReactFlow>
  );
}

export function ProjectMap(props: ProjectMapProps) {
  return (
    <ReactFlowProvider>
      <MapInner {...props} />
    </ReactFlowProvider>
  );
}
