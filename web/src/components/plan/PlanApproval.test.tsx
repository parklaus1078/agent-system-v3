import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useStore } from '../../store/useStore';
import { PlanApproval } from './PlanApproval';

beforeEach(async () => {
  await useStore.getState().load();
});

test('goal mode: shows proposed steps and approves', async () => {
  const onApproved = vi.fn();
  render(<PlanApproval goal="구독 결제 붙이기" onApproved={onApproved} />);
  await waitFor(() => expect(screen.getByDisplayValue('스펙·골격')).toBeInTheDocument());
  await userEvent.click(screen.getByRole('button', { name: /승인/ }));
  await waitFor(() => expect(onApproved).toHaveBeenCalled());
});

test('ticket mode: loads a planning ticket steps, edits, and approves', async () => {
  const onApproved = vi.fn();
  render(<PlanApproval ticketId="t-pay" onApproved={onApproved} />);
  // the planning ticket's existing steps are loaded as editable inputs
  await waitFor(() => expect(screen.getByDisplayValue('페이월 화면 골격')).toBeInTheDocument());
  expect(screen.getByDisplayValue('업셀 카피')).toBeInTheDocument();
  // add a step
  await userEvent.click(screen.getByRole('button', { name: /step 추가/ }));
  expect(screen.getByDisplayValue('새 step')).toBeInTheDocument();
  // approve
  await userEvent.click(screen.getByRole('button', { name: /승인/ }));
  await waitFor(() => expect(onApproved).toHaveBeenCalled());
});
