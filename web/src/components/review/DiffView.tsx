import { useState } from 'react';
import type { DiffBlob } from '../../api/dto';
import { CodeIcon } from '../icons';

function basename(path: string): string {
  return path.split('/').pop() ?? path;
}

function lineClass(line: string): string {
  if (line.startsWith('+++') || line.startsWith('---')) return 'diff-line diff-line--meta';
  if (line.startsWith('@@')) return 'diff-line diff-line--hunk';
  if (line.startsWith('+')) return 'diff-line diff-line--add';
  if (line.startsWith('-')) return 'diff-line diff-line--del';
  return 'diff-line';
}

export function DiffView({ diff }: { diff: DiffBlob[] }) {
  const [active, setActive] = useState(0);
  if (diff.length === 0) return <div className="diff-empty">변경된 파일이 없습니다.</div>;
  const blob = diff[Math.min(active, diff.length - 1)];
  const lines = blob.patch.replace(/\n$/, '').split('\n');

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
      <pre className="diff__code">
        {lines.map((line, i) => (
          <code key={i} className={lineClass(line)}>
            {line || ' '}
          </code>
        ))}
      </pre>
    </div>
  );
}
