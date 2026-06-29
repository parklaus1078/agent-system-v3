import type { ProjectGraph } from '../../domain/graph';

// The wireframe's sample project: "구독 티어 할일앱" (todo app with Free/Pro/Team
// tiers + feature gating). One objective, two tickets, steps across every status
// (one awaiting_review — the review gate), code regions, a test, and a decision.
export function makeFixture(): ProjectGraph {
  return {
    nodes: [
      {
        id: 'obj',
        kind: 'objective',
        label: '구독 티어 할일앱',
        data: { short: '구독 할일앱', description: 'Free / Pro / Team 구독 티어와 기능 게이팅을 갖춘 할 일 관리 앱' },
      },
      { id: 't-crud', kind: 'ticket', label: '할일 CRUD', status: 'done', data: { tag: 'CRUD' } },
      { id: 't-gate', kind: 'ticket', label: '구독 티어 + 기능 게이팅', status: 'executing', data: { tag: 'GATE' } },
      { id: 't-pay', kind: 'ticket', label: '페이월 & 업셀', status: 'planning', data: { tag: 'PAY' } },
      { id: 't-sync', kind: 'ticket', label: '오프라인 동기화', status: 'blocked', data: { tag: 'SYNC' } },
      { id: 's1', kind: 'step', label: '할일 모델 + 저장', status: 'done' },
      { id: 's2', kind: 'step', label: '할일 추가 폼', status: 'done' },
      { id: 's3', kind: 'step', label: '티어 플래그 정의', status: 'done' },
      { id: 's4', kind: 'step', label: '게이트 컴포넌트', status: 'awaiting_review' },
      { id: 's5', kind: 'step', label: '업그레이드 안내 UI', status: 'planning' },
      // planning ticket — every step still queued
      { id: 'sp1', kind: 'step', label: '페이월 화면 골격', status: 'planning' },
      { id: 'sp2', kind: 'step', label: '업셀 카피', status: 'planning' },
      // blocked ticket — a done step, a blocked step, then queued
      { id: 'sy1', kind: 'step', label: '동기화 큐', status: 'done' },
      { id: 'sy2', kind: 'step', label: '충돌 해결', status: 'blocked' },
      { id: 'sy3', kind: 'step', label: '재시도 로직', status: 'planning' },
      { id: 'c-model', kind: 'code_region', label: 'src/todo/model.ts' },
      { id: 'c-form', kind: 'code_region', label: 'src/todo/TodoForm.tsx' },
      { id: 'c-flags', kind: 'code_region', label: 'src/billing/flags.ts' },
      { id: 'c-gate', kind: 'code_region', label: 'src/billing/FeatureGate.tsx' },
      { id: 'c-syncq', kind: 'code_region', label: 'src/sync/queue.ts' },
      { id: 'tst-gate', kind: 'test', label: 'FeatureGate.test.tsx' },
      { id: 'dec', kind: 'decision', label: '게이팅은 플래그로 (티어 분기 금지)' },
    ],
    edges: [
      { id: 'e1', from: 'obj', to: 't-crud', kind: 'has' },
      { id: 'e2', from: 'obj', to: 't-gate', kind: 'has' },
      { id: 'e3', from: 't-crud', to: 's1', kind: 'has' },
      { id: 'e4', from: 't-crud', to: 's2', kind: 'has' },
      { id: 'e5', from: 't-gate', to: 's3', kind: 'has' },
      { id: 'e6', from: 't-gate', to: 's4', kind: 'has' },
      { id: 'e7', from: 't-gate', to: 's5', kind: 'has' },
      { id: 'e8', from: 's1', to: 'c-model', kind: 'touches' },
      { id: 'e9', from: 's2', to: 'c-form', kind: 'touches' },
      { id: 'e10', from: 's3', to: 'c-flags', kind: 'touches' },
      { id: 'e11', from: 's4', to: 'c-gate', kind: 'touches' },
      { id: 'e12', from: 's4', to: 'tst-gate', kind: 'tested_by' },
      { id: 'e13', from: 'c-gate', to: 'tst-gate', kind: 'tested_by' },
      { id: 'e14', from: 's4', to: 'dec', kind: 'decided' },
      { id: 'e15', from: 'obj', to: 't-pay', kind: 'has' },
      { id: 'e16', from: 'obj', to: 't-sync', kind: 'has' },
      { id: 'e17', from: 't-pay', to: 'sp1', kind: 'has' },
      { id: 'e18', from: 't-pay', to: 'sp2', kind: 'has' },
      { id: 'e19', from: 't-sync', to: 'sy1', kind: 'has' },
      { id: 'e20', from: 't-sync', to: 'sy2', kind: 'has' },
      { id: 'e21', from: 't-sync', to: 'sy3', kind: 'has' },
      { id: 'e22', from: 'sy1', to: 'c-syncq', kind: 'touches' },
    ],
  };
}
