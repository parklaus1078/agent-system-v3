import { useEffect, useRef, useState } from 'react';
import { useStore } from '../store/useStore';
import { ProjectMap } from './map/ProjectMap';
import { Cockpit } from './cockpit/Cockpit';
import { SearchIcon, GridIcon } from './icons';
import './Shell.css';

/** Elapsed session clock shown as HH:MM:SS in the top bar (the "live" feel). */
function useElapsedClock(): string {
  const [secs, setSecs] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setSecs((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, []);
  const hh = String(Math.floor(secs / 3600)).padStart(2, '0');
  const mm = String(Math.floor((secs % 3600) / 60)).padStart(2, '0');
  const ss = String(secs % 60).padStart(2, '0');
  return `${hh}:${mm}:${ss}`;
}

export function Shell() {
  const load = useStore((s) => s.load);
  const graph = useStore((s) => s.graph);
  const selectedTicketId = useStore((s) => s.selectedTicketId);
  const selectTicket = useStore((s) => s.selectTicket);
  const clock = useElapsedClock();
  const loaded = useRef(false);

  useEffect(() => {
    if (!loaded.current) {
      loaded.current = true;
      void load();
    }
  }, [load]);

  const objective = graph?.nodes.find((n) => n.kind === 'objective');
  const projectName = (objective?.data?.short as string | undefined) ?? objective?.label ?? '';
  const altitude: 'map' | 'lane' = selectedTicketId ? 'lane' : 'map';

  const goNavigator = () => selectTicket(null);
  const goCockpit = () => {
    if (selectedTicketId) return;
    // Cockpit needs a ticket in focus: prefer the one awaiting your review.
    const tickets = graph?.nodes.filter((n) => n.kind === 'ticket') ?? [];
    const focus = tickets.find((t) => t.status === 'awaiting_review' || t.status === 'executing') ?? tickets[0];
    if (focus) selectTicket(focus.id);
  };

  return (
    <div className="shell">
      <h1 className="sr-only">LLM Dev Control Tower</h1>
      <header className="topbar">
        <div className="topbar__brand">
          <span className="topbar__logo" aria-hidden="true">
            CT
          </span>
          <span className="topbar__title">Control Tower</span>
          {projectName && (
            <>
              <span className="topbar__sep" aria-hidden="true" />
              <button className="topbar__project" onClick={goNavigator}>
                {projectName}
              </button>
            </>
          )}
        </div>

        <div className="topbar__center">
          <div className="trace">
            <span className="trace__icon">
              <SearchIcon size={15} />
            </span>
            <input
              className="trace__input mono"
              type="search"
              aria-label="추적"
              placeholder="추적: 파일 · 심볼 · UI 요소"
            />
          </div>
        </div>

        <div className="topbar__right">
          <span className="live">
            <span className="live__dot" aria-hidden="true" />
            <span className="mono">live</span>
            <span className="live__clock mono">{clock}</span>
          </span>
          <div className="segmented" role="group" aria-label="altitude">
            <button
              className="segmented__btn"
              aria-pressed={altitude === 'map'}
              onClick={goNavigator}
            >
              Navigator
            </button>
            <button
              className="segmented__btn"
              aria-pressed={altitude === 'lane'}
              onClick={goCockpit}
            >
              Cockpit
            </button>
          </div>
          <button className="iconbtn">
            <GridIcon size={15} />
            Legend
          </button>
        </div>
      </header>

      <main className="shell__main">{altitude === 'map' ? <ProjectMap /> : <Cockpit />}</main>
    </div>
  );
}
