import { HttpApiClient } from './HttpApiClient';

const graph = {
  nodes: [{ id: 's4', kind: 'step', label: 'gate', status: 'awaiting_review' }],
  edges: [],
};

test('getGraph maps the REST response', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify(graph))),
  );
  const api = new HttpApiClient('http://api', 'p1');
  const g = await api.getGraph();
  expect(g.nodes[0].status).toBe('awaiting_review');
});

test('owningPath unwraps the {path} envelope', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify({ path: ['cr:x', 's1', 't1', 'obj'] }))),
  );
  const api = new HttpApiClient('http://api', 'p1');
  expect(await api.owningPath('cr:x')).toEqual(['cr:x', 's1', 't1', 'obj']);
});

test('proposePlan(goal) mints a ticket and POSTs to the lifecycle plan endpoint', async () => {
  const fetchMock = vi.fn(
    async () =>
      new Response(
        JSON.stringify({
          ticketId: 't-x',
          next: ['approve'],
          done: false,
          current: 0,
          steps: [],
          awaiting: { type: 'plan_approval', steps: [{ label: 'a', intent: 'i', acceptance: 'x' }] },
        }),
      ),
  );
  vi.stubGlobal('fetch', fetchMock);
  const api = new HttpApiClient('http://api', 'p1');
  const p = await api.proposePlan({ goal: '구독 결제' });
  expect(fetchMock).toHaveBeenCalledWith(
    expect.stringMatching(/^http:\/\/api\/projects\/p1\/tickets\/t-.+\/plan$/),
    expect.objectContaining({ method: 'POST', body: JSON.stringify({ title: '구독 결제' }) }),
  );
  expect(p.ticketId).toMatch(/^t-/); // minted id is threaded back to approve
  expect(p.steps).toEqual([{ label: 'a', intent: 'i', acceptance: 'x' }]);
});

test('approvePlan POSTs the edited steps to the ticket approve endpoint', async () => {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ticketId: 't-x', next: ['review'] })));
  vi.stubGlobal('fetch', fetchMock);
  const api = new HttpApiClient('http://api', 'p1');
  await api.approvePlan({ ticketId: 't-x', steps: [{ label: 'a', intent: '', acceptance: '' }] });
  expect(fetchMock).toHaveBeenCalledWith(
    'http://api/projects/p1/tickets/t-x/plan/approve',
    expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ steps: [{ label: 'a', intent: '', acceptance: '' }] }),
    }),
  );
});

test('reviewStep POSTs the action and notifies subscribers', async () => {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ok: true, status: 'done' })));
  vi.stubGlobal('fetch', fetchMock);
  const api = new HttpApiClient('http://api', 'p1');
  let pinged = 0;
  const unsub = api.subscribe(() => {
    pinged++;
  });
  await api.reviewStep('s4', { kind: 'approve' });
  unsub();
  expect(fetchMock).toHaveBeenCalledWith(
    'http://api/projects/p1/steps/s4/review',
    expect.objectContaining({ method: 'POST', body: JSON.stringify({ kind: 'approve' }) }),
  );
  expect(pinged).toBeGreaterThan(0);
});

test('saveLayout POSTs positions to the per-project layout endpoint and notifies', async () => {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify({ updated: 1 })));
  vi.stubGlobal('fetch', fetchMock);
  const api = new HttpApiClient('http://api', 'p1');
  let pinged = 0;
  const unsub = api.subscribe(() => {
    pinged++;
  });
  await api.saveLayout({ t1: { x: 5, y: 6 } });
  unsub();
  expect(fetchMock).toHaveBeenCalledWith(
    'http://api/projects/p1/layout',
    expect.objectContaining({ method: 'POST', body: JSON.stringify({ positions: { t1: { x: 5, y: 6 } } }) }),
  );
  expect(pinged).toBeGreaterThan(0);
});

test('proposeProject / approveProject hit the top-level (not pid-scoped) project endpoints', async () => {
  const fetchMock = vi.fn(async (url: string) =>
    url.endsWith('/projects/plan')
      ? new Response(JSON.stringify({ slug: 's', title: 't', tickets: [{ title: 'T' }] }))
      : new Response(JSON.stringify({ projectId: 's', title: 't', tickets: 1, created: true })),
  );
  vi.stubGlobal('fetch', fetchMock);
  const api = new HttpApiClient('http://api', 'p1');
  const prop = await api.proposeProject('build a thing');
  expect(fetchMock).toHaveBeenCalledWith(
    'http://api/projects/plan',
    expect.objectContaining({ method: 'POST', body: JSON.stringify({ goal: 'build a thing' }) }),
  );
  const created = await api.approveProject(prop);
  expect(fetchMock).toHaveBeenCalledWith('http://api/projects/approve', expect.objectContaining({ method: 'POST' }));
  expect(created.created).toBe(true);
});
