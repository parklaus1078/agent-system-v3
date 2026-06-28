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
