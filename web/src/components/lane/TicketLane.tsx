import { useStore } from '../../store/useStore';
import { neighbors, type GraphNode, type Status } from '../../domain/graph';
import './TicketLane.css';

const STEP_STATUS_LABEL: Record<Status, string> = {
  planning: 'planned',
  executing: 'executing',
  awaiting_review: 'awaiting review',
  done: 'done',
  blocked: 'blocked',
};

function touchesText(steps: GraphNode[], graph: Parameters<typeof neighbors>[0], stepId: string): string {
  const code = neighbors(graph, stepId, 'out').filter((n) => n.kind === 'code_region');
  if (code.length === 0) return 'touches —';
  const extra = code.length > 1 ? ` +${code.length - 1}` : '';
  void steps;
  return `touches ${code[0].label}${extra}`;
}

export function TicketLane() {
  const graph = useStore((s) => s.graph);
  const selectedTicketId = useStore((s) => s.selectedTicketId);
  const selectedStepId = useStore((s) => s.selectedStepId);
  const selectStep = useStore((s) => s.selectStep);

  if (!graph || !selectedTicketId) return null;
  const ticket = graph.nodes.find((n) => n.id === selectedTicketId);
  const steps = neighbors(graph, selectedTicketId, 'out').filter((n) => n.kind === 'step');
  const done = steps.filter((s) => s.status === 'done').length;
  const tag = (ticket?.data?.tag as string) ?? ticket?.label.slice(0, 4).toUpperCase() ?? '';

  return (
    <section className="lane" data-testid="ticket-lane">
      <header className="lane__head">
        <span className="lane__tag kindtag">{tag}</span>
        <h2 className="lane__title">{ticket?.label}</h2>
        <span className="lane__count mono">
          {done} / {steps.length}
        </span>
      </header>

      <ol className="lane__list">
        {steps.map((s, i) => {
          const status = s.status ?? 'planning';
          const emphasis = status === 'awaiting_review';
          const selected = s.id === selectedStepId;
          return (
            <li key={s.id}>
              <button
                type="button"
                className={`step${selected ? ' is-selected' : ''}`}
                data-emphasis={emphasis ? 'true' : 'false'}
                onClick={() => selectStep(s.id)}
              >
                <span className="step__num mono">{String(i + 1).padStart(2, '0')}</span>
                <span className="step__body">
                  <span className="step__row1">
                    <span className="step__title">{s.label}</span>
                    <span className={`pill pill--${status}`}>
                      <span className="dot" />
                      {STEP_STATUS_LABEL[status]}
                    </span>
                  </span>
                  <span className="step__touches mono">{touchesText(steps, graph, s.id)}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
