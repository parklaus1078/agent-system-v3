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

test('approvePlan starts a planning ticket executing and runs step 1 (executing -> awaiting_review)', async () => {
  vi.useFakeTimers();
  try {
    const api = new MockApiClient();
    // t-pay is planning (sp1, sp2). Approve an edited plan.
    await api.approvePlan({
      ticketId: 't-pay',
      title: '페이월 & 업셀',
      steps: [
        { label: '페이월 화면', intent: '', acceptance: '' },
        { label: '업셀 카피', intent: '', acceptance: '' },
      ],
    });
    let g = await api.getGraph();
    expect(g.nodes.find((n) => n.id === 't-pay')?.status).toBe('executing');
    const steps = neighbors(g, 't-pay', 'out').filter((n) => n.kind === 'step');
    expect(steps.map((s) => s.label)).toEqual(['페이월 화면', '업셀 카피']); // edited plan applied
    expect(steps[0].status).toBe('executing'); // step 1 running
    await vi.runAllTimersAsync();
    g = await api.getGraph();
    const s1 = neighbors(g, 't-pay', 'out').filter((n) => n.kind === 'step')[0];
    expect(s1.status).toBe('awaiting_review'); // gated for review
  } finally {
    vi.useRealTimers();
  }
});

test('approvePlan for a new goal creates the ticket under the objective', async () => {
  const api = new MockApiClient();
  await api.approvePlan({
    ticketId: 't-new',
    title: '새 목표',
    steps: [{ label: 'a', intent: '', acceptance: '' }],
  });
  const g = await api.getGraph();
  const t = g.nodes.find((n) => n.id === 't-new');
  expect(t?.kind).toBe('ticket');
  expect(t?.status).toBe('executing');
  const obj = g.nodes.find((n) => n.kind === 'objective')!;
  expect(g.edges.some((e) => e.from === obj.id && e.to === 't-new')).toBe(true);
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

test('saveLayout persists node positions onto data.pos and notifies', async () => {
  const api = new MockApiClient();
  let pinged = 0;
  api.subscribe(() => {
    pinged++;
  });
  await api.saveLayout({ obj: { x: 12, y: 34 } });
  const g = await api.getGraph();
  expect(g.nodes.find((n) => n.id === 'obj')?.data?.pos).toEqual({ x: 12, y: 34 });
  expect(pinged).toBeGreaterThan(0);
});
