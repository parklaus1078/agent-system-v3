import { useEffect, useState } from 'react';
import { useStore } from '../../store/useStore';
import { neighbors, type ProjectGraph } from '../../domain/graph';
import type { StepDetail } from '../../api/dto';

/** "step 02" — the step's 1-based position within its owning ticket. */
export function stepIndexLabel(graph: ProjectGraph | null, stepId: string | null): string {
  if (!graph || !stepId) return 'step';
  const ticket = graph.nodes.find(
    (n) => n.kind === 'ticket' && neighbors(graph, n.id, 'out').some((s) => s.id === stepId),
  );
  if (!ticket) return 'step';
  const steps = neighbors(graph, ticket.id, 'out').filter((n) => n.kind === 'step');
  const i = steps.findIndex((s) => s.id === stepId);
  return i >= 0 ? `step ${String(i + 1).padStart(2, '0')}` : 'step';
}

/** Fetch a step's detail, re-fetching whenever the live graph changes. */
export function useStepDetail(stepId: string | null): StepDetail | null {
  const api = useStore((s) => s.api);
  const graph = useStore((s) => s.graph);
  const [detail, setDetail] = useState<StepDetail | null>(null);
  useEffect(() => {
    if (!stepId) {
      setDetail(null);
      return;
    }
    let alive = true;
    void api.getStepDetail(stepId).then((d) => {
      if (alive) setDetail(d);
    });
    return () => {
      alive = false;
    };
  }, [api, stepId, graph]);
  return detail;
}
