// Placeholder — replaced by the step-timeline implementation in Task 7.
import { useStore } from '../../store/useStore';
import { neighbors } from '../../domain/graph';

export function TicketLane() {
  const graph = useStore((s) => s.graph);
  const selectedTicketId = useStore((s) => s.selectedTicketId);
  const selectStep = useStore((s) => s.selectStep);
  if (!graph || !selectedTicketId) return null;
  const ticket = graph.nodes.find((n) => n.id === selectedTicketId);
  const steps = neighbors(graph, selectedTicketId, 'out').filter((n) => n.kind === 'step');
  return (
    <div data-testid="ticket-lane" style={{ height: '100%', padding: 24, overflow: 'auto' }}>
      <div style={{ fontWeight: 600 }}>{ticket?.label}</div>
      <ul>
        {steps.map((s) => (
          <li key={s.id}>
            <button onClick={() => selectStep(s.id)}>{s.label}</button>
          </li>
        ))}
      </ul>
    </div>
  );
}
