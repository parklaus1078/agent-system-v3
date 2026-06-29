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

test('segmented toggle tracks the rendered view; the project name returns to the map as Navigator', async () => {
  render(<Shell />);
  await waitFor(() => expect(screen.getByText('구독 티어 할일앱')).toBeInTheDocument());
  const nav = () => screen.getByRole('button', { name: 'Navigator' });
  const cock = () => screen.getByRole('button', { name: 'Cockpit' });

  expect(nav()).toHaveAttribute('aria-pressed', 'true'); // map = Navigator
  await userEvent.click(await screen.findByText('구독 티어 + 기능 게이팅'));
  await screen.findByTestId('ticket-board');
  expect(nav()).toHaveAttribute('aria-pressed', 'true'); // board is still Navigator
  expect(cock()).toHaveAttribute('aria-pressed', 'false');

  await userEvent.click(cock());
  expect(cock()).toHaveAttribute('aria-pressed', 'true'); // cockpit

  // the reported bug: project name -> map, but the toggle stayed on Cockpit
  await userEvent.click(screen.getByRole('button', { name: '구독 할일앱' }));
  expect(nav()).toHaveAttribute('aria-pressed', 'true');
  expect(cock()).toHaveAttribute('aria-pressed', 'false');
});

test('Legend button toggles the legend panel', async () => {
  render(<Shell />);
  await waitFor(() => expect(screen.getByText('구독 티어 할일앱')).toBeInTheDocument());
  expect(screen.queryByText('NODE KIND — shape')).toBeNull();
  await userEvent.click(screen.getByRole('button', { name: /Legend/ }));
  expect(screen.getByText('NODE KIND — shape')).toBeInTheDocument();
  expect(screen.getByText('STATUS — color')).toBeInTheDocument();
});

test('does NOT render internal plumbing controls', async () => {
  render(<Shell />);
  await waitFor(() => expect(screen.getByText('구독 티어 할일앱')).toBeInTheDocument());
  expect(screen.queryByText(/worker tick/i)).toBeNull();
  expect(screen.queryByText(/watcher tick/i)).toBeNull();
  expect(screen.queryByText(/refresh/i)).toBeNull();
});
