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
  // steps hidden by default too
  expect(screen.queryByText('게이트 컴포넌트')).toBeNull();
  await userEvent.click(screen.getByRole('button', { name: /code/i }));
  expect(await screen.findByText('src/billing/FeatureGate.tsx')).toBeInTheDocument();
});

test('a highlighted step auto-reveals the Step layer so the trace target is visible (CP4 channel->map)', async () => {
  // s4 '게이트 컴포넌트' is a step; the Step layer is off by default, so without the auto-reveal
  // a channel step-ref chip (focusNode(stepId)) would land on a fully-dimmed map with no target.
  render(<ProjectMap highlightIds={['s4']} />);
  expect(await screen.findByText('게이트 컴포넌트')).toBeInTheDocument();
});
