import { useStore } from '../../store/useStore';
import {
  neighbors,
  nodeActivity,
  ticketDisplayStatus,
  type GraphNode,
  type ProjectGraph,
  type Status,
} from '../../domain/graph';
import { CheckIcon, ChevronRightIcon, ArrowRightIcon } from '../icons';
import { ActivityBadge } from '../ActivityBadge';
import { TicketAutonomyDial } from '../TicketAutonomyDial';
import './TicketBoard.css';

const STATUS_LABEL: Record<Status, string> = {
  planning: 'planned',
  executing: 'executing',
  awaiting_review: 'awaiting review',
  done: 'done',
  blocked: 'blocked',
};

/** The four board lanes. A step lands in exactly one by its status. blocked joins
 *  AWAITING REVIEW — it's the needs-your-attention lane (you debug it), matching the
 *  wireframe — not EXECUTING, which is only the step actively running. */
const COLUMNS: { key: string; title: string; statuses: Status[] }[] = [
  { key: 'planned', title: 'PLANNED', statuses: ['planning'] },
  { key: 'executing', title: 'EXECUTING', statuses: ['executing'] },
  { key: 'review', title: 'AWAITING REVIEW', statuses: ['awaiting_review', 'blocked'] },
  { key: 'done', title: 'DONE', statuses: ['done'] },
];

function touches(graph: ProjectGraph, stepId: string): string {
  const code = neighbors(graph, stepId, 'out').filter((n) => n.kind === 'code_region');
  if (code.length === 0) return 'touches —';
  return `touches ${code[0].label}${code.length > 1 ? ` +${code.length - 1}` : ''}`;
}

/** Navigator zoom-in: a ticket's steps as a status kanban board. */
export function TicketBoard() {
  const graph = useStore((s) => s.graph);
  const selectedTicketId = useStore((s) => s.selectedTicketId);
  const selectTicket = useStore((s) => s.selectTicket);
  const openInCockpit = useStore((s) => s.openInCockpit);

  if (!graph || !selectedTicketId) return null;
  const ticket = graph.nodes.find((n) => n.id === selectedTicketId);
  if (!ticket) return null;

  const steps = neighbors(graph, selectedTicketId, 'out').filter((n) => n.kind === 'step');
  const numOf = new Map(steps.map((s, i) => [s.id, String(i + 1).padStart(2, '0')]));
  const done = steps.filter((s) => s.status === 'done').length;
  const tag = (ticket.data?.tag as string) ?? ticket.label.slice(0, 4).toUpperCase();
  const display = ticketDisplayStatus(graph, selectedTicketId);
  const hasAwaiting = steps.some((s) => s.status === 'awaiting_review');
  const pct = steps.length ? Math.round((done / steps.length) * 100) : 0;

  const card = (step: GraphNode) => {
    const status = step.status ?? 'planning';
    const num = numOf.get(step.id) ?? '';
    if (status === 'awaiting_review' || status === 'blocked') {
      const blocked = status === 'blocked';
      return (
        <article
          key={step.id}
          className={`bcard ${blocked ? 'bcard--blocked' : 'bcard--review'}`}
          data-col="review"
        >
          <div className="bcard__top">
            <span className="bcard__step mono">step {num}</span>
            <span className={`pill pill--${status}`}>
              <span className="dot" />
              {STATUS_LABEL[status]}
            </span>
          </div>
          <h3 className="bcard__title">{step.label}</h3>
          <div className="bcard__touch mono">{touches(graph, step.id)}</div>
          <button
            className={`bcard__review${blocked ? ' bcard__review--blocked' : ''}`}
            onClick={() => openInCockpit(step.id)}
          >
            {blocked ? '디버그 추적' : '리뷰 시작'}
            <ArrowRightIcon size={14} />
          </button>
        </article>
      );
    }
    if (status === 'done') {
      return (
        <article key={step.id} className="bcard bcard--done" data-col="done">
          <span className="bcard__num mono">{num}</span>
          <span className="bcard__title">{step.label}</span>
          <CheckIcon size={15} className="bcard__check" />
        </article>
      );
    }
    return (
      <article key={step.id} className="bcard" data-col={status === 'planning' ? 'planned' : 'executing'}>
        <div className="bcard__top">
          <span className="bcard__num mono">{num}</span>
          <span className={`pill pill--${status}`}>
            <span className="dot" />
            {STATUS_LABEL[status]}
          </span>
        </div>
        <span className="bcard__title">{step.label}</span>
        <div className="bcard__touch mono">{touches(graph, step.id)}</div>
      </article>
    );
  };

  return (
    <section className="board" data-testid="ticket-board">
      <header className="board__head">
        <button className="board__back" onClick={() => selectTicket(null)}>
          <ChevronRightIcon size={14} className="board__back-ic" />
          지도
        </button>
        <span className="board__tag kindtag">{tag}</span>
        <h2 className="board__title">{ticket.label}</h2>
        <span className={`pill pill--${display}`}>
          <span className="dot" />
          {STATUS_LABEL[display]}
        </span>
        <ActivityBadge activity={nodeActivity(ticket)} />
        <span className="board__progress">
          <span className="board__bar">
            <span className="board__bar-fill" style={{ width: `${pct}%` }} />
          </span>
          <span className="mono board__count">
            {done} / {steps.length}
          </span>
        </span>
        {hasAwaiting && <span className="board__waiting">리뷰 대기 step이 당신을 기다립니다</span>}
        <TicketAutonomyDial ticketId={selectedTicketId} />
      </header>

      <div className="board__cols">
        {COLUMNS.map((col) => {
          const items = steps.filter((s) => col.statuses.includes(s.status ?? 'planning'));
          return (
            <section className="board__col" key={col.key}>
              <header className="board__colhead" data-active={col.key === 'review' ? 'true' : 'false'}>
                <span className="board__colname">{col.title}</span>
                <span className="board__colcount">{items.length}</span>
              </header>
              <div className="board__cards">
                {col.key === 'executing' && items.length === 0 ? (
                  <div className="board__empty">
                    <span className="board__empty-title">정지됨</span>
                    <span>이전 step 리뷰가 끝나면 다음 step이 자동 실행됩니다.</span>
                  </div>
                ) : (
                  items.map(card)
                )}
              </div>
            </section>
          );
        })}
      </div>
    </section>
  );
}
