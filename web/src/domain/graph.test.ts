import { neighbors, type ProjectGraph } from './graph';

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
