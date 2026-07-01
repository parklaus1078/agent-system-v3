import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AutonomyDial } from './AutonomyDial';
import { useStore } from '../store/useStore';

test('shows the three throttle levels and saves the chosen one to the project', async () => {
  const api = useStore.getState().api;
  const spy = vi.spyOn(api, 'setProjectAutonomy');
  render(<AutonomyDial />);

  expect(screen.getByRole('button', { name: '매 step' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '부조종' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '자동' })).toBeInTheDocument();

  await userEvent.click(screen.getByRole('button', { name: '자동' }));
  await waitFor(() => expect(spy).toHaveBeenCalledWith('auto'));
  // the store reflects the new effective throttle (mock echoes resolved='auto')
  await waitFor(() => expect(useStore.getState().autonomy).toBe('auto'));
  expect(screen.getByRole('button', { name: '자동' })).toHaveAttribute('aria-pressed', 'true');
});
