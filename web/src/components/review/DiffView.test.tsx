import { render, screen } from '@testing-library/react';
import { DiffView } from './DiffView';

test('strips the +/- (and context space) prefix but keeps the add/del color class', () => {
  const patch = '@@ -1,2 +1,2 @@\n context line\n-old value\n+const x = 1\n';
  const { container } = render(<DiffView diff={[{ path: 'src/x.ts', patch }]} />);

  // displayed text has NO leading marker
  const added = screen.getByText('const x = 1');
  expect(added.textContent).toBe('const x = 1');
  expect(added.closest('.diff-line')).toHaveClass('diff-line--add');

  const removed = screen.getByText('old value');
  expect(removed.closest('.diff-line')).toHaveClass('diff-line--del');

  // context line keeps alignment (leading space dropped) and stays uncolored
  const ctx = screen.getByText('context line');
  expect(ctx.closest('.diff-line')).toHaveClass('diff-line--ctx');

  // no row text still carries a + or - sign
  container.querySelectorAll('.diff-line__text').forEach((el) => {
    expect(el.textContent?.startsWith('+')).toBe(false);
    expect(el.textContent?.startsWith('-')).toBe(false);
  });
});
