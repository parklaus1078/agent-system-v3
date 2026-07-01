import { useEffect, useRef, useState } from 'react';
import { useStore } from '../../store/useStore';
import type { TicketProposal } from '../../api/dto';
import { LayersIcon, CheckIcon, PlusIcon, XIcon, ArrowRightIcon } from '../icons';
import '../plan/PlanApproval.css';

/** Landing "분해 시작": initialize a PROJECT (not a ticket). The project planner proposes
 *  {slug, title, tickets[]}; the user edits and approves; the project is created (objective
 *  + planning tickets) and we offer to open its map. Tickets get decomposed into steps later
 *  (click a planning ticket on the map → PlanApproval). */
export function ProjectInit({
  goal,
  onCancel,
  onCreated,
  onGoToMap,
  onStay,
}: {
  goal: string;
  onCancel: () => void;
  onCreated?: () => void; // refresh the landing list (a new project now exists)
  onGoToMap: (slug: string) => void;
  onStay: () => void;
}) {
  const api = useStore((s) => s.api);
  const [phase, setPhase] = useState<'loading' | 'edit' | 'done'>('loading');
  const [slug, setSlug] = useState('');
  const [title, setTitle] = useState(goal);
  // The full goal text becomes the project description (the title is only its first line),
  // so the original intent is preserved + viewable/editable later instead of being discarded.
  const [description, setDescription] = useState(goal);
  const [tickets, setTickets] = useState<TicketProposal[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [createdSlug, setCreatedSlug] = useState('');
  const initialized = useRef(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  // Propose the project once (the planner call is live; show elapsed seconds).
  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    let settled = false;
    const timeout = setTimeout(() => {
      if (settled || !mounted.current) return;
      settled = true;
      setError('프로젝트 제안이 지연되고 있습니다. 서버/Claude CLI 상태를 확인해 주세요.');
      setPhase('edit');
    }, 90_000);
    api.proposeProject(goal).then(
      (p) => {
        settled = true;
        clearTimeout(timeout);
        if (!mounted.current) return;
        setSlug(p.slug);
        setTitle(p.title);
        setTickets(p.tickets);
        setPhase('edit');
      },
      () => {
        settled = true;
        clearTimeout(timeout);
        if (!mounted.current) return;
        setError('프로젝트 제안을 불러오지 못했습니다. 서버 연결을 확인해 주세요.');
        setPhase('edit');
      },
    );
  }, [api, goal]);

  useEffect(() => {
    if (phase !== 'loading') return;
    const id = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, [phase]);

  const setTicketTitle = (i: number, t: string) =>
    setTickets((ts) => ts.map((x, j) => (j === i ? { ...x, title: t } : x)));
  const removeTicket = (i: number) => setTickets((ts) => ts.filter((_, j) => j !== i));
  const addTicket = () => setTickets((ts) => [...ts, { title: '새 티켓' }]);

  const approve = async () => {
    setBusy(true);
    setError(null);
    try {
      const created = await api.approveProject({
        slug: slug.trim(),
        title: title.trim() || slug.trim(),
        tickets: tickets.filter((t) => t.title.trim()),
        description: description.trim() || undefined,
      });
      onCreated?.();
      setCreatedSlug(created.projectId);
      setPhase('done');
    } catch {
      setError('프로젝트 생성에 실패했습니다. 다시 시도해 주세요.');
      setBusy(false);
    }
  };

  if (phase === 'loading') {
    return (
      <div className="plan plan--loading">
        <span className="plan__spinner" aria-hidden="true" />
        <span>
          프로젝트를 구성하는 중… <span className="mono">{elapsed}s</span>
        </span>
        <span className="plan__loadhint">PLAN 에이전트가 목표를 티켓으로 분해하고 있습니다.</span>
      </div>
    );
  }

  if (phase === 'done') {
    return (
      <div className="plan">
        <header className="plan__head">
          <div className="plan__title">
            <CheckIcon size={16} />
            <span className="plan__goal">프로젝트 생성됨</span>
          </div>
        </header>
        <p className="plan__hint">
          <b>{title}</b> 프로젝트가 {tickets.length}개 티켓으로 생성되었습니다. 지도로 이동하시겠어요?
        </p>
        <footer className="plan__foot">
          <span className="plan__note">아니오를 누르면 목록에 남고, 나중에 카드로 열 수 있습니다.</span>
          <div className="plan__actions">
            <button className="btn btn--ghost" onClick={onStay}>
              아니오, 목록 유지
            </button>
            <button className="btn btn--primary" onClick={() => onGoToMap(createdSlug)}>
              지도로 이동
              <ArrowRightIcon size={15} />
            </button>
          </div>
        </footer>
      </div>
    );
  }

  return (
    <div className="plan">
      <header className="plan__head">
        <div className="plan__title">
          <LayersIcon size={16} />
          <input
            className="plan-step__input"
            aria-label="프로젝트 제목"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </div>
        <button className="plan__close" aria-label="닫기" onClick={onCancel} disabled={busy}>
          <XIcon size={16} />
        </button>
      </header>

      <label className="plan__sluglabel">
        <span className="plan__slugcap mono">/project/</span>
        <input
          className="plan-step__input"
          aria-label="프로젝트 slug"
          value={slug}
          onChange={(e) => setSlug(e.target.value)}
        />
      </label>

      <label className="plan__desclabel">
        <span className="plan__desccap">설명</span>
        <textarea
          className="plan__descinput"
          aria-label="프로젝트 설명"
          placeholder="이 프로젝트가 무엇을 만드는지 — 나중에 프로젝트 안에서 다시 보고 수정할 수 있어요."
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={3}
        />
      </label>

      <p className="plan__hint">
        PLAN 에이전트가 <b>{tickets.length}개 티켓</b>을 제안했습니다. 편집·승인하면 프로젝트가 생성되고
        각 티켓을 열어 sub-task로 분해합니다.
      </p>

      <ol className="plan__list">
        {tickets.map((t, i) => (
          <li key={i} className="plan-step">
            <span className="plan-step__num mono">{String(i + 1).padStart(2, '0')}</span>
            <input
              className="plan-step__input"
              aria-label={`티켓 ${i + 1}`}
              value={t.title}
              onChange={(e) => setTicketTitle(i, e.target.value)}
            />
            <button
              className="plan-step__remove"
              aria-label="삭제"
              disabled={tickets.length <= 1}
              onClick={() => removeTicket(i)}
            >
              <XIcon size={14} />
            </button>
          </li>
        ))}
      </ol>

      <button className="plan__add" onClick={addTicket}>
        <PlusIcon size={14} />
        티켓 추가
      </button>

      <footer className="plan__foot">
        <span className="plan__note">
          {error ? (
            <span className="plan__error" role="alert">
              {error}
            </span>
          ) : (
            'slug·제목·티켓은 승인 전까지 편집 가능합니다.'
          )}
        </span>
        <div className="plan__actions">
          <button className="btn btn--ghost" onClick={onCancel} disabled={busy}>
            취소
          </button>
          <button
            className="btn btn--primary"
            disabled={busy || !slug.trim() || tickets.filter((t) => t.title.trim()).length === 0}
            onClick={approve}
          >
            {busy ? (
              <>
                <span className="plan__spinner plan__spinner--on-dark" aria-hidden="true" />
                프로젝트 생성 중…
              </>
            ) : (
              <>
                <CheckIcon size={15} />
                프로젝트 생성
              </>
            )}
          </button>
        </div>
      </footer>
    </div>
  );
}
