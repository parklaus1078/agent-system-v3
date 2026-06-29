import { useEffect, useRef, useState } from 'react';
import { useStore } from '../../store/useStore';
import { neighbors } from '../../domain/graph';
import type { PlanProposal } from '../../api/dto';
import { LayersIcon, CheckIcon, PlusIcon, XIcon, ChevronUpIcon, ChevronDownIcon } from '../icons';
import './PlanApproval.css';

type Step = PlanProposal['steps'][number];

/** Edit + approve a ticket's steps. Two modes:
 *  - `goal`: ask the planner to propose steps for a new goal.
 *  - `ticketId`: edit an existing (planning) ticket's proposed steps.
 *  Approving starts execution (each step then stops at its own review gate). */
export function PlanApproval({
  goal,
  ticketId,
  onApproved,
  onCancel,
}: {
  goal?: string;
  ticketId?: string;
  onApproved: () => void;
  onCancel?: () => void;
}) {
  const api = useStore((s) => s.api);
  const graph = useStore((s) => s.graph);
  const [steps, setSteps] = useState<Step[]>([]);
  const [ready, setReady] = useState(false);
  const [title, setTitle] = useState('');
  const [tag, setTag] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Initialize the editable steps ONCE — not on every live graph reload, which
  // would otherwise wipe the user's in-progress add/remove/reorder edits.
  const initialized = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (initialized.current) return;
    if (ticketId) {
      if (!graph) return; // wait until the graph is loaded, then init once
      const ticket = graph.nodes.find((n) => n.id === ticketId);
      const tkSteps = neighbors(graph, ticketId, 'out').filter((n) => n.kind === 'step');
      setTitle(ticket?.label ?? '');
      setTag((ticket?.data?.tag as string) ?? null);
      setSteps(tkSteps.map((s) => ({ label: s.label, intent: '', acceptance: '' })));
      setReady(true);
      initialized.current = true;
    } else if (goal) {
      initialized.current = true;
      setTitle(goal);
      setTag(null);
      void api.proposePlan(goal).then((p) => {
        if (mounted.current) {
          setSteps(p.steps);
          setReady(true);
        }
      });
    }
  }, [api, graph, goal, ticketId]);

  const setLabel = (i: number, label: string) =>
    setSteps((s) => s.map((st, j) => (j === i ? { ...st, label } : st)));
  const remove = (i: number) => setSteps((s) => s.filter((_, j) => j !== i));
  const move = (i: number, dir: -1 | 1) =>
    setSteps((s) => {
      const j = i + dir;
      if (j < 0 || j >= s.length) return s;
      const next = s.slice();
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
  const add = () => setSteps((s) => [...s, { label: '새 step', intent: '', acceptance: '' }]);

  const approve = async () => {
    setBusy(true);
    await api.approvePlan({ ticketId: ticketId ?? 't-new', steps });
    onApproved();
  };

  if (!ready) {
    return <div className="plan plan--loading">플랜을 생성하는 중…</div>;
  }

  return (
    <div className="plan">
      <header className="plan__head">
        <div className="plan__title">
          {tag ? <span className="plan__tag kindtag">{tag}</span> : <LayersIcon size={16} />}
          <span className="plan__goal">{title}</span>
        </div>
        {onCancel && (
          <button className="plan__close" aria-label="닫기" onClick={onCancel}>
            <XIcon size={16} />
          </button>
        )}
      </header>
      <p className="plan__hint">
        PLAN 에이전트가 <b>{steps.length}개 step</b>을 제안했습니다. 편집·승인하면 실행이 시작되고
        step마다 정지해 리뷰합니다.
      </p>

      <ol className="plan__list">
        {steps.map((st, i) => (
          <li key={i} className="plan-step">
            <div className="plan-step__reorder">
              <button aria-label="위로" disabled={i === 0} onClick={() => move(i, -1)}>
                <ChevronUpIcon size={13} />
              </button>
              <button aria-label="아래로" disabled={i === steps.length - 1} onClick={() => move(i, 1)}>
                <ChevronDownIcon size={13} />
              </button>
            </div>
            <span className="plan-step__num mono">{String(i + 1).padStart(2, '0')}</span>
            <input
              className="plan-step__input"
              aria-label={`step ${i + 1}`}
              value={st.label}
              onChange={(e) => setLabel(i, e.target.value)}
            />
            <button
              className="plan-step__remove"
              aria-label="삭제"
              disabled={steps.length <= 1}
              onClick={() => remove(i)}
            >
              <XIcon size={14} />
            </button>
          </li>
        ))}
      </ol>

      <button className="plan__add" onClick={add}>
        <PlusIcon size={14} />
        step 추가
      </button>

      <footer className="plan__foot">
        <span className="plan__note">순서·내용은 언제든 편집 가능합니다.</span>
        <div className="plan__actions">
          {onCancel && (
            <button className="btn btn--ghost" onClick={onCancel}>
              취소
            </button>
          )}
          <button className="btn btn--primary" disabled={busy} onClick={approve}>
            <CheckIcon size={15} />
            승인하고 실행 시작
          </button>
        </div>
      </footer>
    </div>
  );
}
