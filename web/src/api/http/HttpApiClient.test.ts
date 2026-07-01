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

test('getGraph sends If-None-Match and reuses the cached graph on 304', async () => {
  const g = { nodes: [{ id: 's4', kind: 'step', label: 'gate', status: 'awaiting_review' }], edges: [] };
  let call = 0;
  const fetchMock = vi.fn(async (_url: string, _opts?: RequestInit) => {
    call++;
    return call === 1
      ? new Response(JSON.stringify(g), { headers: { ETag: 'W/"abc"' } })
      : new Response(null, { status: 304 });
  });
  vi.stubGlobal('fetch', fetchMock);
  const api = new HttpApiClient('http://api', 'p1');
  const first = await api.getGraph();
  expect(first.nodes[0].id).toBe('s4');
  const second = await api.getGraph(); // 304 -> reuse cache
  expect(second).toEqual(first);
  expect(fetchMock.mock.calls[1][1]).toMatchObject({ headers: { 'If-None-Match': 'W/"abc"' } });
});

test('setPid clears the cached graph etag (no cross-project 304 reuse)', async () => {
  const fetchMock = vi.fn(async (_url: string, _opts?: RequestInit) =>
    new Response(JSON.stringify({ nodes: [], edges: [] }), { headers: { ETag: 'W/"x"' } }),
  );
  vi.stubGlobal('fetch', fetchMock);
  const api = new HttpApiClient('http://api', 'p1');
  await api.getGraph();
  api.setPid('p2');
  await api.getGraph();
  // after setPid the second request must NOT carry the p1 etag
  expect(fetchMock.mock.calls[1][1]).toMatchObject({ headers: {} });
});

test('governance: global rules use /rules (PUT), project rules use /projects/{pid}/rules', async () => {
  const fetchMock = vi.fn(async (url: string) =>
    url.endsWith('/projects/p1/rules')
      ? new Response(
          JSON.stringify({
            project: { coding: '', planning: '' },
            global: { coding: '', planning: '' },
            resolved: { coding: '', planning: '' },
          }),
        )
      : new Response(JSON.stringify({ coding: 'C', planning: '' })),
  );
  vi.stubGlobal('fetch', fetchMock);
  const api = new HttpApiClient('http://api', 'p1');
  await api.setGlobalRules({ coding: 'C' });
  expect(fetchMock).toHaveBeenCalledWith(
    'http://api/rules',
    expect.objectContaining({ method: 'PUT', body: JSON.stringify({ coding: 'C' }) }),
  );
  await api.getProjectRules();
  expect(fetchMock).toHaveBeenCalledWith('http://api/projects/p1/rules');
});

test('governance: setProjectModels PUTs {models} to /projects/{pid}/models', async () => {
  const fetchMock = vi.fn(
    async () =>
      new Response(JSON.stringify({ points: [], transports: [], project: {}, global: {}, resolved: {} })),
  );
  vi.stubGlobal('fetch', fetchMock);
  const api = new HttpApiClient('http://api', 'p1');
  await api.setProjectModels({ executor: { transport: 'simulated', model: '' } });
  expect(fetchMock).toHaveBeenCalledWith(
    'http://api/projects/p1/models',
    expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify({ models: { executor: { transport: 'simulated', model: '' } } }),
    }),
  );
});

test('governance: getModelAvailability GETs /models/available', async () => {
  const fetchMock = vi.fn(
    async () =>
      new Response(JSON.stringify([{ transport: 'simulated', wired: true, available: true, detail: 'x' }])),
  );
  vi.stubGlobal('fetch', fetchMock);
  const api = new HttpApiClient('http://api', 'p1');
  const a = await api.getModelAvailability();
  expect(fetchMock).toHaveBeenCalledWith('http://api/models/available');
  expect(a[0].transport).toBe('simulated');
});

test('steer: POSTs the instruction + scope to /projects/{pid}/steer', async () => {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify({ op: 'redirect', scope: {}, result: {} })));
  vi.stubGlobal('fetch', fetchMock);
  const api = new HttpApiClient('http://api', 'p1');
  const r = await api.steer('use Stripe', { ticketId: 't1' });
  expect(fetchMock).toHaveBeenCalledWith(
    'http://api/projects/p1/steer',
    expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ text: 'use Stripe', ticketId: 't1', stepId: undefined }),
    }),
  );
  expect(r.op).toBe('redirect');
});

test('channel: getMessages GETs /projects/{pid}/messages (+ since cursor)', async () => {
  const fetchMock = vi.fn(
    async () =>
      new Response(JSON.stringify([{ id: 1, type: 'review', author: 'agent', text: 'x', refs: ['s1'], ts: 't' }])),
  );
  vi.stubGlobal('fetch', fetchMock);
  const api = new HttpApiClient('http://api', 'p1');
  await api.getMessages();
  expect(fetchMock).toHaveBeenCalledWith('http://api/projects/p1/messages');
  await api.getMessages(5);
  expect(fetchMock).toHaveBeenCalledWith('http://api/projects/p1/messages?since=5');
});

test('autonomy: get GETs and set PUTs /projects/{pid}/autonomy', async () => {
  const fetchMock = vi.fn(
    async () =>
      new Response(
        JSON.stringify({ levels: ['auto', 'co-pilot', 'per-step'], project: 'auto', global: 'per-step', resolved: 'auto' }),
      ),
  );
  vi.stubGlobal('fetch', fetchMock);
  const api = new HttpApiClient('http://api', 'p1');
  await api.getProjectAutonomy();
  expect(fetchMock).toHaveBeenCalledWith('http://api/projects/p1/autonomy');
  await api.setProjectAutonomy('auto');
  expect(fetchMock).toHaveBeenCalledWith(
    'http://api/projects/p1/autonomy',
    expect.objectContaining({ method: 'PUT', body: JSON.stringify({ level: 'auto' }) }),
  );
});
