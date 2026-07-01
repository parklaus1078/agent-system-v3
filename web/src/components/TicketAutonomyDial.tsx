import { useEffect, useState } from 'react';
import { useStore } from '../store/useStore';
import type { AutonomyLevel, TicketAutonomy } from '../api/dto';

const LABELS: Record<AutonomyLevel, string> = {
  'per-step': '매 step',
  'co-pilot': '부조종',
  auto: '자동',
};
const ORDER: AutonomyLevel[] = ['per-step', 'co-pilot', 'auto'];

/** CP4: a compact per-ticket throttle dial (board/cockpit header). Clicking sets the TICKET
 *  override; the dial shows the EFFECTIVE (resolved) level; a subtle "·상속" marks an inherited
 *  (project/global) level vs an explicit ticket override. */
export function TicketAutonomyDial({ ticketId }: { ticketId: string }) {
  const api = useStore((s) => s.api);
  const setError = useStore((s) => s.setError);
  // The store's effective project autonomy — refreshed by loadAutonomy on every backend tick.
  // For an INHERITED ticket the resolved level tracks this, so refetch when it changes (e.g. a
  // steer `control` op or the top dial flips the project level) instead of showing a stale value.
  const projectAutonomy = useStore((s) => s.autonomy);
  const [view, setView] = useState<TicketAutonomy | null>(null);

  useEffect(() => {
    let alive = true;
    void api.getTicketAutonomy(ticketId).then(
      (v) => alive && setView(v),
      () => {},
    );
    return () => {
      alive = false;
    };
  }, [api, ticketId, projectAutonomy]);

  if (!view) return null;

  const set = async (level: AutonomyLevel) => {
    try {
      setView(await api.setTicketAutonomy(ticketId, level));
    } catch (e) {
      setError(`자율도 저장에 실패했습니다: ${e instanceof Error ? e.message : '알 수 없는 오류'}`);
    }
  };

  return (
    <span className="ticket-dial" title={view.ticket ? '이 티켓 전용 자율도' : `상속됨 (${view.resolved})`}>
      <span className="ticket-dial__cap mono">자율도{view.ticket ? '' : ' ·상속'}</span>
      <span className="segmented segmented--sm" role="group" aria-label="티켓 자율도">
        {ORDER.map((lvl) => (
          <button
            key={lvl}
            className="segmented__btn"
            aria-pressed={view.resolved === lvl}
            onClick={() => void set(lvl)}
          >
            {LABELS[lvl]}
          </button>
        ))}
      </span>
    </span>
  );
}
