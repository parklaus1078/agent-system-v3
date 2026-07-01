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

test('setProjectMeta updates the objective title + description', async () => {
  const api = new MockApiClient();
  const out = await api.setProjectMeta({ title: '새 제목', description: '새 설명' });
  expect(out.title).toBe('새 제목');
  expect(out.description).toBe('새 설명');
  const g = await api.getGraph();
  const obj = g.nodes.find((n) => n.kind === 'objective')!;
  expect(obj.label).toBe('새 제목');
  expect(obj.data?.description).toBe('새 설명');
  // blank description clears it
  const cleared = await api.setProjectMeta({ description: '   ' });
  expect(cleared.description).toBeNull();
});

test('deleteProject drops a project from the listing; directoryRemoved reflects the flag', async () => {
  const api = new MockApiClient();
  expect((await api.listProjects()).some((p) => p.projectId === 'p1')).toBe(true);
  const out = await api.deleteProject('p1', false);
  expect(out.projectId).toBe('p1');
  expect(out.directoryRemoved).toBe(false); // not requested
  expect((await api.listProjects()).some((p) => p.projectId === 'p1')).toBe(false); // gone

  await api.approveProject({ slug: 'todel', title: 'X', tickets: [{ title: 'a', intent: '' }] });
  const out2 = await api.deleteProject('todel', true);
  expect(out2.directoryRemoved).toBe(true); // requested
  expect((await api.listProjects()).some((p) => p.projectId === 'todel')).toBe(false);
});

test('governance rules: global default + project override merge in resolved', async () => {
  const api = new MockApiClient();
  await api.setGlobalRules({ coding: 'G-CODE', planning: 'G-PLAN' });
  await api.setProjectRules({ coding: 'P-CODE' });
  const v = await api.getProjectRules();
  expect(v.global.coding).toBe('G-CODE');
  expect(v.project.coding).toBe('P-CODE');
  expect(v.resolved.coding).toContain('G-CODE');
  expect(v.resolved.coding).toContain('P-CODE'); // appended
  expect(v.resolved.planning).toBe('G-PLAN'); // no project planning override -> global only
});

test('governance models: project override wins over global; resolved reflects it', async () => {
  const api = new MockApiClient();
  await api.setGlobalModels({ executor: { transport: 'codex-cli', model: 'm1' } });
  expect((await api.getProjectModels()).resolved.executor.transport).toBe('codex-cli');
  await api.setProjectModels({ executor: { transport: 'simulated', model: '' } });
  const pm = await api.getProjectModels();
  expect(pm.resolved.executor.transport).toBe('simulated');
  expect(pm.points).toContain('executor');
});

test('governance models: unknown transport is dropped (input validation)', async () => {
  const api = new MockApiClient();
  const g = await api.setGlobalModels({ executor: { transport: 'bogus', model: 'm' } });
  expect(g.global.executor).toBeUndefined();
});

test('governance models: a transport unsupported for a point resolves to simulated (mirrors backend)', async () => {
  const api = new MockApiClient();
  // anthropic-api has no executor backend -> resolved executor falls back to simulated
  await api.setGlobalModels({ executor: { transport: 'anthropic-api', model: 'm' } });
  expect((await api.getProjectModels()).resolved.executor.transport).toBe('simulated');
  // and an invalid project override falls THROUGH to a valid global engine
  await api.setGlobalModels({ executor: { transport: 'codex-cli', model: 'gm' } });
  await api.setProjectModels({ executor: { transport: 'openai-api', model: 'x' } });
  expect((await api.getProjectModels()).resolved.executor).toEqual({ transport: 'codex-cli', model: 'gm' });
});

test('model availability reports wired engines + adapter stubs', async () => {
  const api = new MockApiClient();
  const a = await api.getModelAvailability();
  expect(a.find((e) => e.transport === 'simulated')?.available).toBe(true);
  expect(a.find((e) => e.transport === 'local')?.wired).toBe(true); // now wired (OpenAI-compatible)
});

test('autonomy: default per-step; project override resolves; clear inherits global', async () => {
  const api = new MockApiClient();
  expect((await api.getProjectAutonomy()).resolved).toBe('per-step'); // default
  let v = await api.setProjectAutonomy('auto');
  expect(v.project).toBe('auto');
  expect(v.resolved).toBe('auto');
  v = await api.setProjectAutonomy(null); // clear the override
  expect(v.project).toBeNull();
  expect(v.resolved).toBe('per-step'); // inherits the global default
});

test('steer: constrain records a user instruction + a decision message with a node ref', async () => {
  const api = new MockApiClient();
  const r = await api.steer("don't touch auth");
  expect(r.op).toBe('constrain');
  const msgs = await api.getMessages();
  expect(msgs.some((m) => m.type === 'steer' && m.author === 'user')).toBe(true);
  expect(msgs.some((m) => m.type === 'decision' && m.text.includes('auth'))).toBe(true);
});

test('steer: pause -> control (autonomy per-step); use X -> redirect', async () => {
  const api = new MockApiClient();
  expect((await api.steer('pause')).op).toBe('control');
  expect((await api.getProjectAutonomy()).project).toBe('per-step');
  expect((await api.steer('use Paddle')).op).toBe('redirect');
});

test('steer control: 매 스텝 maps to per-step (not auto) — mock mirrors the backend', async () => {
  const api = new MockApiClient();
  await api.steer('매 스텝으로 바꿔');
  expect((await api.getProjectAutonomy()).project).toBe('per-step');
});

test('steer: a question -> ask -> the agent posts a project answer (conversation)', async () => {
  const api = new MockApiClient();
  const r = await api.steer('이 프로젝트 상태 어때?');
  expect(r.op).toBe('ask');
  const msgs = await api.getMessages();
  expect(msgs.some((m) => m.author === 'agent' && m.text.includes('티켓'))).toBe(true); // answered, not clarified
});

test('steer: 먼저 -> reprioritize; 추가 -> scope creates a new ticket (CP4)', async () => {
  const api = new MockApiClient();
  expect((await api.steer('결제 먼저')).op).toBe('reprioritize');
  const before = (await api.getGraph()).nodes.filter((n) => n.kind === 'ticket').length;
  expect((await api.steer('다국어도 추가')).op).toBe('scope');
  const after = (await api.getGraph()).nodes.filter((n) => n.kind === 'ticket').length;
  expect(after).toBe(before + 1);
});

test('per-ticket autonomy: ticket override resolves over project/global (CP4)', async () => {
  const api = new MockApiClient();
  expect((await api.getTicketAutonomy('t-gate')).resolved).toBe('per-step'); // inherited default
  await api.setProjectAutonomy('co-pilot');
  expect((await api.getTicketAutonomy('t-gate')).resolved).toBe('co-pilot'); // inherits project
  const v = await api.setTicketAutonomy('t-gate', 'auto');
  expect(v.ticket).toBe('auto'); // ticket override
  expect(v.resolved).toBe('auto'); // ...wins over the project's co-pilot
});

test('channel: a gated step posts a review message; since cursor returns only newer', async () => {
  vi.useFakeTimers();
  try {
    const api = new MockApiClient();
    expect(await api.getMessages()).toEqual([]);
    await api.reviewStep('s4', { kind: 'approve' }); // advances -> s5 executing
    await vi.runAllTimersAsync(); // gateLater fires -> s5 gates + posts a review message
    const msgs = await api.getMessages();
    const review = msgs.filter((m) => m.type === 'review');
    expect(review.length).toBeGreaterThan(0);
    expect(review[review.length - 1].refs).toContain('s5');
    expect(await api.getMessages(msgs[msgs.length - 1].id)).toEqual([]); // nothing newer
  } finally {
    vi.useRealTimers();
  }
});
