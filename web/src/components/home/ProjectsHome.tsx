import { useEffect, useState } from 'react';
import { useStore } from '../../store/useStore';
import { ticketDisplayStatus } from '../../domain/graph';
import type { ProjectInfo } from '../../api/dto';
import { Modal } from '../Modal';
import { PlanApproval } from '../plan/PlanApproval';
import { ArrowRightIcon } from '../icons';
import './ProjectsHome.css';

/** Project management / landing page (reached via the Control Tower brand).
 *  Lists in-progress projects and starts new goals. v1 has the single mock
 *  project, derived from the loaded graph. */
export function ProjectsHome({ onOpenProject }: { onOpenProject: () => void }) {
  const graph = useStore((s) => s.graph);
  const load = useStore((s) => s.load);
  const api = useStore((s) => s.api);
  const setError = useStore((s) => s.setError);
  const [goal, setGoal] = useState('');
  const [planning, setPlanning] = useState(false);
  const [info, setInfo] = useState<ProjectInfo | null>(null);
  const [editingRepo, setEditingRepo] = useState(false);
  const [repoInput, setRepoInput] = useState('');

  useEffect(() => {
    if (!graph) void load();
  }, [graph, load]);

  // The project's target repo (where its executor commits) — a per-project BE value.
  useEffect(() => {
    void api.getProjectInfo().then(setInfo, () => {});
  }, [api]);

  const saveRepo = async () => {
    try {
      setInfo(await api.setProjectRepo(repoInput.trim() || null));
      setEditingRepo(false);
    } catch (e) {
      setError(`레포 경로 저장 실패: ${e instanceof Error ? e.message : '알 수 없는 오류'}`);
    }
  };

  const objective = graph?.nodes.find((n) => n.kind === 'objective');
  const tickets = graph?.nodes.filter((n) => n.kind === 'ticket') ?? [];
  const steps = graph?.nodes.filter((n) => n.kind === 'step') ?? [];
  const awaiting = steps.filter((s) => s.status === 'awaiting_review').length;
  const trimmed = goal.trim();

  return (
    <div className="home">
      <h1 className="sr-only">LLM Dev Control Tower</h1>
      <header className="home__bar">
        <div className="home__brand">
          <span className="home__logo" aria-hidden="true">
            CT
          </span>
          <span className="home__brand-name">Control Tower</span>
        </div>
        <span className="home__env mono">local · single-user</span>
      </header>

      <main className="home__main">
        <section className="home__section">
          <h2 className="home__label">새 목표</h2>
          <div className="home__goalcard">
            <textarea
              className="home__goalinput"
              aria-label="새 목표"
              placeholder={'거친 목표를 한 줄~문단으로. 예: "Todo 앱에 Free/Pro/Team 구독 티어와 기능 게이팅을 붙인다."'}
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
            />
            <div className="home__goalfoot">
              <span className="home__goalhint">PLAN 에이전트가 step으로 분해 → 승인 후 실행</span>
              <button
                className="btn btn--primary"
                onClick={() => {
                  if (trimmed) setPlanning(true);
                }}
              >
                분해 시작
                <ArrowRightIcon size={15} />
              </button>
            </div>
          </div>
        </section>

        <section className="home__section">
          <h2 className="home__label">진행 중인 프로젝트</h2>
          {objective && (
            <button className="home__project" onClick={onOpenProject}>
              <div className="home__project-head">
                <span className="home__project-name">{objective.label}</span>
                <span className="home__project-meta mono">
                  {tickets.length} tickets · {steps.length} steps
                </span>
                {awaiting > 0 && (
                  <span className="home__project-await">
                    <span className="home__await-dot" />
                    {awaiting}건 리뷰 대기
                  </span>
                )}
              </div>
              {typeof objective.data?.description === 'string' && (
                <p className="home__project-desc">{objective.data.description}</p>
              )}
              <div className="home__bars">
                {tickets.map((t) => {
                  const status = ticketDisplayStatus(graph!, t.id);
                  const tag = (t.data?.tag as string) ?? t.label.slice(0, 4).toUpperCase();
                  return (
                    <div key={t.id} className="home__bar-seg">
                      <span className={`home__bar-fill is-${status}`} />
                      <span className="home__bar-label kindtag">{tag}</span>
                    </div>
                  );
                })}
              </div>
            </button>
          )}
          {objective && (
            <div className="home__repo">
              <span className="home__repo-label">대상 레포</span>
              {editingRepo ? (
                <>
                  <input
                    className="home__repo-input mono"
                    aria-label="대상 레포 경로"
                    placeholder="비우면 워크스페이스 기본값"
                    value={repoInput}
                    onChange={(e) => setRepoInput(e.target.value)}
                  />
                  <button className="btn btn--primary btn--sm" onClick={saveRepo}>
                    저장
                  </button>
                  <button className="btn btn--ghost btn--sm" onClick={() => setEditingRepo(false)}>
                    취소
                  </button>
                </>
              ) : (
                <>
                  <span className="home__repo-path mono">{info?.repoDir ?? '…'}</span>
                  {info && (
                    <span className={`home__repo-src home__repo-src--${info.repoSource}`}>
                      {info.repoSource === 'override' ? 'custom' : 'auto'}
                    </span>
                  )}
                  <button
                    className="btn btn--ghost btn--sm"
                    onClick={() => {
                      setRepoInput(info?.repoSource === 'override' ? info.repoDir : '');
                      setEditingRepo(true);
                    }}
                  >
                    편집
                  </button>
                </>
              )}
            </div>
          )}
        </section>
      </main>

      {planning && (
        <Modal onClose={() => setPlanning(false)}>
          <PlanApproval
            goal={trimmed}
            onCancel={() => setPlanning(false)}
            onApproved={() => {
              setPlanning(false);
              onOpenProject();
            }}
          />
        </Modal>
      )}
    </div>
  );
}
