import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChannelPanel } from './ChannelPanel';
import { useStore } from '../../store/useStore';
import type { ProjectGraph } from '../../domain/graph';

// the store is a shared singleton across tests in this file — reset CP4 view state each test
beforeEach(() => useStore.setState({ channelFilter: null, highlightIds: null }));

test('renders typed messages; a review message carries the review actions', async () => {
  const api = useStore.getState().api;
  const spy = vi.spyOn(api, 'reviewStep');
  const graph: ProjectGraph = {
    nodes: [{ id: 's4', kind: 'step', label: '구현', status: 'awaiting_review' }],
    edges: [],
  };
  useStore.setState({
    graph,
    messages: [
      { id: 1, type: 'decision', author: 'agent', text: '결정: Stripe', refs: ['dec:s1'], ts: 't' },
      { id: 2, type: 'review', author: 'agent', text: "'구현' 리뷰 대기", refs: ['s4'], ts: 't' },
    ],
  });

  render(<ChannelPanel />);
  expect(screen.getByText('결정: Stripe')).toBeInTheDocument();
  expect(screen.getByText("'구현' 리뷰 대기")).toBeInTheDocument();

  // the review message's 승인 action reuses reviewStep(refs[0], approve)
  await userEvent.click(screen.getByRole('button', { name: '승인' }));
  await waitFor(() => expect(spy).toHaveBeenCalledWith('s4', { kind: 'approve' }));
});

test('the steer input sends the instruction and surfaces the resulting messages', async () => {
  const api = useStore.getState().api;
  const spy = vi.spyOn(api, 'steer');
  useStore.setState({ graph: { nodes: [], edges: [] }, messages: [] });
  render(<ChannelPanel />);

  await userEvent.type(screen.getByLabelText('steer 입력'), 'use Stripe');
  await userEvent.click(screen.getByRole('button', { name: '전송' }));

  await waitFor(() => expect(spy).toHaveBeenCalledWith('use Stripe', { ticketId: undefined, stepId: undefined }));
  await screen.findByText('use Stripe'); // the user 'steer' message appears in the channel
});

test('a not-yet-loaded graph shows neither actions nor 처리됨 (never hides a live gate)', () => {
  useStore.setState({
    graph: null,
    messages: [{ id: 1, type: 'review', author: 'agent', text: '리뷰', refs: ['s4'], ts: 't' }],
  });
  render(<ChannelPanel />);
  expect(screen.queryByRole('button', { name: '승인' })).not.toBeInTheDocument();
  expect(screen.queryByText('처리됨')).not.toBeInTheDocument(); // unknown, not "processed"
});

test('only the latest review message per step carries live actions', () => {
  const graph: ProjectGraph = {
    nodes: [{ id: 's4', kind: 'step', label: '구현', status: 'awaiting_review' }],
    edges: [],
  };
  useStore.setState({
    graph,
    messages: [
      { id: 1, type: 'review', author: 'agent', text: '이전 리뷰', refs: ['s4'], ts: 't' },
      { id: 2, type: 'review', author: 'agent', text: '새 리뷰', refs: ['s4'], ts: 't' },
    ],
  });
  render(<ChannelPanel />);
  expect(screen.getAllByRole('button', { name: '승인' })).toHaveLength(1); // only the latest gate
});

test('a message ref chip focuses the node on the map (CP4 channel->map)', async () => {
  useStore.setState({
    graph: { nodes: [{ id: 's4', kind: 'step', label: '구현' }], edges: [] },
    messages: [{ id: 1, type: 'decision', author: 'system', text: '결정 X', refs: ['s4'], ts: 't' }],
    highlightIds: null,
    channelFilter: null,
  });
  render(<ChannelPanel />);
  await userEvent.click(screen.getByRole('button', { name: '구현' })); // the ref chip (node label)
  expect(useStore.getState().highlightIds).toEqual(['s4']);
});

test('a channel filter (map node click) narrows to that node’s thread (CP4 map->channel)', () => {
  useStore.setState({
    graph: { nodes: [{ id: 's4', kind: 'step', label: '구현' }], edges: [] },
    channelFilter: 's4',
    messages: [
      { id: 1, type: 'system', author: 'system', text: '이건 s4', refs: ['s4'], ts: 't' },
      { id: 2, type: 'system', author: 'system', text: '이건 s9', refs: ['s9'], ts: 't' },
    ],
  });
  render(<ChannelPanel />);
  expect(screen.getByText('이건 s4')).toBeInTheDocument();
  expect(screen.queryByText('이건 s9')).not.toBeInTheDocument(); // filtered out of the thread
});

test('filtering by a ticket includes its owned steps’ messages (CP4 ticket thread, not empty)', () => {
  useStore.setState({
    graph: {
      nodes: [
        { id: 't1', kind: 'ticket', label: '결제' },
        { id: 's4', kind: 'step', label: '구현' },
        { id: 's9', kind: 'step', label: '남의 스텝' },
      ],
      edges: [{ id: 'e1', from: 't1', to: 's4', kind: 'has' }],
    },
    channelFilter: 't1', // a map click on the ticket
    messages: [
      { id: 1, type: 'review', author: 'agent', text: 's4 리뷰 대기', refs: ['s4'], ts: 't' },
      { id: 2, type: 'system', author: 'system', text: '다른 티켓 스텝', refs: ['s9'], ts: 't' },
    ],
  });
  render(<ChannelPanel />);
  expect(screen.getByText('s4 리뷰 대기')).toBeInTheDocument(); // owned step's message shows under its ticket
  expect(screen.queryByText('다른 티켓 스텝')).not.toBeInTheDocument(); // an unowned step stays filtered out
});

test('review actions disappear once the referenced step is no longer actionable', () => {
  const graph: ProjectGraph = {
    nodes: [{ id: 's9', kind: 'step', label: 's', status: 'done' }],
    edges: [],
  };
  useStore.setState({
    graph,
    messages: [{ id: 1, type: 'review', author: 'agent', text: '리뷰', refs: ['s9'], ts: 't' }],
  });
  render(<ChannelPanel />);
  expect(screen.queryByRole('button', { name: '승인' })).not.toBeInTheDocument();
  expect(screen.getByText('처리됨')).toBeInTheDocument();
});
