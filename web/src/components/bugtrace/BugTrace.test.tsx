import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useStore } from '../../store/useStore';
import { BugTrace } from './BugTrace';

beforeEach(async () => {
  useStore.setState({ selectedTicketId: null, selectedStepId: null });
  await useStore.getState().load();
});

test('selecting a file highlights its owning path', async () => {
  const onHighlight = vi.fn();
  render(<BugTrace onHighlight={onHighlight} />);
  await userEvent.type(screen.getByRole('searchbox'), 'FeatureGate');
  await userEvent.click(await screen.findByText('src/billing/FeatureGate.tsx'));
  await waitFor(() => expect(onHighlight).toHaveBeenCalledWith(['c-gate', 's4', 't-gate', 'obj']));
});
