import type { ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import './governance.css';

/** Shared chrome for the project-scoped governance pages (Rules / Models): a top bar with
 *  the project breadcrumb and a tab switch between the two axes. */
export function GovernanceLayout({
  pid,
  active,
  lead,
  children,
}: {
  pid: string;
  active: 'rules' | 'models';
  lead: string;
  children: ReactNode;
}) {
  const navigate = useNavigate();
  return (
    <div className="gov">
      <header className="gov__bar">
        <button className="gov__brand" onClick={() => navigate('/')} aria-label="프로젝트 목록">
          <span className="gov__logo" aria-hidden="true">
            CT
          </span>
        </button>
        <span className="gov__sep" aria-hidden="true">
          /
        </span>
        <button className="gov__project" onClick={() => navigate(`/project/${pid}`)}>
          {pid}
        </button>
        <nav className="gov__tabs" aria-label="governance">
          <button
            className="gov__tab"
            aria-current={active === 'rules'}
            onClick={() => navigate(`/project/${pid}/rules`)}
          >
            Rules
          </button>
          <button
            className="gov__tab"
            aria-current={active === 'models'}
            onClick={() => navigate(`/project/${pid}/models`)}
          >
            Models
          </button>
        </nav>
      </header>
      <main className="gov__main">
        <p className="gov__lead">{lead}</p>
        {children}
      </main>
    </div>
  );
}
