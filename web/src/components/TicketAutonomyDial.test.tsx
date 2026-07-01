import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TicketAutonomyDial } from './TicketAutonomyDial';
import { useStore } from '../store/useStore';

test('shows the effective ticket throttle and sets a ticket override', async () => {
  const api = useStore.getState().api;
  const spy = vi.spyOn(api, 'setTicketAutonomy');
  render(<TicketAutonomyDial ticketId="t-gate" />);

  // default: inherited, resolved = per-step (global)
  await waitFor(() =>
    expect(screen.getByRole('button', { name: '매 step' })).toHaveAttribute('aria-pressed', 'true'),
  );

  await userEvent.click(screen.getByRole('button', { name: '자동' }));
  await waitFor(() => expect(spy).toHaveBeenCalledWith('t-gate', 'auto'));
  // the ticket override now makes 자동 the effective level
  await waitFor(() =>
    expect(screen.getByRole('button', { name: '자동' })).toHaveAttribute('aria-pressed', 'true'),
  );
});

test('refetches the resolved level when the project autonomy changes underneath it (CP4)', async () => {
  const api = useStore.getState().api;
  act(() => useStore.setState({ autonomy: 'per-step' })); // known baseline so the flip below is a real change
  const spy = vi.spyOn(api, 'getTicketAutonomy');
  render(<TicketAutonomyDial ticketId="t-gate" />);
  await waitFor(() => expect(spy).toHaveBeenCalled()); // initial fetch
  const before = spy.mock.calls.length;

  // a steer `control` op / the top dial flips the project level -> store.autonomy changes
  act(() => useStore.setState({ autonomy: 'auto' }));
  // an inherited ticket must re-resolve rather than show a stale value
  await waitFor(() => expect(spy.mock.calls.length).toBeGreaterThan(before));
});
