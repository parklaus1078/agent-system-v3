import { useEffect, useRef, useState } from 'react';
import { useStore } from '../store/useStore';
import { ProjectMap } from './map/ProjectMap';
import { Cockpit } from './cockpit/Cockpit';
import { ReviewPane } from './review/ReviewPane';
import { BugTrace } from './bugtrace/BugTrace';
import { Modal } from './Modal';
import { GoalEntry } from './goal/GoalEntry';
import { PlanApproval } from './plan/PlanApproval';
import { GridIcon } from './icons';
import './Shell.css';

/** Elapsed session clock shown as HH:MM:SS in the top bar (the "live" feel). */
function useElapsedClock(): string {
  const [secs, setSecs] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setSecs((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, []);
  const hh = String(Math.floor(secs / 3600)).padStart(2, '0');
  const mm = String(Math.floor((secs % 3600) / 60)).padStart(2, '0');
  const ss = String(secs % 60).padStart(2, '0');
  return `${hh}:${mm}:${ss}`;
}

export function Shell({ onHome }: { onHome?: () => void }) {
  const load = useStore((s) => s.load);
  const graph = useStore((s) => s.graph);
  const selectedTicketId = useStore((s) => s.selectedTicketId);
  const selectedStepId = useStore((s) => s.selectedStepId);
  const reviewOpen = useStore((s) => s.reviewOpen);
  const planTicketId = useStore((s) => s.planTicketId);
  const closePlan = useStore((s) => s.closePlan);
  const selectTicket = useStore((s) => s.selectTicket);
  const clock = useElapsedClock();
  const loaded = useRef(false);
  const [highlightIds, setHighlightIds] = useState<string[] | null>(null);
  const [goalFlow, setGoalFlow] = useState<'none' | 'goal' | 'plan'>('none');
  const [pendingGoal, setPendingGoal] = useState('');

  useEffect(() => {
    if (!loaded.current) {
      loaded.current = true;
      void load();
    }
  }, [load]);

  // Opening a ticket (cockpit) clears any trace highlight on the map.
  useEffect(() => {
    if (selectedTicketId) setHighlightIds(null);
  }, [selectedTicketId]);

  // Tracing a file highlights its owning path on the map (so jump to the map).
  const handleHighlight = (ids: string[]) => {
    setHighlightIds(ids.length ? ids : null);
    selectTicket(null);
  };

  const objective = graph?.nodes.find((n) => n.kind === 'objective');
  const projectName = (objective?.data?.short as string | undefined) ?? objective?.label ?? '';
  const altitude: 'map' | 'lane' = selectedTicketId ? 'lane' : 'map';

  const goNavigator = () => selectTicket(null);
  const goCockpit = () => {
    if (selectedTicketId) return;
    // Cockpit needs a ticket in focus: prefer the one awaiting your review.
    const tickets = graph?.nodes.filter((n) => n.kind === 'ticket') ?? [];
    const focus = tickets.find((t) => t.status === 'awaiting_review' || t.status === 'executing') ?? tickets[0];
    if (focus) selectTicket(focus.id);
  };

  return (
    <div className="shell">
      <h1 className="sr-only">LLM Dev Control Tower</h1>
      <header className="topbar">
        <div className="topbar__brand">
          <button className="topbar__home" onClick={onHome} aria-label="프로젝트 목록">
            <span className="topbar__logo" aria-hidden="true">
              CT
            </span>
            <span className="topbar__title">Control Tower</span>
          </button>
          {projectName && (
            <>
              <span className="topbar__sep" aria-hidden="true" />
              <button className="topbar__project" onClick={goNavigator}>
                {projectName}
              </button>
            </>
          )}
        </div>

        <div className="topbar__center">
          <BugTrace onHighlight={handleHighlight} />
        </div>

        <div className="topbar__right">
          <span className="live">
            <span className="live__dot" aria-hidden="true" />
            <span className="mono">live</span>
            <span className="live__clock mono">{clock}</span>
          </span>
          <div className="segmented" role="group" aria-label="altitude">
            <button
              className="segmented__btn"
              aria-pressed={altitude === 'map'}
              onClick={goNavigator}
            >
              Navigator
            </button>
            <button
              className="segmented__btn"
              aria-pressed={altitude === 'lane'}
              onClick={goCockpit}
            >
              Cockpit
            </button>
          </div>
          <button className="iconbtn">
            <GridIcon size={15} />
            Legend
          </button>
        </div>
      </header>

      <main className="shell__main">
        {altitude === 'map' ? (
          <ProjectMap
            highlightIds={highlightIds ?? undefined}
            onNewGoal={() => setGoalFlow('goal')}
          />
        ) : (
          <Cockpit />
        )}
        {reviewOpen && selectedStepId && (
          <div className="review-overlay">
            <ReviewPane />
          </div>
        )}
        {goalFlow === 'goal' && (
          <Modal onClose={() => setGoalFlow('none')}>
            <GoalEntry
              onCancel={() => setGoalFlow('none')}
              onSubmit={(goal) => {
                setPendingGoal(goal);
                setGoalFlow('plan');
              }}
            />
          </Modal>
        )}
        {goalFlow === 'plan' && (
          <Modal onClose={() => setGoalFlow('none')}>
            <PlanApproval
              goal={pendingGoal}
              onCancel={() => setGoalFlow('none')}
              onApproved={() => setGoalFlow('none')}
            />
          </Modal>
        )}
        {planTicketId && (
          <Modal onClose={closePlan}>
            <PlanApproval ticketId={planTicketId} onCancel={closePlan} onApproved={closePlan} />
          </Modal>
        )}
      </main>
    </div>
  );
}
