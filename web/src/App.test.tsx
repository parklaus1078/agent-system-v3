import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useStore } from './store/useStore';
import App from './App';

beforeEach(() => {
  useStore.setState({ selectedTicketId: null, selectedStepId: null, reviewOpen: false });
});

test('renders the product name', () => {
  render(<App />);
  expect(screen.getByText('LLM Dev Control Tower')).toBeInTheDocument();
});

test('the Control Tower brand opens the project-management home', async () => {
  render(<App />);
  await waitFor(() => expect(screen.getByText('Control Tower')).toBeInTheDocument());
  await userEvent.click(screen.getByText('Control Tower'));
  expect(await screen.findByText('진행 중인 프로젝트')).toBeInTheDocument();
});
