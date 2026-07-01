import { Handle, Position, type NodeProps } from '@xyflow/react';
import type { NodeActivity, Status } from '../../domain/graph';
import { TargetIcon, DiamondIcon, CodeIcon, FlaskIcon, ChevronRightIcon } from '../icons';
import { ActivityBadge } from '../ActivityBadge';

// status -> short pill label (matches the wireframe's English status words)
const STATUS_LABEL: Record<Status, string> = {
  planning: 'planning',
  executing: 'executing',
  awaiting_review: 'review',
  done: 'done',
  blocked: 'blocked',
};

function StatusPill({ status }: { status: Status }) {
  return (
    <span className={`pill pill--${status}`}>
      <span className="dot" />
      {STATUS_LABEL[status]}
    </span>
  );
}

// Hidden connection handles (edges still route; the dots are invisible).
function Handles({ target = true, source = true }: { target?: boolean; source?: boolean }) {
  return (
    <>
      {target && <Handle type="target" position={Position.Top} isConnectable={false} />}
      {source && <Handle type="source" position={Position.Bottom} isConnectable={false} />}
    </>
  );
}

export interface ObjectiveData {
  label: string;
  description?: string;
  live?: boolean;
  [k: string]: unknown;
}
export function ObjectiveNode({ data }: NodeProps) {
  const d = data as ObjectiveData;
  return (
    <div className="rf-objective">
      <Handles target={false} />
      <div className="rf-objective__head">
        <span className="rf-objective__kind">
          <TargetIcon size={12} className="rf-objective__icon" />
          OBJECTIVE
        </span>
        {d.live && (
          <span className="rf-objective__live">
            <span className="rf-objective__live-dot" />
            live
          </span>
        )}
      </div>
      <div className="rf-objective__label">{d.label}</div>
      {d.description && <div className="rf-objective__desc">{d.description}</div>}
    </div>
  );
}

export interface TicketData {
  tag: string;
  label: string;
  status: Status;
  done: number;
  total: number;
  hint?: { text: string; tone: Status } | null;
  activity?: NodeActivity;
  dimmed?: boolean;
  [k: string]: unknown;
}
export function TicketNode({ data }: NodeProps) {
  const d = data as TicketData;
  const pct = d.total > 0 ? Math.round((d.done / d.total) * 100) : 0;
  // Selection / click is handled by React Flow's onNodeClick (the node wrapper
  // owns pointer-events); this card is purely presentational.
  return (
    <div className={`rf-ticket${d.dimmed ? ' is-dimmed' : ''}`}>
      <Handles />
      <div className="rf-ticket__head">
        <span className="kindtag">{d.tag}</span>
        <span className="rf-ticket__status">
          <ActivityBadge activity={d.activity} compact />
          <StatusPill status={d.status} />
        </span>
      </div>
      <div className="rf-ticket__label">{d.label}</div>
      <div className="rf-ticket__bar" aria-hidden="true">
        <span className={`rf-ticket__fill rf-fill--${d.status}`} style={{ width: `${pct}%` }} />
      </div>
      <div className="rf-ticket__foot">
        <span className="rf-ticket__count mono">
          {d.total > 0 ? `${d.done} / ${d.total} steps` : 'plan 제안됨'}
        </span>
        {d.hint && (
          <span className={`rf-ticket__hint rf-hint--${d.hint.tone}`}>
            {d.hint.text}
            <ChevronRightIcon size={12} />
          </span>
        )}
      </div>
    </div>
  );
}

export interface DecisionData {
  label: string;
  dimmed?: boolean;
  [k: string]: unknown;
}
export function DecisionNode({ data }: NodeProps) {
  const d = data as DecisionData;
  return (
    <div className={`rf-decision${d.dimmed ? ' is-dimmed' : ''}`}>
      <Handles source={false} />
      <div className="rf-decision__head">
        <DiamondIcon size={12} />
        <span className="kindtag">DECISION</span>
      </div>
      <div className="rf-decision__label">{d.label}</div>
    </div>
  );
}

export interface CodeData {
  label: string;
  dimmed?: boolean;
  [k: string]: unknown;
}
export function CodeRegionNode({ data }: NodeProps) {
  const d = data as CodeData;
  return (
    <div className={`rf-code${d.dimmed ? ' is-dimmed' : ''}`}>
      <Handles />
      <CodeIcon size={13} />
      <span className="rf-code__label mono">{d.label}</span>
    </div>
  );
}

export function TestNode({ data }: NodeProps) {
  const d = data as CodeData;
  return (
    <div className={`rf-test${d.dimmed ? ' is-dimmed' : ''}`}>
      <Handles source={false} />
      <FlaskIcon size={13} />
      <span className="rf-code__label mono">{d.label}</span>
    </div>
  );
}

export interface StepData {
  label: string;
  status: Status;
  index: number; // 1-based position within the ticket
  dimmed?: boolean;
  [k: string]: unknown;
}
export function StepNode({ data }: NodeProps) {
  const d = data as StepData;
  return (
    <div className={`rf-step${d.dimmed ? ' is-dimmed' : ''}`} title={STATUS_LABEL[d.status]}>
      <Handles />
      <span className={`rf-step__dot rf-fill--${d.status}`} />
      <span className="rf-step__num mono">{String(d.index).padStart(2, '0')}</span>
      <span className="rf-step__label">{d.label}</span>
    </div>
  );
}

// Invisible node used to extend the layout's bounding box so fitView top-anchors
// the real content instead of vertically centering it.
function SpacerNode() {
  return <div style={{ width: 1, height: 1 }} aria-hidden="true" />;
}

export const nodeTypes = {
  objective: ObjectiveNode,
  ticket: TicketNode,
  step: StepNode,
  decision: DecisionNode,
  code_region: CodeRegionNode,
  test: TestNode,
  spacer: SpacerNode,
};
