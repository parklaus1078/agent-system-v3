import { useStore } from '../store/useStore';
import type { AutonomyLevel } from '../api/dto';

/** CP1 throttle dial in the top bar: how much the agent runs on its own.
 *  per-step (review every step) → co-pilot (stops on trouble/final) → auto (runs the ticket). */
const LABELS: Record<AutonomyLevel, string> = {
  'per-step': '매 step',
  'co-pilot': '부조종',
  auto: '자동',
};
const ORDER: AutonomyLevel[] = ['per-step', 'co-pilot', 'auto'];

export function AutonomyDial() {
  const autonomy = useStore((s) => s.autonomy);
  const setAutonomy = useStore((s) => s.setAutonomy);
  return (
    <div className="segmented" role="group" aria-label="자율도">
      {ORDER.map((lvl) => (
        <button
          key={lvl}
          className="segmented__btn"
          aria-pressed={autonomy === lvl}
          title={`자율도: ${LABELS[lvl]}`}
          onClick={() => void setAutonomy(lvl)}
        >
          {LABELS[lvl]}
        </button>
      ))}
    </div>
  );
}
