import { render, screen } from '@testing-library/react';
import { ActivityBadge } from './ActivityBadge';

test('shows a live badge with detail while executing', () => {
  const { container } = render(
    <ActivityBadge activity={{ state: 'executing', detail: 'step 2/5', since: new Date().toISOString() }} />,
  );
  expect(screen.getByText(/step 2\/5/)).toBeInTheDocument();
  expect(container.querySelector('.activity__spin')).toBeInTheDocument();
});

test('shows "계획 수립 중" while planning', () => {
  render(<ActivityBadge activity={{ state: 'planning', since: new Date().toISOString() }} />);
  expect(screen.getByText(/계획 수립 중/)).toBeInTheDocument();
});

test('renders nothing for gate states (covered by status pills)', () => {
  const { container } = render(<ActivityBadge activity={{ state: 'awaiting_review' }} />);
  expect(container).toBeEmptyDOMElement();
});

test('renders nothing when there is no activity', () => {
  const { container } = render(<ActivityBadge activity={undefined} />);
  expect(container).toBeEmptyDOMElement();
});
