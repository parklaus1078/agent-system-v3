import { useEffect, useState } from 'react';
import { useStore } from '../../store/useStore';
import type { StepDetail } from '../../api/dto';

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
