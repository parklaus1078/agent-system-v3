import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ProjectsHome } from './ProjectsHome';
import { useStore } from '../../store/useStore';

test('lists projects and routes to one on click', async () => {
  render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="/" element={<ProjectsHome />} />
        <Route path="/project/:pid" element={<div>PROJECT MAP</div>} />
      </Routes>
    </MemoryRouter>,
  );
  expect(screen.getByText('진행 중인 프로젝트')).toBeInTheDocument();
  // listProjects (mock) returns the fixture project
  await waitFor(() => expect(screen.getByText('구독 티어 할일앱')).toBeInTheDocument());
  await userEvent.click(screen.getByText('구독 티어 할일앱'));
  expect(await screen.findByText('PROJECT MAP')).toBeInTheDocument();
});

test('분해 시작 initializes a PROJECT (slug + tickets) and routes to its map', async () => {
  render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="/" element={<ProjectsHome />} />
        <Route path="/project/:pid" element={<div>PROJECT MAP</div>} />
      </Routes>
    </MemoryRouter>,
  );
  await userEvent.type(screen.getByLabelText('새 목표'), 'budgeting app');
  await userEvent.click(screen.getByRole('button', { name: /분해 시작/ }));
  // project planner proposes an editable slug + tickets (not steps)
  expect(await screen.findByLabelText('프로젝트 slug')).toHaveValue('budgeting-app');
  expect(screen.getByLabelText('티켓 1')).toBeInTheDocument();
  // approve -> created -> offered the map
  await userEvent.click(screen.getByRole('button', { name: '프로젝트 생성' }));
  await userEvent.click(await screen.findByRole('button', { name: /지도로 이동/ }));
  expect(await screen.findByText('PROJECT MAP')).toBeInTheDocument();
});

test('deletes a project after confirmation, passing the directory option', async () => {
  const api = useStore.getState().api;
  // mock the call so the shared fixture isn't actually mutated for other tests
  const spy = vi
    .spyOn(api, 'deleteProject')
    .mockResolvedValue({ projectId: 'p1', nodes: 0, edges: 0, messages: 0, directoryRemoved: true });
  render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="/" element={<ProjectsHome />} />
      </Routes>
    </MemoryRouter>,
  );
  await screen.findByText('구독 티어 할일앱');

  await userEvent.click(screen.getByRole('button', { name: '구독 티어 할일앱 삭제' })); // the ✕ on the card
  await screen.findByText('프로젝트 삭제'); // confirm dialog
  await userEvent.click(screen.getByRole('checkbox')); // also delete the directory
  await userEvent.click(screen.getByRole('button', { name: '삭제 (디렉터리 포함)' }));

  await waitFor(() => expect(spy).toHaveBeenCalledWith('p1', true));
  spy.mockRestore();
});
