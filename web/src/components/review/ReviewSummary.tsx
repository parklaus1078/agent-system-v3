import { useStore } from '../../store/useStore';
import type { Status } from '../../domain/graph';
import { useStepDetail, stepIndexLabel } from './useStepDetail';
import {
  DiamondIcon,
  CheckIcon,
  ArrowRightIcon,
  TargetIcon,
  ClockIcon,
  PlayIcon,
  AlertIcon,
} from '../icons';

const STATUS_LABEL: Record<Status, string> = {
  planning: 'planned',
  executing: 'executing',
  awaiting_review: 'awaiting review',
  done: 'done',
  blocked: 'blocked',
};

/** Short pseudo-commit hash for display (the mock has no real SHA). */
function shortSha(id: string): string {
  let h = 0;
  for (const c of id) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return h.toString(16).padStart(7, '0').slice(0, 7);
}

/** Compact review shown in the cockpit's right column. Content depends on the
 *  selected step's status: awaiting_review → the review gate (approve / full
 *  review); done → approved + commit; planning → waiting; executing → running;
 *  blocked → failed. */
export function ReviewSummary() {
  const graph = useStore((s) => s.graph);
  const selectedStepId = useStore((s) => s.selectedStepId);
  const api = useStore((s) => s.api);
  const openReview = useStore((s) => s.openReview);
  const detail = useStepDetail(selectedStepId);

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
              <span className="rsum__metric-value rsum__metric-value--ok">● green</span>
            </div>
          </div>
          <div className="rsum__actions">
            <button
              className="rsum__approve"
              onClick={() => void api.reviewStep(selectedStepId, { kind: 'approve' })}
            >
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
        <>
          <div className="rsum__state rsum__state--done">
            <span className="rsum__state-icon">
              <CheckIcon size={17} />
            </span>
            <div className="rsum__state-text">
              <span className="rsum__state-title">승인 완료</span>
              <span className="rsum__state-sub mono">commit 채택됨 · {shortSha(selectedStepId)}</span>
            </div>
          </div>
          {detail.decision && (
            <div className="rsum__decision">
              <div className="rsum__decision-head">
                <DiamondIcon size={12} />
                <span className="kindtag">DECISION</span>
              </div>
              <p>{detail.decision}</p>
            </div>
          )}
        </>
      )}

      {status === 'planning' && (
        <div className="rsum__state rsum__state--wait">
          <span className="rsum__state-icon">
            <ClockIcon size={17} />
          </span>
          <div className="rsum__state-text">
            <span className="rsum__state-title">대기중</span>
            <span className="rsum__state-sub">이전 step이 승인되면 실행을 시작합니다.</span>
          </div>
        </div>
      )}

      {status === 'executing' && (
        <div className="rsum__state rsum__state--run">
          <span className="rsum__state-icon">
            <PlayIcon size={16} />
          </span>
          <div className="rsum__state-text">
            <span className="rsum__state-title">실행 중</span>
            <span className="rsum__state-sub">에이전트가 이 step을 작업하고 있습니다.</span>
          </div>
        </div>
      )}

      {status === 'blocked' && (
        <div className="rsum__state rsum__state--blocked">
          <span className="rsum__state-icon">
            <AlertIcon size={17} />
          </span>
          <div className="rsum__state-text">
            <span className="rsum__state-title">막힘</span>
            <span className="rsum__state-sub">step이 실패했습니다. 로그를 확인하세요.</span>
          </div>
        </div>
      )}
    </div>
  );
}
