import { MockApiClient } from './MockApiClient';
import { neighbors } from '../../domain/graph';

test('getGraph returns the fixture with an awaiting_review step', async () => {
  const api = new MockApiClient();
  const g = await api.getGraph();
  expect(g.nodes.find((n) => n.id === 's4')?.status).toBe('awaiting_review');
});

test('owningPath walks CodeRegion -> Step -> Ticket -> Objective', async () => {
  const api = new MockApiClient();
  const path = await api.owningPath('c-gate');
  expect(path).toEqual(['c-gate', 's4', 't-gate', 'obj']);
});

test('reviewStep approve advances the step to done and notifies subscribers', async () => {
  const api = new MockApiClient();
  let pinged = 0;
  api.subscribe(() => {
    pinged++;
  });
  await api.reviewStep('s4', { kind: 'approve' });
  const g = await api.getGraph();
  expect(g.nodes.find((n) => n.id === 's4')?.status).toBe('done');
  expect(pinged).toBeGreaterThan(0);
});

test('reviewStep approve starts the next step: executing, then gates for review', async () => {
  vi.useFakeTimers();
  try {
    const api = new MockApiClient();
    await api.reviewStep('s4', { kind: 'approve' });
    let g = await api.getGraph();
    expect(g.nodes.find((n) => n.id === 's4')?.status).toBe('done');
    expect(g.nodes.find((n) => n.id === 's5')?.status).toBe('executing'); // in progress now
    await vi.runAllTimersAsync();
    g = await api.getGraph();
    expect(g.nodes.find((n) => n.id === 's5')?.status).toBe('awaiting_review'); // ready to review
    expect(neighbors(g, 's5', 'out').some((n) => n.kind === 'code_region')).toBe(true);
  } finally {
    vi.useRealTimers();
  }
});

test('reviewStep approve on the ticket’s last step completes the ticket', async () => {
  vi.useFakeTimers();
  try {
    const api = new MockApiClient();
    await api.reviewStep('s4', { kind: 'approve' });
    await vi.runAllTimersAsync(); // s5 -> awaiting_review
    await api.reviewStep('s5', { kind: 'approve' });
    const g = await api.getGraph();
    expect(g.nodes.find((n) => n.id === 's5')?.status).toBe('done');
    expect(g.nodes.find((n) => n.id === 't-gate')?.status).toBe('done');
  } finally {
    vi.useRealTimers();
  }
});
