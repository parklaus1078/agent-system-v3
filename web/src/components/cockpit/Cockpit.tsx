import { useStore } from '../../store/useStore';
import { CockpitRail } from './CockpitRail';
import { TicketLane } from '../lane/TicketLane';
import { ReviewSummary } from '../review/ReviewSummary';
import './Cockpit.css';

/** The zoom-in altitude: project-map rail | step timeline | review summary.
 *  "전체 리뷰" in the summary opens the full-screen ReviewPane (handled by Shell). */
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
        <ReviewSummary />
      </aside>
    </div>
  );
}
