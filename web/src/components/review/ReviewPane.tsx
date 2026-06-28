import { useState } from 'react';
import { useStore } from '../../store/useStore';
import type { Status } from '../../domain/graph';
import { DiffView } from './DiffView';
import { useStepDetail } from './useStepDetail';
import {
  ChevronRightIcon,
  CheckIcon,
  EditIcon,
  TakeoverIcon,
  DiamondIcon,
  FlaskIcon,
  CodeIcon,
} from '../icons';
import './review.css';

const STATUS_LABEL: Record<Status, string> = {
  planning: 'planning',
  executing: 'executing',
  awaiting_review: 'review gate',
  done: 'done',
  blocked: 'blocked',
};

function countDiff(patches: string[], sign: '+' | '-'): number {
  const meta = sign === '+' ? '+++' : '---';
  return patches.reduce(
    (n, p) => n + p.split('\n').filter((l) => l.startsWith(sign) && !l.startsWith(meta)).length,
    0,
  );
}

export function ReviewPane() {
  const graph = useStore((s) => s.graph);
  const selectedStepId = useStore((s) => s.selectedStepId);
  const api = useStore((s) => s.api);
  const closeReview = useStore((s) => s.closeReview);
  const detail = useStepDetail(selectedStepId);
  const [commenting, setCommenting] = useState(false);
  const [comment, setComment] = useState('');

  if (!selectedStepId || !detail) {
    return (
      <div className="review review--empty">
        <p>리뷰 대기 중인 step이 없습니다.</p>
      </div>
    );
  }

  const node = detail.node;
  const status = (node.status ?? 'awaiting_review') as Status;
  const labelOf = (id: string) => graph?.nodes.find((n) => n.id === id)?.label ?? id;

  // tests connected to this step (via its code regions' tested_by, or directly)
  const testNodes = graph
    ? graph.nodes.filter(
        (n) =>
          n.kind === 'test' &&
          graph.edges.some(
            (e) =>
              e.kind === 'tested_by' &&
              e.to === n.id &&
              (e.from === selectedStepId || detail.createdNodeIds.includes(e.from)),
          ),
      )
    : [];

  const added = countDiff(detail.diff.map((d) => d.patch), '+');
  const removed = countDiff(detail.diff.map((d) => d.patch), '-');
  const acceptanceMet = detail.acceptance.filter((a) => a.met).length;

  async function act(action: Parameters<typeof api.reviewStep>[1]) {
    await api.reviewStep(selectedStepId!, action);
    closeReview();
  }

  return (
    <div className="review review--full">
      <header className="review__subbar">
        <button className="review__back" onClick={closeReview}>
          <ChevronRightIcon size={14} style={{ transform: 'rotate(180deg)' }} />
          레인
        </button>
        <span className={`review__badge pill pill--${status}`}>
          <span className="dot" />
          step · {STATUS_LABEL[status]}
        </span>
        <h2 className="review__title">{node.label}</h2>
        <span className="review__stats mono">
          <span className="review__add">+{added}</span> <span className="review__del">−{removed}</span> ·{' '}
          {detail.diff.length} files
        </span>
      </header>

      <div className="review__panes">
        <div className="review__left">
          <DiffView diff={detail.diff} />
        </div>

        <div className="review__right">
          <section className="rev-card">
            <div className="rev-card__head">
              <CodeIcon size={14} />
              <span>이 step이 만든 지도 조각</span>
              <span className="rev-card__count mono">
                +{detail.createdNodeIds.length + detail.createdEdgeIds.length} 노드·엣지
              </span>
            </div>
            <ul className="rev-slice">
              {detail.createdNodeIds.map((id) => (
                <li key={id} className="rev-slice__row">
                  <span className="mono">{labelOf(id)}</span>
                  <span className="rev-tag rev-tag--code">CodeRegion · NEW</span>
                </li>
              ))}
              {testNodes.map((t) => (
                <li key={t.id} className="rev-slice__row">
                  <span className="mono">{t.label}</span>
                  <span className="rev-tag rev-tag--test">tested_by</span>
                </li>
              ))}
              {detail.decision && (
                <li className="rev-slice__row">
                  <span>{detail.decision}</span>
                  <span className="rev-tag rev-tag--dec">decided</span>
                </li>
              )}
            </ul>
          </section>

          {detail.decision && (
            <section className="rev-card">
              <div className="rev-card__head">
                <DiamondIcon size={14} />
                <span>Decision — 왜</span>
              </div>
              <p className="rev-decision">{detail.decision}</p>
            </section>
          )}

          <section className="rev-card">
            <div className="rev-card__head">
              <span>Acceptance</span>
              <span className="rev-card__count mono">
                {acceptanceMet} / {detail.acceptance.length}
              </span>
            </div>
            <ul className="rev-accept">
              {detail.acceptance.map((a, i) => (
                <li key={i} className={a.met ? 'is-met' : ''}>
                  <span className="rev-accept__check">
                    <CheckIcon size={12} />
                  </span>
                  {a.text}
                </li>
              ))}
            </ul>
          </section>

          <section className="rev-card">
            <div className="rev-card__head">
              <FlaskIcon size={14} />
              <span>Tests</span>
              <span className="rev-card__count rev-card__count--ok">● green</span>
            </div>
            <ul className="rev-tests">
              {testNodes.length > 0 ? (
                testNodes.map((t) => (
                  <li key={t.id}>
                    <CheckIcon size={12} />
                    <span className="mono">{t.label}</span>
                    <span className="rev-tests__pass">passed</span>
                  </li>
                ))
              ) : (
                <li className="rev-tests__none">연결된 테스트 없음</li>
              )}
            </ul>
          </section>
        </div>
      </div>

      <footer className="review__actions">
        <div className="review__hint mono">step 게이트 — 당신의 결정을 기다립니다</div>
        <div className="review__btns">
          <button className="rev-act" onClick={() => setCommenting((v) => !v)}>
            <EditIcon size={15} />
            수정요청
            <kbd className="rev-kbd" aria-hidden="true">
              R
            </kbd>
          </button>
          <button className="rev-act" onClick={() => act({ kind: 'takeover' })}>
            <TakeoverIcon size={15} />
            내가 인수
            <kbd className="rev-kbd" aria-hidden="true">
              T
            </kbd>
          </button>
          <button className="rev-act rev-act--primary" onClick={() => act({ kind: 'approve' })}>
            <CheckIcon size={15} />
            승인
            <kbd className="rev-kbd rev-kbd--on-dark" aria-hidden="true">
              A
            </kbd>
          </button>
        </div>
      </footer>

      {commenting && (
        <div className="review__comment">
          <textarea
            className="review__comment-input"
            placeholder="무엇을 바꿔야 하는지 적어주세요…"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
          />
          <button
            className="rev-act rev-act--primary"
            onClick={() => act({ kind: 'changes', comment })}
          >
            변경 요청 보내기
          </button>
        </div>
      )}
    </div>
  );
}
