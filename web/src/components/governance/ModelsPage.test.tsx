import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ModelsPage } from './ModelsPage';
import { useStore } from '../../store/useStore';

function renderModels() {
  return render(
    <MemoryRouter initialEntries={['/project/p1/models']}>
      <Routes>
        <Route path="/project/:pid/models" element={<ModelsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

test('renders the point×engine table and saves a project executor override', async () => {
  const api = useStore.getState().api;
  const spy = vi.spyOn(api, 'setProjectModels');
  renderModels();

  await screen.findByText('executor'); // routing table loaded
  await userEvent.click(screen.getByRole('button', { name: '프로젝트' })); // scope -> project override
  await userEvent.selectOptions(screen.getByLabelText('executor transport'), 'simulated');
  await userEvent.click(screen.getByRole('button', { name: '저장' }));

  await waitFor(() => expect(spy).toHaveBeenCalled());
  expect(spy.mock.calls[0][0]).toMatchObject({ executor: { transport: 'simulated', model: '' } });
});

test('health chips surface transport availability (status only)', async () => {
  renderModels();
  // simulated is always available; its chip title carries the human-readable status
  expect(await screen.findByTitle(/deterministic offline stub/)).toBeInTheDocument();
});

test('the help (?) icon reveals official model-name docs for claude + codex CLIs', async () => {
  renderModels();
  await screen.findByText('executor'); // page loaded
  expect(screen.queryByRole('dialog', { name: '모델명 공식 문서' })).toBeNull(); // closed by default
  await userEvent.click(screen.getByRole('button', { name: '사용 가능한 모델명 공식 문서' }));
  const claude = await screen.findByRole('link', { name: /Claude 모델명/ });
  expect(claude).toHaveAttribute('href', expect.stringContaining('docs.anthropic.com'));
  expect(screen.getByRole('link', { name: /OpenAI 모델명/ })).toHaveAttribute(
    'href',
    expect.stringContaining('platform.openai.com'),
  );
});
