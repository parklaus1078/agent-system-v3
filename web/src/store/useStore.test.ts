import { useStore } from './useStore';

beforeEach(async () => {
  useStore.setState({ mode: 'navigator', selectedTicketId: null, selectedStepId: null });
  await useStore.getState().load();
});

test('opening a ticket focuses the step that needs you — awaiting review first', () => {
  useStore.getState().selectTicket('t-gate'); // s4 게이트 컴포넌트 is awaiting_review
  expect(useStore.getState().selectedStepId).toBe('s4');
});

test('opening a blocked ticket focuses the blocked step (so you can debug it)', () => {
  useStore.getState().selectTicket('t-sync'); // sy2 충돌 해결 is blocked, sy1 is done
  expect(useStore.getState().selectedStepId).toBe('sy2');
});
