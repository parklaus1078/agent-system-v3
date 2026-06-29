import { render, screen, waitFor } from '@testing-library/react';
import { useStore } from '../../store/useStore';
import { ReviewSummary } from './ReviewSummary';

beforeEach(async () => {
  useStore.setState({ selectedTicketId: null, selectedStepId: null, reviewOpen: false });
  await useStore.getState().load();
});

test('awaiting_review step shows the approve gate', async () => {
  useStore.getState().selectStep('s4');
  render(<ReviewSummary />);
  await waitFor(() => expect(screen.getByRole('button', { name: '승인' })).toBeInTheDocument());
  expect(screen.getByRole('button', { name: /전체 리뷰/ })).toBeInTheDocument();
});

test('done step shows "승인 완료 · commit 채택됨"', async () => {
  useStore.getState().selectStep('s1');
  render(<ReviewSummary />);
  await waitFor(() => expect(screen.getByText(/승인 완료/)).toBeInTheDocument());
  expect(screen.getByText(/commit 채택됨/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: '승인' })).toBeNull();
});

test('planning step shows the waiting note', async () => {
  useStore.getState().selectStep('s5');
  render(<ReviewSummary />);
  await waitFor(() => expect(screen.getByText(/대기 중/)).toBeInTheDocument());
  expect(screen.getByText(/이전 step이 승인되면 실행을 시작합니다/)).toBeInTheDocument();
});

test('blocked step shows the failed note + trace shortcut', async () => {
  useStore.getState().selectStep('sy2');
  render(<ReviewSummary />);
  await waitFor(() => expect(screen.getByText(/디버그가 필요합니다/)).toBeInTheDocument());
  expect(screen.getByRole('button', { name: /전체 리뷰에서 추적/ })).toBeInTheDocument();
});
