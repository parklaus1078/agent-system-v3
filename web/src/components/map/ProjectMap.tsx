// Placeholder — replaced by the React Flow implementation in Task 6.
import { useStore } from '../../store/useStore';

export function ProjectMap() {
  const graph = useStore((s) => s.graph);
  const selectTicket = useStore((s) => s.selectTicket);
  if (!graph) return null;
  const objective = graph.nodes.find((n) => n.kind === 'objective');
  const tickets = graph.nodes.filter((n) => n.kind === 'ticket');
  return (
    <div className="dotgrid" style={{ height: '100%', padding: 24, overflow: 'auto' }}>
      {objective && <div style={{ fontWeight: 600 }}>{objective.label}</div>}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginTop: 16 }}>
        {tickets.map((t) => (
          <button key={t.id} onClick={() => selectTicket(t.id)}>
            {t.label}
          </button>
        ))}
      </div>
    </div>
  );
}
