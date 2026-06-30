import { useEffect, useState } from 'react';
import type { NodeActivity } from '../domain/graph';
import './ActivityBadge.css';

function elapsedSecs(since?: string): number {
  if (!since) return 0;
  const t = Date.parse(since);
  if (Number.isNaN(t)) return 0;
  return Math.max(0, Math.floor((Date.now() - t) / 1000));
}

/** Live "what's happening now" pill: spinner + detail + elapsed seconds. Only renders for
 *  the IN-PROGRESS states (planning / executing) — the gate states (awaiting_review /
 *  blocked / done) are already shown by the status pills, so we don't duplicate them. */
export function ActivityBadge({ activity, compact = false }: { activity?: NodeActivity; compact?: boolean }) {
  // Re-render every second so the elapsed counter ticks while a step runs.
  const [, setTick] = useState(0);
  const running = activity?.state === 'planning' || activity?.state === 'executing';
  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setTick((x) => x + 1), 1000);
    return () => clearInterval(id);
  }, [running]);

  if (!activity || !running) return null;
  const label = activity.state === 'planning' ? '계획 수립 중' : activity.detail || '실행 중';
  const secs = elapsedSecs(activity.since);
  return (
    <span className={`activity${compact ? ' activity--compact' : ''}`} title={`${label} · ${secs}s`}>
      <span className="activity__spin" aria-hidden="true" />
      {!compact && (
        <span className="activity__text">
          {label}
          <span className="mono"> · {secs}s</span>
        </span>
      )}
    </span>
  );
}
