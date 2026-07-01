import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { RulesPage } from './RulesPage';
import { useStore } from '../../store/useStore';

function renderRules() {
  return render(
    <MemoryRouter initialEntries={['/project/p1/rules']}>
      <Routes>
        <Route path="/project/:pid/rules" element={<RulesPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

test('loads the seeded global coding rule and saves an edit via setGlobalRules', async () => {
  const api = useStore.getState().api;
  const spy = vi.spyOn(api, 'setGlobalRules');
  renderRules();

  const globalCoding = (await screen.findByLabelText(
    '전역 기본 규칙 coding rules',
  )) as HTMLTextAreaElement;
  expect(globalCoding.value).toContain('DRY'); // seeded default loaded

  await userEvent.clear(globalCoding);
  await userEvent.type(globalCoding, 'NEW-RULE');
  await userEvent.click(screen.getAllByRole('button', { name: '저장' })[0]); // global card

  await waitFor(() => expect(spy).toHaveBeenCalled());
  expect(spy.mock.calls[0][0]).toMatchObject({ coding: 'NEW-RULE' });
});

test('saves a project override via setProjectRules and shows it in resolved', async () => {
  const api = useStore.getState().api;
  const spy = vi.spyOn(api, 'setProjectRules');
  renderRules();

  const projCoding = (await screen.findByLabelText(
    '프로젝트 규칙 (오버라이드) coding rules',
  )) as HTMLTextAreaElement;
  await userEvent.type(projCoding, 'PROJ-ONLY');
  await userEvent.click(screen.getAllByRole('button', { name: '저장' })[1]); // project card

  await waitFor(() => expect(spy).toHaveBeenCalled());
  const resolved = (await screen.findByLabelText('resolved coding rules')) as HTMLTextAreaElement;
  expect(resolved.value).toContain('PROJ-ONLY');
});
