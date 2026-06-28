import { useStore } from '../../store/useStore';
import type { Status } from '../../domain/graph';
import { useStepDetail, stepIndexLabel } from './useStepDetail';
import { DiamondIcon, CheckIcon, ArrowRightIcon, TargetIcon } from '../icons';

const STATUS_LABEL: Record<Status, string> = {
  planning: 'planning',
  executing: 'executing',
  awaiting_review: 'awaiting review',
  done: 'done',
  blocked: 'blocked',
};

/** Compact review shown in the cockpit's right column. "전체 리뷰" opens the gate. */
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

  const status = (detail.node.status ?? 'awaiting_review') as Status;
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
    </div>
  );
}
