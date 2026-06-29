import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useStore } from '../../store/useStore';
import { ProjectsHome } from './ProjectsHome';

beforeEach(() => {
  useStore.setState({ selectedTicketId: null, selectedStepId: null, reviewOpen: false });
});

test('lists the in-progress project and opens it', async () => {
  const onOpen = vi.fn();
  render(<ProjectsHome onOpenProject={onOpen} />);
  await waitFor(() => expect(screen.getByText('구독 티어 할일앱')).toBeInTheDocument());
  expect(screen.getByText('진행 중인 프로젝트')).toBeInTheDocument();
  await userEvent.click(screen.getByText('구독 티어 할일앱'));
  expect(onOpen).toHaveBeenCalled();
});
