import { nextStatus } from './lifecycle';

test('lifecycle advances planning -> executing -> awaiting_review -> done', () => {
  expect(nextStatus('planning')).toBe('executing');
  expect(nextStatus('executing')).toBe('awaiting_review');
  expect(nextStatus('awaiting_review')).toBe('done');
});
test('terminal statuses are stable', () => {
  expect(nextStatus('done')).toBe('done');
  expect(nextStatus('blocked')).toBe('blocked');
});
