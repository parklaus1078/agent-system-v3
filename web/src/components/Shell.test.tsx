import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Shell } from './Shell';
import { useStore } from '../store/useStore';

// useStore is a module singleton; reset to the map (navigator, no ticket) each test.
beforeEach(() => {
  useStore.setState({ mode: 'navigator', selectedTicketId: null, selectedStepId: null });
});

test('shows objective and opens the ticket board when a ticket is clicked', async () => {
  render(<Shell />);
  await waitFor(() => expect(screen.getByText('구독 티어 할일앱')).toBeInTheDocument());
  // map shows tickets; clicking one drills into its kanban board (Navigator zoom-in)
  await userEvent.click(await screen.findByText('구독 티어 + 기능 게이팅'));
  expect(await screen.findByTestId('ticket-board')).toBeInTheDocument();
  expect(screen.getByText('AWAITING REVIEW')).toBeInTheDocument();
});

test('does NOT render internal plumbing controls', async () => {
  render(<Shell />);
  await waitFor(() => expect(screen.getByText('구독 티어 할일앱')).toBeInTheDocument());
  expect(screen.queryByText(/worker tick/i)).toBeNull();
  expect(screen.queryByText(/watcher tick/i)).toBeNull();
  expect(screen.queryByText(/refresh/i)).toBeNull();
});
