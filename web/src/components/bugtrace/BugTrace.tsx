import { useState } from 'react';
import { useStore } from '../../store/useStore';
import { SearchIcon } from '../icons';
import './BugTrace.css';

/** Top-bar trace box: search a file/symbol, then highlight its owning path
 *  (CodeRegion -> Step -> Ticket -> Objective) on the map. */
export function BugTrace({ onHighlight }: { onHighlight: (ids: string[]) => void }) {
  const graph = useStore((s) => s.graph);
  const api = useStore((s) => s.api);
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);

  const query = q.trim().toLowerCase();
  const matches =
    graph && query
      ? graph.nodes
          .filter(
            (n) =>
              (n.kind === 'code_region' || n.kind === 'test') &&
              n.label.toLowerCase().includes(query),
          )
          .slice(0, 8)
      : [];

  async function pick(id: string, label: string) {
    const path = await api.owningPath(id);
    onHighlight(path);
    setQ(label);
    setOpen(false);
  }

  return (
    <div className="trace">
      <span className="trace__icon">
        <SearchIcon size={15} />
      </span>
      <input
        className="trace__input mono"
        type="search"
        aria-label="추적"
        placeholder="추적: 파일 · 심볼 · UI 요소"
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
          if (e.target.value.trim() === '') onHighlight([]);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {open && matches.length > 0 && (
        <ul className="trace__menu">
          {matches.map((m) => (
            <li key={m.id}>
              <button
                className="trace__item"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => pick(m.id, m.label)}
              >
                <span className="mono trace__item-label">{m.label}</span>
                <span className="trace__item-kind">{m.kind === 'test' ? 'test' : 'code'}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
