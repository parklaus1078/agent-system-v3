import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useStore } from '../store/useStore';
import { ProjectMap } from './map/ProjectMap';
import { TicketBoard } from './board/TicketBoard';
import { Cockpit } from './cockpit/Cockpit';
import { ReviewPane } from './review/ReviewPane';
import { BugTrace } from './bugtrace/BugTrace';
import { Modal } from './Modal';
import { GoalEntry } from './goal/GoalEntry';
import { PlanApproval } from './plan/PlanApproval';
import { ProjectMetaEditor } from './home/ProjectMetaEditor';
import { Legend } from './legend/Legend';
import { AutonomyDial } from './AutonomyDial';
import { ChannelPanel } from './channel/ChannelPanel';
import { GridIcon, EditIcon, LayersIcon } from './icons';
import { nextTicketId } from '../domain/graph';
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

export function Shell() {
  const { pid } = useParams();
  const navigate = useNavigate();
  const setPid = useStore((s) => s.setPid);
  const graph = useStore((s) => s.graph);
  const selectedTicketId = useStore((s) => s.selectedTicketId);
  const selectedStepId = useStore((s) => s.selectedStepId);
  const reviewOpen = useStore((s) => s.reviewOpen);
  const planTicketId = useStore((s) => s.planTicketId);
  const closePlan = useStore((s) => s.closePlan);
  const selectTicket = useStore((s) => s.selectTicket);
  const mode = useStore((s) => s.mode);
  const setMode = useStore((s) => s.setMode);
  const online = useStore((s) => s.online);
  const error = useStore((s) => s.error);
  const setError = useStore((s) => s.setError);
  const clock = useElapsedClock();
  const highlightIds = useStore((s) => s.highlightIds); // CP4: shared (BugTrace + channel refs)
  const setHighlightIds = useStore((s) => s.setHighlightIds);
  const [goalFlow, setGoalFlow] = useState<'none' | 'goal' | 'plan'>('none');
  const [pendingGoal, setPendingGoal] = useState('');
  // Stable ticket id minted ONCE per goal so re-opening the plan modal reuses the same
  // /plan thread instead of creating duplicate tickets.
  const [pendingTid, setPendingTid] = useState('');
  const [legendOpen, setLegendOpen] = useState(false);
  const [metaOpen, setMetaOpen] = useState(false); // project title/description view+edit
  // CP2 conversation channel (right rail). Lives in the store so a CP4 map-node click can open
  // it alongside the filter it sets (otherwise the filter would be invisible + unclearable).
  const channelOpen = useStore((s) => s.channelOpen);
  const setChannelOpen = useStore((s) => s.setChannelOpen);
  const messageCount = useStore((s) => s.messages.length);
  const [seenMessages, setSeenMessages] = useState(0);
  // The badge is a genuine UNREAD count: while the panel is open everything is seen, so it
  // stays 0; while closed it counts messages that arrived since it was last viewed.
  useEffect(() => {
    if (channelOpen) setSeenMessages(messageCount);
  }, [channelOpen, messageCount]);
  const unreadMessages = channelOpen ? 0 : Math.max(0, messageCount - seenMessages);

  // The route's :pid selects the project; setPid loads its graph (and is a no-op if
  // already current).
  useEffect(() => {
    if (pid) setPid(pid);
  }, [pid, setPid]);

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
  // Navigator = map (no ticket) or the ticket's board (ticket open); Cockpit = review workspace.
  const view: 'map' | 'board' | 'cockpit' =
    mode === 'cockpit' && selectedTicketId ? 'cockpit' : selectedTicketId ? 'board' : 'map';

  const goNavigator = () => setMode('navigator');
  const goMap = () => {
    // breadcrumb / project name: back to the Navigator project map
    setMode('navigator');
    selectTicket(null);
  };
  const goCockpit = () => {
    setMode('cockpit');
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
          <button className="topbar__home" onClick={() => navigate('/')} aria-label="프로젝트 목록">
            <span className="topbar__logo" aria-hidden="true">
              CT
            </span>
            <span className="topbar__title">Control Tower</span>
          </button>
          {projectName && (
            <>
              <span className="topbar__sep" aria-hidden="true" />
              <button className="topbar__project" onClick={goMap}>
                {projectName}
              </button>
              <button
                className="topbar__editmeta"
                aria-label="프로젝트 설명 보기·수정"
                title="프로젝트 설명 보기·수정"
                onClick={() => setMetaOpen(true)}
              >
                <EditIcon size={14} />
              </button>
            </>
          )}
        </div>

        <div className="topbar__center">
          <BugTrace onHighlight={handleHighlight} />
        </div>

        <div className="topbar__right">
          <span className="topbar__autonomy">
            <span className="topbar__autonomy-cap mono">자율도</span>
            <AutonomyDial />
          </span>
          <span className={`live${online ? '' : ' live--off'}`} title={online ? '백엔드 연결됨' : '백엔드 연결 끊김'}>
            <span className="live__dot" aria-hidden="true" />
            <span className="mono">{online ? 'live' : 'offline'}</span>
            <span className="live__clock mono">{clock}</span>
          </span>
          <div className="segmented" role="group" aria-label="altitude">
            <button
              className="segmented__btn"
              aria-pressed={view !== 'cockpit'} // map & board are both Navigator
              onClick={goNavigator}
            >
              Navigator
            </button>
            <button
              className="segmented__btn"
              aria-pressed={view === 'cockpit'}
              onClick={goCockpit}
            >
              Cockpit
            </button>
          </div>
          <button
            className="iconbtn"
            aria-label="거버넌스 — 규칙·모델 라우팅"
            title="거버넌스 (규칙·모델)"
            onClick={() => pid && navigate(`/project/${pid}/rules`)}
          >
            <LayersIcon size={15} />
            Governance
          </button>
          <button
            className="iconbtn"
            aria-pressed={channelOpen}
            aria-label="대화 채널 열기·닫기"
            title="대화 채널"
            onClick={() => setChannelOpen(!channelOpen)}
          >
            채널
            {unreadMessages > 0 && <span className="iconbtn__badge mono">{unreadMessages}</span>}
          </button>
          <div className="legend-anchor">
            <button
              className="iconbtn"
              aria-expanded={legendOpen}
              onClick={() => setLegendOpen((o) => !o)}
            >
              <GridIcon size={15} />
              Legend
            </button>
            {legendOpen && <Legend onClose={() => setLegendOpen(false)} />}
          </div>
        </div>
      </header>

      <div className="shell__body">
      <main className="shell__main">
        {view === 'map' ? (
          <ProjectMap
            highlightIds={highlightIds ?? undefined}
            onNewGoal={() => setGoalFlow('goal')}
          />
        ) : view === 'board' ? (
          <TicketBoard />
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
                // mint once for this goal as {slug}-{number(auto-increment)} — same shape the
                // backend assigns, so UI-created tickets don't get an opaque t-{timestamp} id.
                setPendingTid(graph ? nextTicketId(graph, pid ?? 'p1') : `${pid ?? 'p1'}-1`);
                setGoalFlow('plan');
              }}
            />
          </Modal>
        )}
        {goalFlow === 'plan' && (
          <Modal onClose={() => setGoalFlow('none')} dismissable={false}>
            <PlanApproval
              goal={pendingGoal}
              newTicketId={pendingTid}
              onCancel={() => setGoalFlow('none')}
              onApproved={() => {
                setGoalFlow('none');
                selectTicket(pendingTid); // navigate to the new ticket so the user sees it
              }}
            />
          </Modal>
        )}
        {planTicketId && (
          <Modal onClose={closePlan} dismissable={false}>
            <PlanApproval ticketId={planTicketId} onCancel={closePlan} onApproved={closePlan} />
          </Modal>
        )}
        {metaOpen && objective && (
          <Modal onClose={() => setMetaOpen(false)}>
            <ProjectMetaEditor
              initialTitle={objective.label ?? ''}
              initialDescription={(objective.data?.description as string | undefined) ?? ''}
              onClose={() => setMetaOpen(false)}
            />
          </Modal>
        )}
        {error && (
          <div className="toast" role="alert">
            <span>{error}</span>
            <button className="toast__close" aria-label="닫기" onClick={() => setError(null)}>
              ✕
            </button>
          </div>
        )}
      </main>
        {channelOpen && <ChannelPanel />}
      </div>
    </div>
  );
}
