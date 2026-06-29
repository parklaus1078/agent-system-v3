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

// git/unidiff file headers that aren't +/-/@@ — drop them so they don't render as context
const GIT_HEADER =
  /^(diff --git |index |new file mode |deleted file mode |old mode |new mode |similarity index |dissimilarity index |rename (from|to) |copy (from|to) |Binary files )/;

function toRows(patch: string): Row[] {
  return patch
    .replace(/\n$/, '')
    .split('\n')
    .filter(
      (l) =>
        !l.startsWith('+++') && !l.startsWith('---') && !l.startsWith('@@') && !GIT_HEADER.test(l),
    )
    .map((line, i) => ({
      line,
      num: i + 1,
      cls: line.startsWith('+') ? 'add' : line.startsWith('-') ? 'del' : 'ctx',
    }));
}

/** A file reads as "new" only when its patch actually says so (or is pure additions) —
 *  not unconditionally for the first tab. Empty patches (seed/no-diff) are neither. */
function isNewFile(patch: string): boolean {
  if (patch.includes('new file')) return true;
  const body = patch
    .split('\n')
    .filter((l) => !l.startsWith('+++') && !l.startsWith('---') && !l.startsWith('@@'));
  const changed = body.filter((l) => l.startsWith('+') || l.startsWith('-'));
  return changed.length > 0 && changed.every((l) => l.startsWith('+'));
}

export function DiffView({ diff }: { diff: DiffBlob[] }) {
  const [active, setActive] = useState(0);
  if (diff.length === 0) return <div className="diff-empty">변경된 파일이 없습니다.</div>;
  const blob = diff[Math.min(active, diff.length - 1)];
  const rows = toRows(blob.patch);
  const blobIsNew = isNewFile(blob.patch);
  const hasPatch = blob.patch.trim().length > 0;

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
            {isNewFile(b.patch) && <span className="diff__newtag">NEW</span>}
          </button>
        ))}
      </div>
      <div className="diff__pathbar mono">
        <CodeIcon size={13} />
        {blob.path}
        {blobIsNew ? (
          <span className="diff__pathnote">· 새 파일</span>
        ) : (
          !hasPatch && <span className="diff__pathnote">· diff 없음</span>
        )}
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
