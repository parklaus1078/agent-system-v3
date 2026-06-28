import { useStore } from '../../store/useStore';
import { neighbors, ticketDisplayStatus, type Status } from '../../domain/graph';
import { LayersIcon, TargetIcon } from '../icons';

const RAIL_STATUS_LABEL: Record<Status, string> = {
  planning: 'planning',
  executing: 'executing',
  awaiting_review: 'awaiting review',
  done: 'done',
  blocked: 'blocked',
};

/** Left rail of the cockpit: the zoom-out map condensed into a list. */
export function CockpitRail() {
  const graph = useStore((s) => s.graph);
  const selectedTicketId = useStore((s) => s.selectedTicketId);
  const selectTicket = useStore((s) => s.selectTicket);
  if (!graph) return null;

  const objective = graph.nodes.find((n) => n.kind === 'objective');
  const tickets = graph.nodes.filter((n) => n.kind === 'ticket');

  return (
    <div className="rail">
      <div className="rail__head">
        <LayersIcon size={14} />
        <span className="kindtag">PROJECT MAP</span>
      </div>

      {objective && (
        <div className="rail__obj">
          <div className="rail__obj-top">
            <span className="rail__obj-kind mono">
              <TargetIcon size={11} />
              OBJECTIVE
            </span>
            <span className="rail__obj-live" aria-hidden="true" />
          </div>
          <span className="rail__obj-label">{objective.label}</span>
        </div>
      )}

      <div className="rail__list">
        {tickets.map((t) => {
          const status = ticketDisplayStatus(graph, t.id);
          const steps = neighbors(graph, t.id, 'out').filter((n) => n.kind === 'step');
          const done = steps.filter((s) => s.status === 'done').length;
          const pct = steps.length > 0 ? Math.round((done / steps.length) * 100) : 0;
          const tag = (t.data?.tag as string) ?? t.label.slice(0, 4).toUpperCase();
          const active = t.id === selectedTicketId;
          return (
            <button
              key={t.id}
              type="button"
              className={`rail-ticket${active ? ' is-active' : ''}`}
              onClick={() => selectTicket(t.id)}
            >
              <span className="rail-ticket__top">
                <span className={`rail-ticket__dot rf-dot--${status}`} aria-hidden="true" />
                <span className="kindtag">{tag}</span>
                <span className="rail-ticket__title">{t.label}</span>
              </span>
              <span className="rail-ticket__bottom">
                <span className="rail-ticket__bar" aria-hidden="true">
                  <span className={`rail-ticket__fill rf-fill--${status}`} style={{ width: `${pct}%` }} />
                </span>
                <span className={`pill pill--${status}`}>{RAIL_STATUS_LABEL[status]}</span>
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
