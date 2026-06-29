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
      { id: 's1', kind: 'step', label: '할일 모델 + 저장', status: 'done' },
      { id: 's2', kind: 'step', label: '할일 추가 폼', status: 'done' },
      { id: 's3', kind: 'step', label: '티어 플래그 정의', status: 'done' },
      { id: 's4', kind: 'step', label: '게이트 컴포넌트', status: 'awaiting_review' },
      { id: 's5', kind: 'step', label: '업그레이드 안내 UI', status: 'planning' },
      { id: 'c-model', kind: 'code_region', label: 'src/todo/model.ts' },
      { id: 'c-form', kind: 'code_region', label: 'src/todo/TodoForm.tsx' },
      { id: 'c-flags', kind: 'code_region', label: 'src/billing/flags.ts' },
      { id: 'c-gate', kind: 'code_region', label: 'src/billing/FeatureGate.tsx' },
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
    ],
  };
}
