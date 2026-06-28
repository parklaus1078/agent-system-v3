import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useStore } from '../../store/useStore';
import { ProjectMap } from './ProjectMap';

beforeEach(async () => {
  useStore.setState({ selectedTicketId: null, selectedStepId: null });
  await useStore.getState().load();
});

test('renders a node per graph node and toggles the code layer', async () => {
  render(<ProjectMap />);
  await waitFor(() => expect(screen.getByText('구독 티어 + 기능 게이팅')).toBeInTheDocument());
  // code regions hidden by default
  expect(screen.queryByText('src/billing/FeatureGate.tsx')).toBeNull();
  await userEvent.click(screen.getByRole('button', { name: /code/i }));
  expect(await screen.findByText('src/billing/FeatureGate.tsx')).toBeInTheDocument();
});
