import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { PlanApproval } from './PlanApproval';

test('shows proposed steps and approves', async () => {
  const onApproved = vi.fn();
  render(<PlanApproval goal="구독 결제 붙이기" onApproved={onApproved} />);
  await waitFor(() => expect(screen.getByDisplayValue('스펙·골격')).toBeInTheDocument());
  await userEvent.click(screen.getByRole('button', { name: /승인/ }));
  await waitFor(() => expect(onApproved).toHaveBeenCalled());
});
