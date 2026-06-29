import { render, screen, waitFor } from '@testing-library/react';
import { useStore } from '../../store/useStore';
import { TicketLane } from './TicketLane';

beforeEach(async () => {
  useStore.setState({ selectedTicketId: null, selectedStepId: null });
  await useStore.getState().load();
});

test('emphasizes the awaiting_review step', async () => {
  useStore.getState().selectTicket('t-gate');
  render(<TicketLane />);
  await waitFor(() => expect(screen.getByText('게이트 컴포넌트')).toBeInTheDocument());
  const card = screen.getByText('게이트 컴포넌트').closest('[data-emphasis]');
  expect(card).toHaveAttribute('data-emphasis', 'true');
});
