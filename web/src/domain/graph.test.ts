import { neighbors, nextTicketId, orderedTickets, ticketOrder, type ProjectGraph } from './graph';

const g: ProjectGraph = {
  nodes: [
    { id: 'o1', kind: 'objective', label: 'Todo' },
    { id: 't1', kind: 'ticket', label: 'CRUD', status: 'executing' },
    { id: 's1', kind: 'step', label: 'add form', status: 'awaiting_review' },
    { id: 'c1', kind: 'code_region', label: 'TodoForm.tsx' },
  ],
  edges: [
    { id: 'e1', from: 'o1', to: 't1', kind: 'has' },
    { id: 'e2', from: 't1', to: 's1', kind: 'has' },
    { id: 'e3', from: 's1', to: 'c1', kind: 'touches' },
  ],
};

test('neighbors out returns direct children', () => {
  expect(neighbors(g, 't1', 'out').map((n) => n.id)).toEqual(['s1']);
});
test('neighbors in returns parents', () => {
  expect(neighbors(g, 's1', 'in').map((n) => n.id)).toEqual(['t1']);
});
test('neighbors both is union', () => {
  expect(neighbors(g, 's1', 'both').map((n) => n.id).sort()).toEqual(['c1', 't1']);
});

test('ticketOrder: explicit data.order wins, else the {slug}-{n} id index (legacy -t{n} too), else 0', () => {
  expect(ticketOrder({ id: 'proj-5', kind: 'ticket', label: 'x' })).toBe(5); // new {slug}-{n}
  expect(ticketOrder({ id: 'p-t3', kind: 'ticket', label: 'x' })).toBe(3); // legacy -t{n} still read
  expect(ticketOrder({ id: 'proj-5', kind: 'ticket', label: 'x', data: { order: -1 } })).toBe(-1); // explicit wins
  expect(ticketOrder({ id: 'no-suffix', kind: 'ticket', label: 'x' })).toBe(0);
});

test('nextTicketId: {pid}-{highest number + 1}, counting legacy -t{n}, 1 when none', () => {
  const gg: ProjectGraph = {
    nodes: [
      { id: 'proj-1', kind: 'ticket', label: 'A' },
      { id: 'proj-3', kind: 'ticket', label: 'C' }, // a gap — must not reuse 2
      { id: 'obj', kind: 'objective', label: 'O' },
    ],
    edges: [],
  };
  expect(nextTicketId(gg, 'proj')).toBe('proj-4'); // max(1,3)+1
  expect(nextTicketId({ nodes: [], edges: [] }, 'fresh')).toBe('fresh-1'); // no tickets -> 1
  expect(nextTicketId({ nodes: [{ id: 'p-t2', kind: 'ticket', label: 'x' }], edges: [] }, 'p')).toBe('p-3');
});

test('orderedTickets sorts by backlog order so a reprioritized ticket moves to the front (CP4)', () => {
  const gg: ProjectGraph = {
    nodes: [
      { id: 'p-t1', kind: 'ticket', label: 'A' },
      { id: 'p-t2', kind: 'ticket', label: 'B', data: { order: -1 } }, // reprioritized to the front
      { id: 'p-t3', kind: 'ticket', label: 'C' },
      { id: 'obj', kind: 'objective', label: 'O' },
    ],
    edges: [],
  };
  expect(orderedTickets(gg).map((t) => t.id)).toEqual(['p-t2', 'p-t1', 'p-t3']);
});
