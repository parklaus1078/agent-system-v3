import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ProjectMetaEditor } from './ProjectMetaEditor';
import { useStore } from '../../store/useStore';

test('shows current title/description and saves edits via setProjectMeta', async () => {
  const api = useStore.getState().api;
  const spy = vi.spyOn(api, 'setProjectMeta');
  const onClose = vi.fn();
  render(
    <ProjectMetaEditor initialTitle="구독 티어 할일앱" initialDescription="원래 설명 본문" onClose={onClose} />,
  );
  expect(screen.getByLabelText('프로젝트 제목')).toHaveValue('구독 티어 할일앱');
  expect(screen.getByLabelText('프로젝트 설명')).toHaveValue('원래 설명 본문');

  await userEvent.clear(screen.getByLabelText('프로젝트 설명'));
  await userEvent.type(screen.getByLabelText('프로젝트 설명'), '고친 설명');
  await userEvent.click(screen.getByRole('button', { name: '저장' }));

  expect(spy).toHaveBeenCalledWith({ title: '구독 티어 할일앱', description: '고친 설명' });
  expect(onClose).toHaveBeenCalled();
});
