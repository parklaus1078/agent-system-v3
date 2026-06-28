import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useStore } from './store/useStore';
import App from './App';

beforeEach(() => {
  useStore.setState({ selectedTicketId: null, selectedStepId: null, reviewOpen: false });
});

test('approving the awaiting step updates state live (no refresh control used)', async () => {
  render(<App />);
  // open the ticket -> cockpit; the awaiting-review step's review is auto-shown
  await userEvent.click(await screen.findByText('구독 티어 + 기능 게이팅'));
  // the lane shows the awaiting-review step before approval
  await waitFor(() => expect(screen.getAllByText('awaiting review').length).toBeGreaterThan(0));
  // approve it from the review pane
  await userEvent.click(await screen.findByRole('button', { name: '승인' }));
  // the map/lane reflect "done" live, with no manual refresh control
  await waitFor(() => expect(screen.queryByText('awaiting review')).toBeNull());
  expect(screen.queryByRole('button', { name: /refresh/i })).toBeNull();
  expect(screen.queryByText(/refresh/i)).toBeNull();
});
