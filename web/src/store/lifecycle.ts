import type { Status } from '../domain/graph';

const ORDER: Status[] = ['planning', 'executing', 'awaiting_review', 'done'];

/** Pure step-state transition. `done`/`blocked` are terminal and stay put. */
export function nextStatus(s: Status): Status {
  if (s === 'done' || s === 'blocked') return s;
  const i = ORDER.indexOf(s);
  return i < 0 || i === ORDER.length - 1 ? s : ORDER[i + 1];
}
