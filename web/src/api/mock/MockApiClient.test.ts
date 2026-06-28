import { MockApiClient } from './MockApiClient';

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
