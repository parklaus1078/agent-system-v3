import { useState } from 'react';
import type { DiffBlob } from '../../api/dto';
import { CodeIcon } from '../icons';

function basename(path: string): string {
  return path.split('/').pop() ?? path;
}

interface Row {
  line: string;
  num: number;
  cls: 'add' | 'del' | 'ctx';
}

function toRows(patch: string): Row[] {
  return patch
    .replace(/\n$/, '')
    .split('\n')
    .filter((l) => !l.startsWith('+++') && !l.startsWith('---') && !l.startsWith('@@'))
    .map((line, i) => ({
      line,
      num: i + 1,
      cls: line.startsWith('+') ? 'add' : line.startsWith('-') ? 'del' : 'ctx',
    }));
}

export function DiffView({ diff }: { diff: DiffBlob[] }) {
  const [active, setActive] = useState(0);
  if (diff.length === 0) return <div className="diff-empty">변경된 파일이 없습니다.</div>;
  const blob = diff[Math.min(active, diff.length - 1)];
  const rows = toRows(blob.patch);

  return (
    <div className="diff">
      <div className="diff__tabs" role="tablist">
        {diff.map((b, i) => (
          <button
            key={b.path}
            role="tab"
            aria-selected={i === active}
            className={`diff__tab${i === active ? ' is-active' : ''}`}
            onClick={() => setActive(i)}
          >
            <span className="mono">{basename(b.path)}</span>
            {i === 0 && <span className="diff__newtag">NEW</span>}
          </button>
        ))}
      </div>
      <div className="diff__pathbar mono">
        <CodeIcon size={13} />
        {blob.path}
        <span className="diff__pathnote">· 새 파일</span>
      </div>
      <div className="diff__code">
        {rows.map((r, i) => (
          <div key={i} className={`diff-line diff-line--${r.cls}`}>
            <span className="diff-line__num" aria-hidden="true">
              {r.num}
            </span>
            <code className="diff-line__text">{r.line || ' '}</code>
          </div>
        ))}
      </div>
    </div>
  );
}
