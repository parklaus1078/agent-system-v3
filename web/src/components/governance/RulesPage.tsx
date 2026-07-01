import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useStore } from '../../store/useStore';
import type { Rules } from '../../api/dto';
import { GovernanceLayout } from './GovernanceLayout';

/** A coding + planning editor card (one scope: global or project). Saves via `onSave`. */
function RulesCard({
  title,
  hint,
  value,
  onSave,
}: {
  title: string;
  hint: string;
  value: Rules;
  onSave: (rules: Rules) => Promise<void>;
}) {
  const [coding, setCoding] = useState(value.coding);
  const [planning, setPlanning] = useState(value.planning);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ text: string; ok: boolean } | null>(null);

  // keep local fields in sync when the loaded value arrives/changes
  useEffect(() => {
    setCoding(value.coding);
    setPlanning(value.planning);
  }, [value.coding, value.planning]);

  const save = async () => {
    setBusy(true);
    setNote(null);
    try {
      await onSave({ coding, planning });
      setNote({ text: '저장됨', ok: true });
    } catch {
      setNote({ text: '저장 실패 — 다시 시도해 주세요.', ok: false });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="gov-card">
      <header className="gov-card__head">
        <span className="gov-card__title">{title}</span>
        <span className="gov-card__hint">{hint}</span>
      </header>
      <div className="gov-card__body">
        <label className="gov-field">
          <span className="gov-field__cap">coding → executor</span>
          <textarea
            className="gov-area"
            aria-label={`${title} coding rules`}
            value={coding}
            onChange={(e) => setCoding(e.target.value)}
          />
        </label>
        <label className="gov-field">
          <span className="gov-field__cap">planning → project/ticket planner</span>
          <textarea
            className="gov-area"
            aria-label={`${title} planning rules`}
            value={planning}
            onChange={(e) => setPlanning(e.target.value)}
          />
        </label>
      </div>
      <footer className="gov-card__foot">
        {note && (
          <span className={`gov-note ${note.ok ? 'gov-note--ok' : 'gov-note--err'}`} role="status">
            {note.text}
          </span>
        )}
        <button className="btn btn--primary" onClick={save} disabled={busy}>
          저장
        </button>
      </footer>
    </section>
  );
}

/** Rules page (/project/:pid/rules): edit the global default + the project override, and
 *  preview the effective (merged) rules that are actually injected into prompts. */
export function RulesPage() {
  const { pid } = useParams();
  const api = useStore((s) => s.api);
  const [view, setView] = useState<{ project: Rules; global: Rules; resolved: Rules } | null>(null);

  useEffect(() => {
    if (pid) api.setPid(pid);
  }, [pid, api]);

  const load = () => void api.getProjectRules().then(setView, () => {});
  useEffect(load, [api, pid]); // re-fetch when the route's :pid changes (same component instance)

  if (!pid) return null;

  return (
    <GovernanceLayout
      pid={pid}
      active="rules"
      lead="에이전트가 따르는 규칙. coding 룰은 executor 프롬프트에, planning 룰은 planner 프롬프트에 주입됩니다. 전역 기본값에 프로젝트 규칙이 덧붙습니다."
    >
      {view && (
        <>
          <RulesCard
            title="전역 기본 규칙"
            hint="모든 프로젝트에 적용"
            value={view.global}
            onSave={async (r) => {
              await api.setGlobalRules(r);
              load();
            }}
          />
          <RulesCard
            title="프로젝트 규칙 (오버라이드)"
            hint={`${pid} 에만 적용 — 전역에 덧붙음`}
            value={view.project}
            onSave={async (r) => {
              await api.setProjectRules(r);
              load();
            }}
          />
          <section className="gov-card">
            <header className="gov-card__head">
              <span className="gov-card__title">실제 주입되는 규칙 (resolved)</span>
              <span className="gov-card__hint">전역 + 프로젝트 병합 결과</span>
            </header>
            <div className="gov-card__body">
              <label className="gov-field">
                <span className="gov-field__cap">coding</span>
                <textarea
                  className="gov-area gov-area--resolved"
                  aria-label="resolved coding rules"
                  readOnly
                  value={view.resolved.coding}
                />
              </label>
              <label className="gov-field">
                <span className="gov-field__cap">planning</span>
                <textarea
                  className="gov-area gov-area--resolved"
                  aria-label="resolved planning rules"
                  readOnly
                  value={view.resolved.planning}
                />
              </label>
            </div>
          </section>
        </>
      )}
    </GovernanceLayout>
  );
}
