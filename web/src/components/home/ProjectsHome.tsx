import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useStore } from '../../store/useStore';
import type { ProjectSummary } from '../../api/dto';
import { Modal } from '../Modal';
import { ProjectInit } from './ProjectInit';
import { ArrowRightIcon, XIcon } from '../icons';
import './ProjectsHome.css';

/** Landing / project-management home ("/"). Lists every project and starts a new goal.
 *  Clicking a project routes to its map at /project/{projectId}. */
export function ProjectsHome() {
  const navigate = useNavigate();
  const api = useStore((s) => s.api);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [goal, setGoal] = useState('');
  const [planning, setPlanning] = useState(false);
  const [deleting, setDeleting] = useState<ProjectSummary | null>(null); // project pending deletion
  const [alsoDir, setAlsoDir] = useState(false); // also delete the actual project directory
  const [busy, setBusy] = useState(false);
  const [delErr, setDelErr] = useState<string | null>(null);
  const trimmed = goal.trim();

  const refresh = () => void api.listProjects().then(setProjects, () => {});
  useEffect(refresh, [api]);

  const confirmDelete = async () => {
    if (!deleting) return;
    setBusy(true);
    setDelErr(null);
    try {
      await api.deleteProject(deleting.projectId, alsoDir);
      setDeleting(null);
      refresh();
    } catch (e) {
      setDelErr(e instanceof Error ? e.message : '삭제에 실패했습니다.');
    } finally {
      setBusy(false);
    }
  };

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
              <span className="home__goalhint">PLAN 에이전트가 프로젝트를 티켓으로 분해 → 승인 후 생성</span>
              <button
                className="btn btn--primary"
                disabled={!trimmed}
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
          {projects.length === 0 ? (
            <p className="home__empty mono">아직 프로젝트가 없습니다. 위에서 새 목표로 시작하세요.</p>
          ) : (
            <div className="home__projects">
              {projects.map((p) => (
                <div key={p.projectId} className="home__project-wrap">
                  <button
                    className="home__project"
                    onClick={() => navigate(`/project/${p.projectId}`)}
                  >
                    <div className="home__project-head">
                      <span className="home__project-name">{p.title}</span>
                      <span className="home__project-meta mono">
                        {p.tickets} tickets · {p.steps} steps
                      </span>
                      {p.awaiting > 0 && (
                        <span className="home__project-await">
                          <span className="home__await-dot" />
                          {p.awaiting}건 리뷰 대기
                        </span>
                      )}
                    </div>
                    {p.description && <p className="home__project-desc">{p.description}</p>}
                  </button>
                  <button
                    className="home__project-del"
                    aria-label={`${p.title} 삭제`}
                    title="프로젝트 삭제"
                    onClick={() => {
                      setDeleting(p);
                      setAlsoDir(false);
                      setDelErr(null);
                    }}
                  >
                    <XIcon size={14} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>
      </main>

      {planning && (
        <Modal onClose={() => setPlanning(false)} dismissable={false}>
          <ProjectInit
            goal={trimmed}
            onCancel={() => setPlanning(false)}
            onCreated={refresh}
            onStay={() => {
              setPlanning(false);
              setGoal('');
              refresh();
            }}
            onGoToMap={(slug) => {
              setPlanning(false);
              navigate(`/project/${slug}`); // open the newly created project's map
            }}
          />
        </Modal>
      )}

      {deleting && (
        <Modal onClose={() => !busy && setDeleting(null)} dismissable={!busy}>
          <div className="home__confirm">
            <h3 className="home__confirm-title">프로젝트 삭제</h3>
            <p className="home__confirm-body">
              <b>{deleting.title}</b> 프로젝트를 삭제합니다. 매핑 데이터(그래프·티켓·계획·대화 채널)가 모두 삭제되며 되돌릴 수 없습니다.
            </p>
            <label className="home__confirm-check">
              <input
                type="checkbox"
                checked={alsoDir}
                onChange={(e) => setAlsoDir(e.target.checked)}
                disabled={busy}
              />
              <span>
                실제 프로젝트 디렉터리(파일)도 삭제 <span className="mono">— 워크스페이스의 실제 코드가 사라집니다</span>
              </span>
            </label>
            {delErr && (
              <p className="home__confirm-err" role="alert">
                {delErr}
              </p>
            )}
            <div className="home__confirm-actions">
              <button className="btn" onClick={() => setDeleting(null)} disabled={busy}>
                취소
              </button>
              <button className="btn btn--danger" onClick={() => void confirmDelete()} disabled={busy}>
                {busy ? '삭제 중…' : alsoDir ? '삭제 (디렉터리 포함)' : '삭제'}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
