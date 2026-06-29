import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useStore } from '../../store/useStore';
import { TicketBoard } from './TicketBoard';

beforeEach(async () => {
  useStore.setState({ mode: 'navigator', selectedTicketId: null, selectedStepId: null });
  await useStore.getState().load();
});

test('lays out the ticket steps as status columns (planned / awaiting review / done)', async () => {
  useStore.getState().selectTicket('t-gate');
  render(<TicketBoard />);
  await waitFor(() => expect(screen.getByTestId('ticket-board')).toBeInTheDocument());
  // four columns
  ['PLANNED', 'EXECUTING', 'AWAITING REVIEW', 'DONE'].forEach((c) =>
    expect(screen.getByText(c)).toBeInTheDocument(),
  );
  // t-gate fixtures: 티어 플래그 정의 (done), 게이트 컴포넌트 (awaiting_review), 업그레이드 안내 UI (planning)
  const done = screen.getByText('티어 플래그 정의').closest('[data-col]');
  const review = screen.getByText('게이트 컴포넌트').closest('[data-col]');
  const planned = screen.getByText('업그레이드 안내 UI').closest('[data-col]');
  expect(done).toHaveAttribute('data-col', 'done');
  expect(review).toHaveAttribute('data-col', 'review');
  expect(planned).toHaveAttribute('data-col', 'planned');
});

test('“리뷰 시작” on the awaiting-review card enters the cockpit for that step', async () => {
  useStore.getState().selectTicket('t-gate');
  render(<TicketBoard />);
  await userEvent.click(await screen.findByRole('button', { name: /리뷰 시작/ }));
  expect(useStore.getState().mode).toBe('cockpit');
  expect(useStore.getState().selectedStepId).toBe('s4'); // the awaiting_review step
});

test('back-to-map button clears the ticket selection', async () => {
  useStore.getState().selectTicket('t-gate');
  render(<TicketBoard />);
  await userEvent.click(await screen.findByRole('button', { name: /지도/ }));
  expect(useStore.getState().selectedTicketId).toBeNull();
});

test('a blocked step sits in the AWAITING REVIEW column with a “디버그 추적” action', async () => {
  // t-sync fixtures: 동기화 큐 (done), 충돌 해결 (blocked), 재시도 로직 (planning)
  useStore.getState().selectTicket('t-sync');
  render(<TicketBoard />);
  const blocked = (await screen.findByText('충돌 해결')).closest('[data-col]');
  expect(blocked).toHaveAttribute('data-col', 'review'); // needs-attention column, not executing
  // its CTA is a debug trace (not "리뷰 시작"), and it drills into the cockpit
  await userEvent.click(screen.getByRole('button', { name: /디버그 추적/ }));
  expect(useStore.getState().mode).toBe('cockpit');
  expect(useStore.getState().selectedStepId).toBe('sy2');
});
