import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useStore } from '../../store/useStore';
import type { EngineSpec, ModelsMap, ModelAvailability, ProjectModels } from '../../api/dto';
import { GovernanceLayout } from './GovernanceLayout';

type Scope = 'global' | 'project';

export function ModelsPage() {
  const { pid } = useParams();
  const api = useStore((s) => s.api);
  const [view, setView] = useState<ProjectModels | null>(null);
  const [avail, setAvail] = useState<ModelAvailability[]>([]);
  const [scope, setScope] = useState<Scope>('global');
  const [draft, setDraft] = useState<ModelsMap>({});
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ text: string; ok: boolean } | null>(null);
  const [helpOpen, setHelpOpen] = useState(false);

  useEffect(() => {
    if (pid) api.setPid(pid);
  }, [pid, api]);

  const load = () => {
    void api.getProjectModels().then((v) => {
      setView(v);
      setDraft({ ...(scope === 'global' ? v.global : v.project) });
    }, () => {});
  };
  useEffect(load, [api, pid]); // re-fetch when the route's :pid changes (same component instance)
  const loadAvail = () => void api.getModelAvailability().then(setAvail, () => {});
  useEffect(loadAvail, [api]); // availability is global (not pid-scoped)

  // switching scope re-seeds the editable draft from that scope's saved map
  const switchScope = (s: Scope) => {
    setScope(s);
    setNote(null);
    if (view) setDraft({ ...(s === 'global' ? view.global : view.project) });
  };

  const setTransport = (point: string, transport: string) => {
    setDraft((d) => {
      const next = { ...d };
      if (!transport) delete next[point];
      else next[point] = { transport, model: next[point]?.model ?? '' };
      return next;
    });
  };
  const setModel = (point: string, model: string) => {
    setDraft((d) => (d[point] ? { ...d, [point]: { ...d[point], model } } : d));
  };

  const save = async () => {
    setBusy(true);
    setNote(null);
    try {
      const updated = scope === 'global'
        ? // global PUT returns {points, transports, global}; refetch the project view for resolved
          (await api.setGlobalModels(draft), await api.getProjectModels())
        : await api.setProjectModels(draft);
      setView(updated);
      setDraft({ ...(scope === 'global' ? updated.global : updated.project) });
      setNote({ text: '저장됨', ok: true });
    } catch {
      setNote({ text: '저장 실패 — 다시 시도해 주세요.', ok: false });
    } finally {
      setBusy(false);
    }
  };

  if (!pid) return null;

  return (
    <GovernanceLayout
      pid={pid}
      active="models"
      lead="개입 지점별로 어떤 엔진(transport·model)이 호출되는지 정하는 라우팅 표. 전역 기본 프로필에 프로젝트별 오버라이드가 우선합니다. 각 지점은 실제 배선된 transport만 고를 수 있고, 지원하지 않는 값은 조용히 '실제(resolved)'로 대체됩니다. API 키는 환경변수로만 두고 여기엔 상태만 노출됩니다."
    >
      {view && (
        <section className="gov-card">
          <header className="gov-card__head">
            <span className="gov-card__title">모델 라우팅</span>
            <span className="gov-help">
              <button
                type="button"
                className="gov-help__btn"
                aria-label="사용 가능한 모델명 공식 문서"
                aria-expanded={helpOpen}
                title="어떤 model 이름을 쓸 수 있나요?"
                onClick={() => setHelpOpen((o) => !o)}
              >
                ?
              </button>
              {helpOpen && (
                <div className="gov-help__pop" role="dialog" aria-label="모델명 공식 문서">
                  <p className="gov-help__lead mono">사용 가능한 model 이름 (공식 문서)</p>
                  <a
                    href="https://docs.anthropic.com/en/docs/about-claude/models/overview"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Claude 모델명 <span className="mono">(claude CLI · anthropic-api)</span> ↗
                  </a>
                  <a href="https://platform.openai.com/docs/models" target="_blank" rel="noopener noreferrer">
                    OpenAI 모델명 <span className="mono">(codex CLI)</span> ↗
                  </a>
                  <a href="https://github.com/openai/codex" target="_blank" rel="noopener noreferrer">
                    Codex CLI 문서 <span className="mono">(설치·모델 지정)</span> ↗
                  </a>
                </div>
              )}
            </span>
            <div className="gov__tabs" role="group" aria-label="scope">
              <button
                className="gov__tab"
                aria-current={scope === 'global'}
                onClick={() => switchScope('global')}
              >
                전역
              </button>
              <button
                className="gov__tab"
                aria-current={scope === 'project'}
                onClick={() => switchScope('project')}
              >
                프로젝트
              </button>
            </div>
          </header>
          <div className="gov-card__body">
            <table className="gov-table">
              <thead>
                <tr>
                  <th scope="col">지점 (point)</th>
                  <th scope="col">transport</th>
                  <th scope="col">model</th>
                  <th scope="col">실제 (resolved)</th>
                </tr>
              </thead>
              <tbody>
                {view.points.map((point) => {
                  const spec: EngineSpec | undefined = draft[point];
                  const resolved = view.resolved[point];
                  // only transports actually wired for THIS point resolve; the rest are silently
                  // ignored by the backend and fall back — so offer only those + flag a stale one.
                  const allowed = view.supported?.[point] ?? view.transports;
                  const unsupported = !!spec?.transport && !allowed.includes(spec.transport);
                  return (
                    <tr key={point}>
                      <td className="gov-point">{point}</td>
                      <td>
                        <select
                          className={`gov-select${unsupported ? ' gov-select--warn' : ''}`}
                          aria-label={`${point} transport`}
                          value={spec?.transport ?? ''}
                          onChange={(e) => setTransport(point, e.target.value)}
                        >
                          <option value="">{scope === 'global' ? '(env 기본값)' : '(전역 따름)'}</option>
                          {allowed.map((t) => (
                            <option key={t} value={t}>
                              {t}
                            </option>
                          ))}
                          {unsupported && (
                            <option value={spec!.transport}>{spec!.transport} · 미지원</option>
                          )}
                        </select>
                      </td>
                      <td>
                        <input
                          className="gov-input"
                          aria-label={`${point} model`}
                          placeholder="claude-opus-4-8"
                          value={spec?.model ?? ''}
                          disabled={!spec || spec.transport === 'simulated'}
                          onChange={(e) => setModel(point, e.target.value)}
                        />
                      </td>
                      <td className="gov-resolved">
                        {resolved ? `${resolved.transport}${resolved.model ? ` · ${resolved.model}` : ''}` : '—'}
                        {unsupported && (
                          <span
                            className="gov-warn"
                            title={`이 지점은 '${spec!.transport}'를 지원하지 않아 위 엔진으로 대체됩니다`}
                          >
                            ⚠ 미지원 → 대체됨
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
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
      )}

      <section className="gov-card">
        <header className="gov-card__head">
          <span className="gov-card__title">엔진 상태 (health)</span>
          <span className="gov-card__hint">CLI 설치 / API 키 유무 — 비밀값은 노출하지 않음</span>
          <button
            className="btn btn--ghost"
            style={{ marginLeft: 'auto' }}
            onClick={loadAvail}
            aria-label="상태 새로고침"
          >
            새로고침
          </button>
        </header>
        <div className="gov-card__body">
          <div className="gov-health">
            {avail.map((e) => (
              <span
                key={e.transport}
                className={`gov-chip ${e.available ? 'gov-chip--ok' : 'gov-chip--off'}${
                  e.wired ? '' : ' gov-chip--stub'
                }`}
                title={e.detail}
              >
                <span className="gov-dot" aria-hidden="true" />
                {e.transport}
                {!e.wired && ' · stub'}
              </span>
            ))}
          </div>
        </div>
      </section>
    </GovernanceLayout>
  );
}
