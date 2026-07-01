import { useEffect, useMemo, useRef, useState } from 'react';
import { useStore } from '../../store/useStore';
import { neighbors } from '../../domain/graph';
import type { ChannelMessage, ReviewAction } from '../../api/dto';
import { CheckIcon, EditIcon, TakeoverIcon } from '../icons';
import './channel.css';

const TYPE_META: Record<ChannelMessage['type'], { label: string; cls: string }> = {
  assumption: { label: '가정', cls: 'assumption' },
  blocked: { label: '막힘', cls: 'blocked' },
  decision: { label: '결정', cls: 'decision' },
  review: { label: '리뷰', cls: 'review' },
  steer: { label: '지시', cls: 'steer' },
  system: { label: '시스템', cls: 'system' },
  clarify: { label: '되물음', cls: 'clarify' },
};

/** The always-on steer input (channel bottom): free NL -> POST /steer -> op executes. */
function SteerInput() {
  const api = useStore((s) => s.api);
  const loadMessages = useStore((s) => s.loadMessages);
  const setError = useStore((s) => s.setError);
  const selectedTicketId = useStore((s) => s.selectedTicketId);
  const selectedStepId = useStore((s) => s.selectedStepId);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);

  const send = async () => {
    const t = text.trim();
    if (!t || busy) return;
    setBusy(true);
    try {
      await api.steer(t, {
        ticketId: selectedTicketId ?? undefined,
        stepId: selectedStepId ?? undefined,
      });
      setText('');
      await loadMessages(); // pull the user + result messages the op just posted
    } catch (e) {
      setError(`지시 처리에 실패했습니다: ${e instanceof Error ? e.message : '알 수 없는 오류'}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form
      className="channel__steer"
      onSubmit={(e) => {
        e.preventDefault();
        void send();
      }}
    >
      <input
        className="channel__steer-input"
        aria-label="steer 입력"
        placeholder="무엇이든 지시… (use Stripe · auth 건드리지 마 · pause)"
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={busy}
      />
      <button className="btn btn--primary" type="submit" disabled={busy || !text.trim()}>
        전송
      </button>
    </form>
  );
}

/** The approve/수정요청/인수 actions on a `review` message — reuses the existing reviewStep
 *  flow (CP2 promotes the review gate into this channel message). Hidden once the step is no
 *  longer actionable (already reviewed). */
function ReviewActions({ stepId }: { stepId: string }) {
  const api = useStore((s) => s.api);
  const graph = useStore((s) => s.graph);
  const setError = useStore((s) => s.setError);
  const [commenting, setCommenting] = useState(false);
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);

  if (!graph) return null; // graph not loaded yet -> unknown, NOT "processed" (don't hide a live gate)
  const node = graph.nodes.find((n) => n.id === stepId);
  const actionable = !!node && (node.status === 'awaiting_review' || node.status === 'blocked');
  if (!actionable) return <span className="chan-msg__done mono">처리됨</span>;

  const act = async (action: ReviewAction) => {
    setBusy(true);
    try {
      await api.reviewStep(stepId, action);
      setCommenting(false);
      setComment('');
    } catch (e) {
      setError(`리뷰 적용에 실패했습니다: ${e instanceof Error ? e.message : '알 수 없는 오류'}`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="chan-actions">
      <div className="chan-actions__row">
        <button className="chan-btn" disabled={busy} onClick={() => setCommenting((v) => !v)}>
          <EditIcon size={13} />
          수정요청
        </button>
        <button className="chan-btn" disabled={busy} onClick={() => act({ kind: 'takeover' })}>
          <TakeoverIcon size={13} />
          인수
        </button>
        <button
          className="chan-btn chan-btn--primary"
          disabled={busy}
          onClick={() => act({ kind: 'approve' })}
        >
          <CheckIcon size={13} />
          승인
        </button>
      </div>
      {commenting && (
        <div className="chan-comment">
          <textarea
            aria-label="수정 요청 내용"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="무엇을 바꿔야 하는지 적어주세요…"
          />
          <button
            className="chan-btn chan-btn--primary"
            disabled={busy}
            onClick={() => act({ kind: 'changes', comment })}
          >
            변경 요청 보내기
          </button>
        </div>
      )}
    </div>
  );
}

/** CP2 conversation channel — the agent's typed messages (assumption/blocked/decision/review)
 *  as the lifecycle advances; review messages carry the review-gate actions. */
export function ChannelPanel() {
  const messages = useStore((s) => s.messages);
  const graph = useStore((s) => s.graph);
  const channelFilter = useStore((s) => s.channelFilter);
  const setChannelFilter = useStore((s) => s.setChannelFilter);
  const focusNode = useStore((s) => s.focusNode);
  const endRef = useRef<HTMLDivElement>(null);

  // CP4 channel<->map: when a node is selected on the map, show only its thread. A ticket's
  // thread = messages ref-ing the ticket OR any of its owned steps/decisions (its conversation
  // rides on step ids, so filtering by the bare ticket id alone would collapse it to empty).
  // A message ref chip highlights the node back on the map (focusNode).
  const filterIds = useMemo(() => {
    if (!channelFilter) return null;
    const ids = new Set<string>([channelFilter]);
    if (graph) for (const n of neighbors(graph, channelFilter, 'out')) ids.add(n.id);
    return ids;
  }, [channelFilter, graph]);
  const shown = filterIds ? messages.filter((m) => m.refs.some((r) => filterIds.has(r))) : messages;
  const labelOf = (id: string) => graph?.nodes.find((n) => n.id === id)?.label ?? id;

  useEffect(() => {
    // optional-chain the method too: jsdom (tests) doesn't implement scrollIntoView.
    endRef.current?.scrollIntoView?.({ block: 'end' });
  }, [shown.length]);

  // Only the LATEST review message per step carries live actions — earlier ones are past gates
  // (e.g. a `changes` re-run posts a fresh review; the older prompt is now resolved).
  const latestReviewByStep = new Map<string, number>();
  for (const m of messages) {
    if (m.type === 'review' && m.refs[0]) latestReviewByStep.set(m.refs[0], m.id);
  }

  return (
    <aside className="channel" aria-label="대화 채널">
      <header className="channel__head">
        <span className="channel__title">대화 채널</span>
        <span className="channel__count mono">{shown.length}</span>
      </header>
      {channelFilter && (
        <div className="channel__filter">
          <span className="mono">필터: {labelOf(channelFilter)}</span>
          <button className="channel__filter-clear" aria-label="필터 해제" onClick={() => setChannelFilter(null)}>
            ✕
          </button>
        </div>
      )}
      <div className="channel__list">
        {shown.length === 0 ? (
          <p className="channel__empty mono">
            {channelFilter ? '이 노드에 연결된 메시지가 없습니다.' : '아직 메시지가 없습니다. 에이전트가 진행하면 여기에 쌓입니다.'}
          </p>
        ) : (
          shown.map((m) => {
            const meta = TYPE_META[m.type];
            return (
              <article key={m.id} className={`chan-msg chan-msg--${meta.cls}`}>
                <div className="chan-msg__head">
                  <span className={`chan-tag chan-tag--${meta.cls}`}>{meta.label}</span>
                  <span className="chan-msg__author mono">{m.author}</span>
                </div>
                <p className="chan-msg__text">{m.text}</p>
                {m.refs.length > 0 && (
                  <div className="chan-refs">
                    {m.refs.map((r) => (
                      <button key={r} className="chan-ref" title="지도에서 보기" onClick={() => focusNode(r)}>
                        {labelOf(r)}
                      </button>
                    ))}
                  </div>
                )}
                {m.type === 'review' && m.refs[0] && latestReviewByStep.get(m.refs[0]) === m.id && (
                  <ReviewActions stepId={m.refs[0]} />
                )}
              </article>
            );
          })
        )}
        <div ref={endRef} />
      </div>
      <SteerInput />
    </aside>
  );
}
