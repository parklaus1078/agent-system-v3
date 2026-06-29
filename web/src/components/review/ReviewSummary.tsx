import { useStore } from '../../store/useStore';
import type { Status } from '../../domain/graph';
import { useStepDetail, stepIndexLabel } from './useStepDetail';
import { DiamondIcon, CheckIcon, ArrowRightIcon, TargetIcon, PlayIcon, NoEntryIcon } from '../icons';

const STATUS_LABEL: Record<Status, string> = {
  planning: 'planned',
  executing: 'executing',
  awaiting_review: 'awaiting review',
  done: 'done',
  blocked: 'blocked',
};

/** Compact review shown in the cockpit's right column. Content depends on the
 *  selected step's status: awaiting_review → the review gate (approve / full
 *  review); done → approved + commit; planning → waiting; executing → running;
 *  blocked → failed (with a trace shortcut). Non-gate states render as the
 *  wireframe's plain status-colored note box. */
export function ReviewSummary() {
  const graph = useStore((s) => s.graph);
  const selectedStepId = useStore((s) => s.selectedStepId);
  const api = useStore((s) => s.api);
  const openReview = useStore((s) => s.openReview);
  const setError = useStore((s) => s.setError);
  const detail = useStepDetail(selectedStepId);

  const approve = async () => {
    if (!selectedStepId) return;
    try {
      await api.reviewStep(selectedStepId, { kind: 'approve' });
    } catch (e) {
      setError(`승인에 실패했습니다: ${e instanceof Error ? e.message : '알 수 없는 오류'}`);
    }
  };
  // tests actually connected to this step (no execution engine, so don't claim "green"
  // when nothing is linked).
  const hasTests = !!(
    graph &&
    selectedStepId &&
    graph.edges.some((e) => e.kind === 'tested_by' && e.from === selectedStepId)
  );

  if (!selectedStepId || !detail) {
    return (
      <div className="cockpit__review-empty">
        <TargetIcon size={22} />
        <p>step을 선택하면 리뷰가 여기에 표시됩니다.</p>
      </div>
    );
  }

  const status = (detail.node.status ?? 'planning') as Status;
  const met = detail.acceptance.filter((a) => a.met).length;

  return (
    <div className="rsum">
      <div className="rsum__head">
        <span className="kindtag rsum__step">{stepIndexLabel(graph, selectedStepId)}</span>
        <span className={`pill pill--${status}`}>
          <span className="dot" />
          {STATUS_LABEL[status]}
        </span>
      </div>
      <h3 className="rsum__title">{detail.node.label}</h3>

      {status === 'awaiting_review' && (
        <>
          {detail.decision && (
            <div className="rsum__decision">
              <div className="rsum__decision-head">
                <DiamondIcon size={12} />
                <span className="kindtag">DECISION</span>
              </div>
              <p>{detail.decision}</p>
            </div>
          )}
          <div className="rsum__metrics">
            <div className="rsum__metric">
              <span className="rsum__metric-label">ACCEPTANCE</span>
              <span className="rsum__metric-value mono">
                {met} / {detail.acceptance.length}
              </span>
            </div>
            <div className="rsum__metric">
              <span className="rsum__metric-label">TESTS</span>
              {hasTests ? (
                <span className="rsum__metric-value rsum__metric-value--ok">● green</span>
              ) : (
                <span className="rsum__metric-value">테스트 없음</span>
              )}
            </div>
          </div>
          <div className="rsum__actions">
            <button className="rsum__approve" onClick={approve}>
              <CheckIcon size={15} />
              승인
            </button>
            <button className="rsum__full" onClick={openReview}>
              전체 리뷰
              <ArrowRightIcon size={14} />
            </button>
          </div>
        </>
      )}

      {status === 'done' && (
        <div className="rsum__note rsum__note--done">
          <CheckIcon size={15} />
          <span>승인 완료 · commit 채택됨</span>
        </div>
      )}

      {status === 'planning' && (
        <div className="rsum__note rsum__note--wait">
          <span>대기 중 — 이전 step이 승인되면 실행을 시작합니다.</span>
        </div>
      )}

      {status === 'executing' && (
        <div className="rsum__note rsum__note--run">
          <PlayIcon size={14} />
          <span>실행 중 — 에이전트가 이 step을 작업하고 있습니다.</span>
        </div>
      )}

      {status === 'blocked' && (
        <>
          <div className="rsum__note rsum__note--blocked">
            <NoEntryIcon size={15} />
            <span>실패 — 디버그가 필요합니다</span>
          </div>
          <button className="rsum__trace" onClick={openReview}>
            전체 리뷰에서 추적
            <ArrowRightIcon size={14} />
          </button>
        </>
      )}
    </div>
  );
}
