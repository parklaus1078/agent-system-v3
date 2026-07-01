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

test('setChannelFilter forces the channel open so its filter + clear button are reachable (CP4)', () => {
  useStore.setState({ channelOpen: false, channelFilter: null });
  useStore.getState().setChannelFilter('t-gate'); // a map node click
  expect(useStore.getState().channelFilter).toBe('t-gate');
  expect(useStore.getState().channelOpen).toBe(true); // opened so the ✕ clear is mounted (no stuck filter)

  // clearing the filter must NOT touch the channel's open/closed state
  useStore.setState({ channelOpen: false });
  useStore.getState().setChannelFilter(null);
  expect(useStore.getState().channelFilter).toBeNull();
  expect(useStore.getState().channelOpen).toBe(false);
});
