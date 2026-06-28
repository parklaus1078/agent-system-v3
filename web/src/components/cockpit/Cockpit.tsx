import { useStore } from '../../store/useStore';
import { CockpitRail } from './CockpitRail';
import { TicketLane } from '../lane/TicketLane';
import { TargetIcon } from '../icons';
import './Cockpit.css';

/** The zoom-in altitude: project-map rail | step timeline | review gate.
 *  The review column is filled by the ReviewPane in Task 8. */
export function Cockpit() {
  const selectedTicketId = useStore((s) => s.selectedTicketId);
  if (!selectedTicketId) return null;
  return (
    <div className="cockpit">
      <aside className="cockpit__rail">
        <CockpitRail />
      </aside>
      <div className="cockpit__lane">
        <TicketLane />
      </div>
      <aside className="cockpit__review">
        <div className="cockpit__review-empty">
          <TargetIcon size={22} />
          <p>step을 선택하면 리뷰가 여기에 표시됩니다.</p>
        </div>
      </aside>
    </div>
  );
}
