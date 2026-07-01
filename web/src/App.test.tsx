import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { useStore } from './store/useStore';
import App from './App';

beforeEach(() => {
  useStore.setState({ selectedTicketId: null, selectedStepId: null, reviewOpen: false });
});

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );

test('landing (/) renders the projects home', async () => {
  renderAt('/');
  expect(await screen.findByText('진행 중인 프로젝트')).toBeInTheDocument();
});

test('the Control Tower brand returns from a project to the home', async () => {
  renderAt('/project/p1');
  await waitFor(() => expect(screen.getByText('Control Tower')).toBeInTheDocument());
  await userEvent.click(screen.getByText('Control Tower'));
  expect(await screen.findByText('진행 중인 프로젝트')).toBeInTheDocument();
});
