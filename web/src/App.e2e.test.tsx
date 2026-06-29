import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useStore } from './store/useStore';
import App from './App';

beforeEach(() => {
  useStore.setState({ mode: 'navigator', selectedTicketId: null, selectedStepId: null, reviewOpen: false });
});

test('approving the awaiting step updates state live (no refresh control used)', async () => {
  render(<App />);
  // open the ticket -> kanban board; the awaiting-review step shows "리뷰 시작"
  await userEvent.click(await screen.findByText('구독 티어 + 기능 게이팅'));
  await waitFor(() => expect(screen.getAllByText('awaiting review').length).toBeGreaterThan(0));
  // "리뷰 시작" drills into the cockpit, then approve from the review pane
  await userEvent.click(await screen.findByRole('button', { name: /리뷰 시작/ }));
  await userEvent.click(await screen.findByRole('button', { name: '승인' }));
  // the board/cockpit reflect "done" live, with no manual refresh control
  await waitFor(() => expect(screen.queryByText('awaiting review')).toBeNull());
  expect(screen.queryByRole('button', { name: /refresh/i })).toBeNull();
  expect(screen.queryByText(/refresh/i)).toBeNull();
});
