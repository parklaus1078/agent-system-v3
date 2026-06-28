# Frontend UI (on Mock API) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Use Karpathy-skill to think about how to write the actual codes.

**Goal:** Build the clickable v1 frontend of the LLM Dev Control Tower — the 4 main screens (Project Map, Ticket Lane, Review Pane, Bug Trace) plus Plan Approval and Goal Entry — running entirely on a typed **mock API** with fixture data, faithful to the wireframe.

**Architecture:** A React + Vite + TypeScript single-page app. All data comes through one `ApiClient` interface; v1 ships only a `MockApiClient` backed by in-memory fixtures + a simulated lifecycle ticker (so step state advances `planning → executing → awaiting_review → done` without a backend). The graph map uses React Flow. State lives in a small store; the UI subscribes so it is always live (no manual refresh). When the real backend exists, only the `ApiClient` implementation swaps.

**Tech Stack:** React 18, Vite, TypeScript (strict), React Flow (`@xyflow/react`), Zustand (store), Vitest + @testing-library/react (tests).

## Global Constraints

- Frontend lives in `~/agent-system-v3/web/`. All paths below are relative to that unless noted.
- **No backend in this plan.** Data only through `src/api/ApiClient.ts`; v1 implements `MockApiClient`. Never call `fetch` to a real server.
- Domain types mirror spec §6 exactly: node kinds `Objective | Ticket | Step | CodeRegion | Test | Decision`; edge kinds `has | subdivides | touches | tested_by | decided | produced`; status `planning | executing | awaiting_review | done | blocked`.
- **Anti-patterns (forbidden in UI):** no "Worker tick"/"Watcher tick" buttons, no manual Refresh dependency, no raw file absolute paths / API URLs / actor names exposed, no single-screen vertical form-dump.
- **Visual source of truth:** `docs/design/wireframes/llm-dev-control-tower.html` (a self-contained mockup; open it in a browser while implementing). On any visual ambiguity, match the wireframe. Functional/data truth = spec §6/§7/§8.
- Tone: minimal, information-dense, dark-first developer-console. Monospace for code/ids. Motion only to make state transitions legible.
- TypeScript strict mode on. Every task ends green (`npm run test`) and the dev app runs (`npm run dev`).

---

## File Structure

```
web/
  package.json  vite.config.ts  tsconfig.json  index.html  .eslintrc.cjs
  src/
    main.tsx                      # React root
    App.tsx                       # Shell + altitude routing
    domain/graph.ts               # §6 types: nodes, edges, status, type guards
    api/
      ApiClient.ts                # the interface every screen depends on
      dto.ts                      # request/response shapes (PlanProposal, ReviewAction, DiffBlob...)
      mock/
        fixtures.ts               # the "subscription-tier todo app" sample graph
        MockApiClient.ts          # ApiClient over fixtures + lifecycle simulation
    store/
      useStore.ts                 # Zustand store: graph, selection, live subscription
      lifecycle.ts                # pure step-state transitions
    design/tokens.css             # color/typography/spacing tokens (dark console)
    components/
      Shell.tsx                   # top layout + altitude nav (map <-> lane), bug-trace entry
      map/ProjectMap.tsx          # React Flow canvas (zoom-out)
      map/nodeTypes.tsx           # node renderers per kind + status color
      lane/TicketLane.tsx         # step timeline (zoom-in)
      review/ReviewPane.tsx       # 2-pane: diff | map-slice + decision + acceptance + 3 actions
      review/DiffView.tsx         # diff renderer
      bugtrace/BugTrace.tsx       # search/select -> owning-path highlight
      plan/PlanApproval.tsx       # edit + approve proposed steps
      goal/GoalEntry.tsx          # new-goal input
    test/setup.ts
```

---

## Task 1: Scaffold the web app + test runner

**Files:**
- Create: `web/package.json`, `web/vite.config.ts`, `web/tsconfig.json`, `web/index.html`, `web/src/main.tsx`, `web/src/App.tsx`, `web/src/test/setup.ts`, `web/.eslintrc.cjs`
- Test: `web/src/App.test.tsx`

**Interfaces:**
- Produces: a runnable Vite app (`npm run dev`) and a green test runner (`npm run test`). `App` exports default React component rendering the text `LLM Dev Control Tower`.

- [ ] **Step 1: Create `web/package.json`**

```json
{
  "name": "control-tower-web",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "test": "vitest run",
    "test:watch": "vitest",
    "lint": "eslint src --ext .ts,.tsx"
  },
  "dependencies": {
    "@xyflow/react": "^12.3.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "zustand": "^4.5.5"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.4.8",
    "@testing-library/react": "^16.0.1",
    "@testing-library/user-event": "^14.5.2",
    "@types/react": "^18.3.5",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.1",
    "jsdom": "^25.0.0",
    "typescript": "^5.5.4",
    "vite": "^5.4.2",
    "vitest": "^2.0.5"
  }
}
```

- [ ] **Step 2: Create config files**

`web/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022", "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext", "moduleResolution": "Bundler", "jsx": "react-jsx",
    "strict": true, "noUnusedLocals": true, "noUnusedParameters": true,
    "skipLibCheck": true, "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src"]
}
```

`web/vite.config.ts`:
```ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
  },
});
```

`web/index.html`:
```html
<!doctype html>
<html lang="ko">
  <head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>LLM Dev Control Tower</title></head>
  <body><div id="root"></div><script type="module" src="/src/main.tsx"></script></body>
</html>
```

`web/src/test/setup.ts`:
```ts
import '@testing-library/jest-dom/vitest';
```

`web/.eslintrc.cjs`:
```js
module.exports = {
  root: true,
  parser: '@typescript-eslint/parser',
  plugins: ['@typescript-eslint'],
  extends: ['eslint:recommended'],
  env: { browser: true, es2022: true },
};
```

- [ ] **Step 3: Create `web/src/main.tsx` and `web/src/App.tsx`**

```tsx
// main.tsx
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';

createRoot(document.getElementById('root')!).render(
  <StrictMode><App /></StrictMode>,
);
```
```tsx
// App.tsx
export default function App() {
  return <div className="app">LLM Dev Control Tower</div>;
}
```

- [ ] **Step 4: Write the failing test** — `web/src/App.test.tsx`

```tsx
import { render, screen } from '@testing-library/react';
import App from './App';

test('renders the product name', () => {
  render(<App />);
  expect(screen.getByText('LLM Dev Control Tower')).toBeInTheDocument();
});
```

- [ ] **Step 5: Install + run test**

Run: `cd web && npm install && npm run test`
Expected: 1 passed.

- [ ] **Step 6: Verify dev server boots**

Run: `npm run dev` → open the printed URL → page shows "LLM Dev Control Tower". Stop the server.

- [ ] **Step 7: Commit**

```bash
cd ~/agent-system-v3
git add web && git commit -m "feat(web): scaffold Vite+React+TS app with Vitest"
```

---

## Task 2: Domain types (spec §6)

**Files:**
- Create: `web/src/domain/graph.ts`
- Test: `web/src/domain/graph.test.ts`

**Interfaces:**
- Produces:
  - `NodeKind = 'objective'|'ticket'|'step'|'code_region'|'test'|'decision'`
  - `EdgeKind = 'has'|'subdivides'|'touches'|'tested_by'|'decided'|'produced'`
  - `Status = 'planning'|'executing'|'awaiting_review'|'done'|'blocked'`
  - `interface GraphNode { id: string; kind: NodeKind; label: string; status?: Status; data?: Record<string, unknown> }`
  - `interface GraphEdge { id: string; from: string; to: string; kind: EdgeKind }`
  - `interface ProjectGraph { nodes: GraphNode[]; edges: GraphEdge[] }`
  - `function neighbors(g: ProjectGraph, nodeId: string, dir: 'in'|'out'|'both'): GraphNode[]`

- [ ] **Step 1: Write the failing test**

```ts
import { neighbors, type ProjectGraph } from './graph';

const g: ProjectGraph = {
  nodes: [
    { id: 'o1', kind: 'objective', label: 'Todo' },
    { id: 't1', kind: 'ticket', label: 'CRUD', status: 'executing' },
    { id: 's1', kind: 'step', label: 'add form', status: 'awaiting_review' },
    { id: 'c1', kind: 'code_region', label: 'TodoForm.tsx' },
  ],
  edges: [
    { id: 'e1', from: 'o1', to: 't1', kind: 'has' },
    { id: 'e2', from: 't1', to: 's1', kind: 'has' },
    { id: 'e3', from: 's1', to: 'c1', kind: 'touches' },
  ],
};

test('neighbors out returns direct children', () => {
  expect(neighbors(g, 't1', 'out').map((n) => n.id)).toEqual(['s1']);
});
test('neighbors in returns parents', () => {
  expect(neighbors(g, 's1', 'in').map((n) => n.id)).toEqual(['t1']);
});
test('neighbors both is union', () => {
  expect(neighbors(g, 's1', 'both').map((n) => n.id).sort()).toEqual(['c1', 't1']);
});
```

- [ ] **Step 2: Run test, expect FAIL** — `cd web && npx vitest run src/domain/graph.test.ts` → fails (module not found).

- [ ] **Step 3: Implement `web/src/domain/graph.ts`**

```ts
export type NodeKind = 'objective' | 'ticket' | 'step' | 'code_region' | 'test' | 'decision';
export type EdgeKind = 'has' | 'subdivides' | 'touches' | 'tested_by' | 'decided' | 'produced';
export type Status = 'planning' | 'executing' | 'awaiting_review' | 'done' | 'blocked';

export interface GraphNode {
  id: string;
  kind: NodeKind;
  label: string;
  status?: Status;
  data?: Record<string, unknown>;
}
export interface GraphEdge { id: string; from: string; to: string; kind: EdgeKind }
export interface ProjectGraph { nodes: GraphNode[]; edges: GraphEdge[] }

export function neighbors(g: ProjectGraph, nodeId: string, dir: 'in' | 'out' | 'both'): GraphNode[] {
  const byId = new Map(g.nodes.map((n) => [n.id, n]));
  const ids = new Set<string>();
  for (const e of g.edges) {
    if ((dir === 'out' || dir === 'both') && e.from === nodeId) ids.add(e.to);
    if ((dir === 'in' || dir === 'both') && e.to === nodeId) ids.add(e.from);
  }
  return [...ids].map((id) => byId.get(id)!).filter(Boolean);
}
```

- [ ] **Step 4: Run test, expect PASS.**

- [ ] **Step 5: Commit** — `git add web/src/domain && git commit -m "feat(web): domain graph types (spec §6)"`

---

## Task 3: Mock API contract + fixtures

**Files:**
- Create: `web/src/api/dto.ts`, `web/src/api/ApiClient.ts`, `web/src/api/mock/fixtures.ts`, `web/src/api/mock/MockApiClient.ts`
- Test: `web/src/api/mock/MockApiClient.test.ts`

**Interfaces:**
- Produces:
  - `interface DiffBlob { path: string; patch: string }`
  - `interface StepDetail { node: GraphNode; diff: DiffBlob[]; decision?: string; acceptance: { text: string; met: boolean }[]; createdNodeIds: string[]; createdEdgeIds: string[] }`
  - `type ReviewAction = { kind: 'approve' } | { kind: 'changes'; comment: string } | { kind: 'takeover' }`
  - `interface PlanProposal { ticketId: string; steps: { label: string; intent: string; acceptance: string }[] }`
  - `interface ApiClient { getGraph(): Promise<ProjectGraph>; getStepDetail(stepId): Promise<StepDetail>; proposePlan(goal): Promise<PlanProposal>; approvePlan(p): Promise<void>; reviewStep(stepId, action): Promise<void>; owningPath(nodeId): Promise<string[]>; subscribe(cb:()=>void): ()=>void }`
- Consumes: `domain/graph.ts` types.

- [ ] **Step 1: Write `web/src/api/dto.ts` and `web/src/api/ApiClient.ts`**

```ts
// dto.ts
import type { GraphNode } from '../domain/graph';
export interface DiffBlob { path: string; patch: string }
export interface Acceptance { text: string; met: boolean }
export interface StepDetail {
  node: GraphNode; diff: DiffBlob[]; decision?: string;
  acceptance: Acceptance[]; createdNodeIds: string[]; createdEdgeIds: string[];
}
export type ReviewAction = { kind: 'approve' } | { kind: 'changes'; comment: string } | { kind: 'takeover' };
export interface PlanProposal { ticketId: string; steps: { label: string; intent: string; acceptance: string }[] }
```
```ts
// ApiClient.ts
import type { ProjectGraph } from '../domain/graph';
import type { StepDetail, ReviewAction, PlanProposal } from './dto';
export interface ApiClient {
  getGraph(): Promise<ProjectGraph>;
  getStepDetail(stepId: string): Promise<StepDetail>;
  proposePlan(goal: string): Promise<PlanProposal>;
  approvePlan(proposal: PlanProposal): Promise<void>;
  reviewStep(stepId: string, action: ReviewAction): Promise<void>;
  owningPath(nodeId: string): Promise<string[]>;   // node ids from CodeRegion up to Objective
  subscribe(cb: () => void): () => void;            // called on any state change
}
```

- [ ] **Step 2: Write fixtures** — `web/src/api/mock/fixtures.ts`

Build the wireframe's sample project: **"구독 티어 할일앱"** (Todo app with Free/Pro/Team tiers + feature gating). Include 1 objective, 2 tickets, several steps across statuses (one `awaiting_review`), code regions, one decision (feature-gating-via-flags). Exact content:

```ts
import type { ProjectGraph } from '../../domain/graph';

export function makeFixture(): ProjectGraph {
  return {
    nodes: [
      { id: 'obj', kind: 'objective', label: '구독 티어 할일앱' },
      { id: 't-crud', kind: 'ticket', label: '할일 CRUD', status: 'done' },
      { id: 't-gate', kind: 'ticket', label: '구독 티어 + 기능 게이팅', status: 'executing' },
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
      { id: 'e12', from: 's4', to: 'tst-gate', kind: 'adds' as never },
      { id: 'e13', from: 'c-gate', to: 'tst-gate', kind: 'tested_by' },
      { id: 'e14', from: 's4', to: 'dec', kind: 'decided' },
    ],
  };
}
```
(Note: use `kind: 'tested_by'` for e12 instead of the placeholder — set `{ id: 'e12', from: 's4', to: 'tst-gate', kind: 'tested_by' }` and drop the `as never`. Keep only valid `EdgeKind` values.)

- [ ] **Step 3: Write the failing test** — `web/src/api/mock/MockApiClient.test.ts`

```ts
import { MockApiClient } from './MockApiClient';

test('getGraph returns the fixture with an awaiting_review step', async () => {
  const api = new MockApiClient();
  const g = await api.getGraph();
  expect(g.nodes.find((n) => n.id === 's4')?.status).toBe('awaiting_review');
});

test('owningPath walks CodeRegion -> Step -> Ticket -> Objective', async () => {
  const api = new MockApiClient();
  const path = await api.owningPath('c-gate');
  expect(path).toEqual(['c-gate', 's4', 't-gate', 'obj']);
});

test('reviewStep approve advances the step to done and notifies subscribers', async () => {
  const api = new MockApiClient();
  let pinged = 0;
  api.subscribe(() => { pinged++; });
  await api.reviewStep('s4', { kind: 'approve' });
  const g = await api.getGraph();
  expect(g.nodes.find((n) => n.id === 's4')?.status).toBe('done');
  expect(pinged).toBeGreaterThan(0);
});
```

- [ ] **Step 4: Run test, expect FAIL.**

- [ ] **Step 5: Implement `web/src/api/mock/MockApiClient.ts`**

```ts
import type { ProjectGraph, GraphNode } from '../../domain/graph';
import { neighbors } from '../../domain/graph';
import type { ApiClient } from '../ApiClient';
import type { StepDetail, ReviewAction, PlanProposal } from '../dto';
import { makeFixture } from './fixtures';

export class MockApiClient implements ApiClient {
  private graph: ProjectGraph = makeFixture();
  private subs = new Set<() => void>();

  private notify() { this.subs.forEach((cb) => cb()); }
  subscribe(cb: () => void) { this.subs.add(cb); return () => this.subs.delete(cb); }

  async getGraph(): Promise<ProjectGraph> { return structuredClone(this.graph); }

  async getStepDetail(stepId: string): Promise<StepDetail> {
    const node = this.graph.nodes.find((n) => n.id === stepId)!;
    const touched = neighbors(this.graph, stepId, 'out').filter((n) => n.kind === 'code_region');
    return {
      node,
      diff: touched.map((c) => ({ path: c.label, patch: sampleDiff(c.label) })),
      decision: neighbors(this.graph, stepId, 'out').find((n) => n.kind === 'decision')?.label,
      acceptance: [{ text: `${node.label} 동작 확인`, met: true }],
      createdNodeIds: touched.map((c) => c.id),
      createdEdgeIds: this.graph.edges.filter((e) => e.from === stepId).map((e) => e.id),
    };
  }

  async proposePlan(goal: string): Promise<PlanProposal> {
    return {
      ticketId: 't-new',
      steps: [
        { label: '스펙·골격', intent: `${goal} 스펙 정리`, acceptance: '스펙 합의' },
        { label: '구현', intent: '핵심 구현', acceptance: '동작' },
        { label: '테스트', intent: '테스트 추가', acceptance: '그린' },
      ],
    };
  }

  async approvePlan(_p: PlanProposal): Promise<void> { this.notify(); }

  async reviewStep(stepId: string, action: ReviewAction): Promise<void> {
    const node = this.graph.nodes.find((n) => n.id === stepId);
    if (!node) return;
    if (action.kind === 'approve') node.status = 'done';
    else if (action.kind === 'changes') node.status = 'executing';
    else node.status = 'awaiting_review';
    this.notify();
  }

  async owningPath(nodeId: string): Promise<string[]> {
    const order: GraphNode['kind'][] = ['code_region', 'step', 'ticket', 'objective'];
    const path = [nodeId];
    let cur = nodeId;
    for (let i = 0; i < order.length - 1; i++) {
      const parent = neighbors(this.graph, cur, 'in').find((n) => n.kind === order[i + 1]);
      if (!parent) break;
      path.push(parent.id);
      cur = parent.id;
    }
    return path;
  }
}

function sampleDiff(path: string): string {
  return `--- a/${path}\n+++ b/${path}\n@@ -0,0 +1,3 @@\n+// generated by step\n+export const ok = true;\n`;
}
```

- [ ] **Step 6: Run test, expect PASS.**

- [ ] **Step 7: Commit** — `git add web/src/api && git commit -m "feat(web): mock ApiClient + fixtures (subscription-tier todo app)"`

---

## Task 4: Store + simulated live lifecycle

**Files:**
- Create: `web/src/store/lifecycle.ts`, `web/src/store/useStore.ts`
- Test: `web/src/store/lifecycle.test.ts`

**Interfaces:**
- Produces:
  - `function nextStatus(s: Status): Status` (`planning→executing→awaiting_review→done`; `done`/`blocked` stay)
  - `useStore` (Zustand): `{ graph: ProjectGraph|null; selectedTicketId: string|null; selectedStepId: string|null; load(): Promise<void>; select(...); api: ApiClient }` that calls `api.subscribe` to refresh `graph` automatically (the "always live, no manual refresh" guarantee).

- [ ] **Step 1: Write the failing test** — `web/src/store/lifecycle.test.ts`

```ts
import { nextStatus } from './lifecycle';

test('lifecycle advances planning -> executing -> awaiting_review -> done', () => {
  expect(nextStatus('planning')).toBe('executing');
  expect(nextStatus('executing')).toBe('awaiting_review');
  expect(nextStatus('awaiting_review')).toBe('done');
});
test('terminal statuses are stable', () => {
  expect(nextStatus('done')).toBe('done');
  expect(nextStatus('blocked')).toBe('blocked');
});
```

- [ ] **Step 2: Run test, expect FAIL.**

- [ ] **Step 3: Implement `web/src/store/lifecycle.ts`**

```ts
import type { Status } from '../domain/graph';
const ORDER: Status[] = ['planning', 'executing', 'awaiting_review', 'done'];
export function nextStatus(s: Status): Status {
  if (s === 'done' || s === 'blocked') return s;
  const i = ORDER.indexOf(s);
  return i < 0 || i === ORDER.length - 1 ? s : ORDER[i + 1];
}
```

- [ ] **Step 4: Run test, expect PASS.**

- [ ] **Step 5: Implement `web/src/store/useStore.ts`** (no separate unit test; covered by component tests)

```ts
import { create } from 'zustand';
import type { ProjectGraph } from '../domain/graph';
import type { ApiClient } from '../api/ApiClient';
import { MockApiClient } from '../api/mock/MockApiClient';

interface State {
  api: ApiClient;
  graph: ProjectGraph | null;
  selectedTicketId: string | null;
  selectedStepId: string | null;
  load: () => Promise<void>;
  selectTicket: (id: string | null) => void;
  selectStep: (id: string | null) => void;
}

export const useStore = create<State>((set, get) => {
  const api = new MockApiClient();
  api.subscribe(() => { void get().load(); });   // always live: refresh on any change
  return {
    api,
    graph: null,
    selectedTicketId: null,
    selectedStepId: null,
    load: async () => set({ graph: await api.getGraph() }),
    selectTicket: (id) => set({ selectedTicketId: id }),
    selectStep: (id) => set({ selectedStepId: id }),
  };
});
```

- [ ] **Step 6: Commit** — `git add web/src/store && git commit -m "feat(web): store + simulated live lifecycle"`

---

## Task 5: App shell + design tokens + altitude nav

**Files:**
- Create: `web/src/design/tokens.css`, `web/src/components/Shell.tsx`
- Modify: `web/src/App.tsx` (render Shell), `web/src/main.tsx` (import tokens.css)
- Test: `web/src/components/Shell.test.tsx`

**Interfaces:**
- Consumes: `useStore`.
- Produces: `Shell` with two altitudes — `map` (default) and `lane` (when a ticket is selected) — and a bug-trace entry. Renders the project objective label in a slim top bar. **No** Refresh/tick buttons, no API URL.

- [ ] **Step 1: Write `tokens.css`** — dark developer-console palette; status colors. Match the wireframe's palette (open it and sample). Minimum tokens:

```css
:root {
  --bg: #0f1117; --panel: #171a23; --border: #2a2f3d; --fg: #e6e8ee; --muted: #9aa3b4;
  --planning: #9aa3b4; --executing: #7aa2f7; --awaiting: #e0af68; --done: #9ece6a; --blocked: #f7768e;
  --mono: ui-monospace, SFMono-Regular, Menlo, monospace;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg);
  font-family: ui-sans-serif, system-ui, "Noto Sans KR", sans-serif; }
.mono { font-family: var(--mono); }
```

- [ ] **Step 2: Write the failing test** — `Shell.test.tsx`

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Shell } from './Shell';

test('shows objective and switches to lane when a ticket is opened', async () => {
  render(<Shell />);
  await waitFor(() => expect(screen.getByText('구독 티어 할일앱')).toBeInTheDocument());
  // map shows tickets; opening one switches altitude to the lane
  await userEvent.click(await screen.findByText('구독 티어 + 기능 게이팅'));
  expect(await screen.findByTestId('ticket-lane')).toBeInTheDocument();
});

test('does NOT render internal plumbing controls', async () => {
  render(<Shell />);
  await waitFor(() => expect(screen.getByText('구독 티어 할일앱')).toBeInTheDocument());
  expect(screen.queryByText(/worker tick/i)).toBeNull();
  expect(screen.queryByText(/watcher tick/i)).toBeNull();
  expect(screen.queryByText(/refresh/i)).toBeNull();
});
```

- [ ] **Step 3: Implement `Shell.tsx`** — load graph on mount, render top bar with objective label, render `ProjectMap` at the `map` altitude and `TicketLane` when `selectedTicketId` is set. Use `data-testid="ticket-lane"` on the lane container. Import `ProjectMap` (Task 6) and `TicketLane` (Task 7) — create thin placeholders now and fill them in their tasks. Wire `selectTicket` from map clicks.

- [ ] **Step 4: Update `App.tsx`** to render `<Shell />`; import `./design/tokens.css` in `main.tsx`.

- [ ] **Step 5: Run tests** (Shell test may depend on Task 6/7 placeholders — use minimal placeholders that render the objective + ticket labels and a `ticket-lane` testid so this task is green on its own). Expected: PASS.

- [ ] **Step 6: Run the app**, compare top bar + altitude switching against the wireframe. Fix discrepancies.

- [ ] **Step 7: Commit** — `git add web/src && git commit -m "feat(web): app shell, tokens, altitude nav"`

---

## Task 6: Project Map (React Flow, zoom-out)

**Files:**
- Create: `web/src/components/map/ProjectMap.tsx`, `web/src/components/map/nodeTypes.tsx`
- Test: `web/src/components/map/ProjectMap.test.tsx`

**Interfaces:**
- Consumes: `useStore` (graph), `selectTicket`.
- Produces: `ProjectMap` rendering one React Flow node per `GraphNode`, colored by `status`, with a **CodeRegion layer toggle** (hides `code_region`/`test` nodes + `touches`/`tested_by` edges when off). Clicking a `ticket` node calls `selectTicket(id)`.

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ProjectMap } from './ProjectMap';

test('renders a node per graph node and toggles the code layer', async () => {
  render(<ProjectMap />);
  await waitFor(() => expect(screen.getByText('구독 티어 + 기능 게이팅')).toBeInTheDocument());
  // code regions hidden by default
  expect(screen.queryByText('src/billing/FeatureGate.tsx')).toBeNull();
  await userEvent.click(screen.getByRole('button', { name: /code/i }));
  expect(await screen.findByText('src/billing/FeatureGate.tsx')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test, expect FAIL.**

- [ ] **Step 3: Implement `nodeTypes.tsx`** — a node renderer per kind. Each shows the label; ticket nodes show step-progress `N/M`; border/dot color = `var(--{status})`. Use the wireframe node styling as the visual reference.

- [ ] **Step 4: Implement `ProjectMap.tsx`** — map `graph.nodes`→React Flow nodes (auto-layout: objective at top, tickets below, steps/code under their ticket; a simple layered position function is fine), `graph.edges`→edges. A toggle button labeled "Code layer" filters `code_region`/`test` nodes and their edges. `onNodeClick`: if kind==='ticket', `selectTicket(id)`. Wrap in `<ReactFlowProvider>`; import `@xyflow/react` styles.

- [ ] **Step 5: Run test, expect PASS.**

- [ ] **Step 6: Run the app**, compare the map against the wireframe (node shapes, status colors, layer toggle). Fix.

- [ ] **Step 7: Commit** — `git add web/src/components/map && git commit -m "feat(web): project map with status colors + code-layer toggle"`

---

## Task 7: Ticket Lane (step timeline, zoom-in)

**Files:**
- Create: `web/src/components/lane/TicketLane.tsx`
- Test: `web/src/components/lane/TicketLane.test.tsx`

**Interfaces:**
- Consumes: `useStore` (graph, selectedTicketId, selectStep).
- Produces: `TicketLane` rendering the selected ticket's steps (via `has` edges) as a timeline of cards with status; the `awaiting_review` step is visually emphasized (`data-emphasis="true"`). Clicking a step calls `selectStep(id)`.

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import { useStore } from '../../store/useStore';
import { TicketLane } from './TicketLane';

test('emphasizes the awaiting_review step', async () => {
  await useStore.getState().load();
  useStore.getState().selectTicket('t-gate');
  render(<TicketLane />);
  await waitFor(() => expect(screen.getByText('게이트 컴포넌트')).toBeInTheDocument());
  const card = screen.getByText('게이트 컴포넌트').closest('[data-emphasis]');
  expect(card).toHaveAttribute('data-emphasis', 'true');
});
```

- [ ] **Step 2: Run test, expect FAIL.**

- [ ] **Step 3: Implement `TicketLane.tsx`** — read steps = `neighbors(graph, selectedTicketId, 'out')` filtered to `kind==='step'`; render each as a card (number, label, status dot, touched code-region preview). `data-emphasis="true"` when `status==='awaiting_review'`. Container has `data-testid="ticket-lane"`. Click → `selectStep(id)`. Match the wireframe lane.

- [ ] **Step 4: Run test, expect PASS.**

- [ ] **Step 5: Run the app**, compare lane to wireframe. Fix.

- [ ] **Step 6: Commit** — `git add web/src/components/lane && git commit -m "feat(web): ticket lane step timeline"`

---

## Task 8: Review Pane (the gate — most important)

**Files:**
- Create: `web/src/components/review/ReviewPane.tsx`, `web/src/components/review/DiffView.tsx`
- Test: `web/src/components/review/ReviewPane.test.tsx`

**Interfaces:**
- Consumes: `useStore` (api, selectedStepId), `getStepDetail`, `reviewStep`.
- Produces: `ReviewPane` 2-pane layout — left `DiffView` (renders `StepDetail.diff` patches), right = "이 step이 만든 지도 조각" (created node/edge ids) + decision + acceptance list. Bottom fixed bar: **승인 / 수정요청 / 내가 인수**. "수정요청" reveals a comment input then calls `reviewStep(id,{kind:'changes',comment})`.

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useStore } from '../../store/useStore';
import { ReviewPane } from './ReviewPane';

test('renders diff + 3 actions and approves a step', async () => {
  await useStore.getState().load();
  useStore.getState().selectStep('s4');
  render(<ReviewPane />);
  await waitFor(() => expect(screen.getByText(/FeatureGate.tsx/)).toBeInTheDocument());
  expect(screen.getByRole('button', { name: '승인' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '수정요청' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '내가 인수' })).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: '승인' }));
  await waitFor(async () => {
    const g = await useStore.getState().api.getGraph();
    expect(g.nodes.find((n) => n.id === 's4')?.status).toBe('done');
  });
});
```

- [ ] **Step 2: Run test, expect FAIL.**

- [ ] **Step 3: Implement `DiffView.tsx`** — render each `DiffBlob`: a `path` header (`.mono`) + the `patch` with `+`/`-` line coloring.

- [ ] **Step 4: Implement `ReviewPane.tsx`** — on `selectedStepId` change, `await api.getStepDetail(id)`; left pane `DiffView`; right pane shows `createdNodeIds`/`createdEdgeIds` ("지도 조각"), `decision`, and `acceptance` list; bottom 3 buttons calling `api.reviewStep`. "수정요청" toggles a textarea + submit. Empty state when no step selected: "리뷰 대기 중인 step이 없습니다".

- [ ] **Step 5: Run test, expect PASS.**

- [ ] **Step 6: Run the app**, compare against the wireframe review screen (2-pane + 3 actions). Fix.

- [ ] **Step 7: Commit** — `git add web/src/components/review && git commit -m "feat(web): review pane (diff | map-slice + 3 actions)"`

---

## Task 9: Bug Trace (owning-path highlight)

**Files:**
- Create: `web/src/components/bugtrace/BugTrace.tsx`
- Modify: `web/src/components/map/ProjectMap.tsx` (accept `highlightIds` to dim non-path nodes)
- Test: `web/src/components/bugtrace/BugTrace.test.tsx`

**Interfaces:**
- Consumes: `useStore` (api), `owningPath`.
- Produces: `BugTrace` — a search/select input over node labels (files/symbols/UI); choosing one calls `api.owningPath(id)` and sets `highlightIds`; `ProjectMap` dims everything not in `highlightIds` and shows the path `CodeRegion→Step→Ticket→Objective`.

- [ ] **Step 1: Write the failing test**

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BugTrace } from './BugTrace';

test('selecting a file highlights its owning path', async () => {
  const onHighlight = vi.fn();
  render(<BugTrace onHighlight={onHighlight} />);
  await userEvent.type(screen.getByRole('searchbox'), 'FeatureGate');
  await userEvent.click(await screen.findByText('src/billing/FeatureGate.tsx'));
  await waitFor(() => expect(onHighlight).toHaveBeenCalledWith(['c-gate', 's4', 't-gate', 'obj']));
});
```

- [ ] **Step 2: Run test, expect FAIL.**

- [ ] **Step 3: Implement `BugTrace.tsx`** with prop `onHighlight(ids: string[])`; filter graph nodes by query (code_region/test/ui labels), on select call `await api.owningPath(id)` then `onHighlight(path)`.

- [ ] **Step 4: Modify `ProjectMap`** to accept optional `highlightIds?: string[]`; when set, dim nodes/edges not on the path. Wire `BugTrace` into `Shell` (map altitude), passing `onHighlight` → `ProjectMap.highlightIds`.

- [ ] **Step 5: Run test, expect PASS.** Then run the app and verify the highlight + dim against the wireframe bug-trace screen.

- [ ] **Step 6: Commit** — `git add web/src && git commit -m "feat(web): bug-trace owning-path highlight"`

---

## Task 10: Plan Approval + Goal Entry

**Files:**
- Create: `web/src/components/plan/PlanApproval.tsx`, `web/src/components/goal/GoalEntry.tsx`
- Modify: `web/src/components/Shell.tsx` (route goal entry → plan approval)
- Test: `web/src/components/plan/PlanApproval.test.tsx`

**Interfaces:**
- Consumes: `useStore` (api), `proposePlan`, `approvePlan`.
- Produces: `GoalEntry` (textarea + submit → `proposePlan(goal)`), `PlanApproval` (editable step list: add/remove/reorder + 승인 → `approvePlan`). Matches wireframe "새 목표" / "분해 시작" / "승인 후 실행".

- [ ] **Step 1: Write the failing test**

```tsx
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
```

- [ ] **Step 2: Run test, expect FAIL.**

- [ ] **Step 3: Implement `GoalEntry.tsx` and `PlanApproval.tsx`.** PlanApproval: on mount `await api.proposePlan(goal)`, render each step label as an editable input + remove button + add-step; 승인 → `await api.approvePlan(proposal); onApproved()`.

- [ ] **Step 4: Wire into Shell** — a "새 목표" affordance opens `GoalEntry`; submitting shows `PlanApproval`; approve returns to the map.

- [ ] **Step 5: Run test, expect PASS.** Run the app; compare to wireframe goal/plan screens. Fix.

- [ ] **Step 6: Commit** — `git add web/src && git commit -m "feat(web): goal entry + plan approval"`

---

## Task 11: Live wiring + end-to-end smoke

**Files:**
- Modify: `web/src/store/useStore.ts` (optional auto-tick), `web/src/App.tsx`
- Test: `web/src/App.e2e.test.tsx`

**Interfaces:**
- Produces: an integrated app where reviewing a step updates the map/lane **without manual refresh** (store re-loads via `api.subscribe`).

- [ ] **Step 1: Write the failing integration test** — `App.e2e.test.tsx`

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';

test('approving the awaiting step updates state live (no refresh control used)', async () => {
  render(<App />);
  await userEvent.click(await screen.findByText('구독 티어 + 기능 게이팅')); // open lane
  await userEvent.click(await screen.findByText('게이트 컴포넌트'));          // open review
  await userEvent.click(await screen.findByRole('button', { name: '승인' }));
  // lane reflects done without any refresh button
  await waitFor(() => expect(screen.queryByText(/리뷰 대기/)).toBeNull());
  expect(screen.queryByRole('button', { name: /refresh/i })).toBeNull();
});
```

- [ ] **Step 2: Run test, expect FAIL** (or flaky) → fix wiring so the store refreshes on `api.subscribe` and components read from the store.

- [ ] **Step 3: Run the full app** — walk goal → plan approve → map → lane → review → approve; confirm the map/lane update live and the bug-trace highlights a path. Compare each screen to the wireframe.

- [ ] **Step 4: Run all tests** — `cd web && npm run test` → all green. `npm run lint` clean.

- [ ] **Step 5: Commit** — `git add web && git commit -m "feat(web): live wiring + e2e smoke (v1 UI on mock API)"`

---

## Self-Review (done at write time)

- **Spec coverage:** §8 screens ①map(T6) ②lane(T7) ③review(T8) ④bug-trace(T9) + plan-approval/goal(T10); §6 data model(T2,T3); live state / no-plumbing(T4,T5,T11). RAG/LangGraph/backend are **out of scope** for this plan (Plans 2–4).
- **Mock-only:** every screen binds to `ApiClient`; real API swaps later (Plan 3). ✔
- **Type consistency:** `ProjectGraph`/`GraphNode`/`Status`/`EdgeKind` defined in T2 and reused verbatim in T3–T11; `ApiClient` signatures defined in T3 are the ones consumed in T6–T11. ✔ (Fix noted in T3 Step 2: fixture edge `e12` uses a valid `EdgeKind` `'tested_by'`, not the placeholder.)

## Notes / Open Items for later plans

- The real diff→graph extraction, LangGraph lifecycle, headless executor, and RAG memory are Plans 2–4; this plan deliberately simulates them in `MockApiClient` so the UI is buildable now.
- Wireframe filename: `docs/design/wireframes/llm-dev-control-tower.html` (single bundled mockup). Open in a browser as the visual reference per task.
