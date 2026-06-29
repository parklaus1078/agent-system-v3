import { useRef, useState } from 'react';
import { TargetIcon, ArrowRightIcon, XIcon } from '../icons';
import './GoalEntry.css';

/** New-goal input. Submitting hands the goal up so the planner can decompose it. */
export function GoalEntry({
  onSubmit,
  onCancel,
}: {
  onSubmit: (goal: string) => void;
  onCancel: () => void;
}) {
  const [goal, setGoal] = useState('');
  const trimmed = goal.trim();
  // Guard against double-submit (button + Cmd/Ctrl+Enter firing twice).
  const submitted = useRef(false);
  const submit = () => {
    if (submitted.current || !trimmed) return;
    submitted.current = true;
    onSubmit(trimmed);
  };

  return (
    <div className="goal">
      <header className="goal__head">
        <div className="goal__title">
          <TargetIcon size={16} />
          <span>새 목표</span>
        </div>
        <button className="goal__close" aria-label="닫기" onClick={onCancel}>
          <XIcon size={16} />
        </button>
      </header>
      <p className="goal__hint">
        무엇을 만들까요? PLAN 에이전트가 목표를 step으로 분해하고, 승인하면 실행이 시작됩니다.
      </p>
      <textarea
        className="goal__input"
        aria-label="목표"
        placeholder="예: 구독 결제 붙이기"
        value={goal}
        autoFocus
        onChange={(e) => setGoal(e.target.value)}
        onKeyDown={(e) => {
          if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') submit();
        }}
      />
      <footer className="goal__foot">
        <button className="btn btn--ghost" onClick={onCancel}>
          취소
        </button>
        <button className="btn btn--primary" disabled={!trimmed} onClick={submit}>
          분해 시작
          <ArrowRightIcon size={15} />
        </button>
      </footer>
    </div>
  );
}
