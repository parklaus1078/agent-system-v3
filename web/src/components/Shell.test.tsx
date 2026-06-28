import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Shell } from './Shell';
import { useStore } from '../store/useStore';

// useStore is a module singleton; clear selection so each test starts at the map altitude.
beforeEach(() => {
  useStore.setState({ selectedTicketId: null, selectedStepId: null });
});

test('shows objective and switches to lane when a ticket is opened', async () => {
  render(<Shell />);
  await waitFor(() => expect(screen.getByText('구독 티어 할일앱')).toBeInTheDocument());
  // map shows tickets; opening one switches altitude to the lane
  await userEvent.click(await screen.findByText('구독 티어 + 기능 게이팅'));
  expect(await screen.findByTestId('ticket-lane')).toBeInTheDocument();
});

test('does NOT render internal plumbing controls', async () => {
  render(<Shell />);
  await waitFor(() => expect(screen.getByText('구독 티어 할일앱')).toBeInTheDocument());
  expect(screen.queryByText(/worker tick/i)).toBeNull();
  expect(screen.queryByText(/watcher tick/i)).toBeNull();
  expect(screen.queryByText(/refresh/i)).toBeNull();
});
