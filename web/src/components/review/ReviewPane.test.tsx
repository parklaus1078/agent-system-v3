import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useStore } from '../../store/useStore';
import { ReviewPane } from './ReviewPane';

beforeEach(async () => {
  useStore.setState({ selectedTicketId: null, selectedStepId: null, reviewOpen: false });
  await useStore.getState().load();
});

test('renders diff + 3 actions and approves a step', async () => {
  useStore.getState().selectStep('s4');
  render(<ReviewPane />);
  // the diff shows the touched file (in the tab and the path bar)
  await waitFor(() => expect(screen.getAllByText(/FeatureGate\.tsx/).length).toBeGreaterThan(0));
  expect(screen.getByRole('button', { name: '승인' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '수정요청' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '내가 인수' })).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: '승인' }));
  await waitFor(async () => {
    const g = await useStore.getState().api.getGraph();
    expect(g.nodes.find((n) => n.id === 's4')?.status).toBe('done');
  });
});
