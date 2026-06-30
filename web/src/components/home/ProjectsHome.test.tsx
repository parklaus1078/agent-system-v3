import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ProjectsHome } from './ProjectsHome';

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
