import type { ProjectGraph, GraphNode } from '../../domain/graph';
import { neighbors } from '../../domain/graph';
import type { ApiClient } from '../ApiClient';
import type {
  StepDetail,
  ReviewAction,
  PlanProposal,
  ProjectInfo,
  ProjectSummary,
  ProjectProposal,
  ProjectCreated,
  ProjectMeta,
  ProjectDeleted,
  Rules,
  ProjectRules,
  GlobalModels,
  ProjectModels,
  ModelsMap,
  EngineSpec,
  ModelAvailability,
  AutonomyLevel,
  ProjectAutonomy,
  TicketAutonomy,
  ChannelMessage,
  MessageType,
  SteerResult,
} from '../dto';

/** Minimal in-browser intent classifier mirroring the backend SimulatedIntentRouter, so the
 *  mock demonstrates the full steer -> op -> channel flow with no server. */
function classifyMock(text: string, ctx: { hasBlocked: boolean }): string {
  const t = text.toLowerCase().trim();
  if (!t) return 'clarify';
  if (/(auto|자동|오토|co-pilot|copilot|부조종|per-step|perstep|매 step|매 스텝)/.test(t)) return 'control';
  if (/(pause|멈춰|정지|일시정지|resume|재개|continue|이어서)/.test(t)) return 'control';
  if (/(don't touch|dont touch|do not touch|hands off|pin |건드리지|손대지|건들지|고정|constrain)/.test(t))
    return 'constrain';
  if (/(먼저|우선순위|우선|priority|prioritize|reprioritize)/.test(t)) return 'reprioritize';
  if (/(추가|add |새 티켓|새 일감|도 만들|also add|scope)/.test(t)) return 'scope';
  if (/(use |switch to|instead|대신|바꿔|로 해|써|쓰자|redirect|재계획)/.test(t) || t.endsWith('로'))
    return 'redirect';
  // a clear question -> `ask` (answer it) even mid-block; a plain non-question reply below answers.
  // \p{L}/u so a Korean-only question counts as content (bare "???" does not).
  if (/[\p{L}\p{N}]/u.test(t) && (/[?？]$/.test(t) || /(뭐|무엇|어때|어떻|어떤|왜|언제|어디|누가|알려|설명|상태|현황|진행|몇|있어|있나|까요|나요|what|why|how|status|explain|tell me)/.test(t)))
    return 'ask';
  if (ctx.hasBlocked) return 'answer';
  return 'clarify';
}

const GOV_POINTS = [
  'project-planner',
  'ticket-planner',
  'executor',
  'intent-router',
  'agent-message-gen',
];
const GOV_TRANSPORTS = ['claude-cli', 'codex-cli', 'anthropic-api', 'openai-api', 'local', 'simulated'];
// Which transports each point can actually run on — mirrors the backend governance.SUPPORTED
// (codex-cli is executor-only; openai-api/local are stubs not wired anywhere this CP).
// completion points run on ANY transport; the executor stays CLI/simulated (mirrors backend SUPPORTED)
const GOV_COMPLETION_ALL = ['claude-cli', 'codex-cli', 'anthropic-api', 'openai-api', 'local', 'simulated'];
const GOV_SUPPORTED: Record<string, string[]> = {
  'project-planner': GOV_COMPLETION_ALL,
  'ticket-planner': GOV_COMPLETION_ALL,
  executor: ['claude-cli', 'codex-cli', 'simulated'],
  'intent-router': GOV_COMPLETION_ALL,
  'agent-message-gen': GOV_COMPLETION_ALL,
};
import { makeFixture } from './fixtures';

function slugify(text: string): string {
  return (
    text
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '')
      .slice(0, 40)
      .replace(/^-+|-+$/g, '') || 'project'
  );
}

export class MockApiClient implements ApiClient {
  private graph: ProjectGraph = makeFixture();
  private subs = new Set<() => void>();
  private repoOverride: string | null = null; // null -> workspace default
  // Projects created via approveProject — surfaced in listProjects so the landing list
  // updates (the mock keeps a single fixture graph, so their maps show the fixture).
  private extraProjects: ProjectSummary[] = [];
  // CP0 governance (in-memory; mirrors the backend's global-default + project-override model).
  private globalRules: Rules = {
    coding: '# General Coding Principles\n- DRY (Don’t Repeat Yourself)\n- KISS\n- YAGNI\n- SOLID',
    planning: '',
  };
  private projectRules: Rules = { coding: '', planning: '' };
  private globalModels: ModelsMap = {};
  private projectModels: ModelsMap = {};
  private projectAutonomy: AutonomyLevel | null = null; // null -> inherit global
  private globalAutonomy: AutonomyLevel = 'per-step';
  private ticketAutonomy: Record<string, AutonomyLevel | null> = {}; // CP4 per-ticket override
  private messages: ChannelMessage[] = []; // CP2 channel (append-only)
  private msgSeq = 0;

  private notify() {
    this.subs.forEach((cb) => cb());
  }

  subscribe(cb: () => void) {
    this.subs.add(cb);
    return () => {
      this.subs.delete(cb);
    };
  }

  async getGraph(): Promise<ProjectGraph> {
    return structuredClone(this.graph);
  }

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

  async proposePlan(
    target: { goal: string; ticketId?: string } | { ticketId: string },
  ): Promise<PlanProposal> {
    if (!('goal' in target)) {
      const ticket = this.graph.nodes.find((n) => n.id === target.ticketId);
      const existing = neighbors(this.graph, target.ticketId, 'out')
        .filter((n) => n.kind === 'step')
        .map((s) => ({ label: s.label, intent: '', acceptance: '' }));
      return {
        ticketId: target.ticketId,
        title: ticket?.label,
        steps: existing.length
          ? existing
          : [
              { label: '스펙·골격', intent: '스펙 정리', acceptance: '스펙 합의' },
              { label: '구현', intent: '핵심 구현', acceptance: '동작' },
              { label: '테스트', intent: '테스트 추가', acceptance: '그린' },
            ],
      };
    }
    const goal = target.goal;
    return {
      ticketId: ('ticketId' in target && target.ticketId) || 't-new',
      title: goal,
      steps: [
        { label: '스펙·골격', intent: `${goal} 스펙 정리`, acceptance: '스펙 합의' },
        { label: '구현', intent: '핵심 구현', acceptance: '동작' },
        { label: '테스트', intent: '테스트 추가', acceptance: '그린' },
      ],
    };
  }

  async approvePlan(p: PlanProposal): Promise<void> {
    let ticket = this.graph.nodes.find((n) => n.id === p.ticketId);
    if (!ticket) {
      // new goal: create the ticket under the objective
      ticket = { id: p.ticketId, kind: 'ticket', label: p.title ?? p.ticketId, status: 'executing', data: {} };
      this.graph.nodes.push(ticket);
      const obj = this.graph.nodes.find((n) => n.kind === 'objective');
      if (obj) {
        this.graph.edges.push({ id: `has:${obj.id}:${p.ticketId}`, from: obj.id, to: p.ticketId, kind: 'has' });
      }
    }
    if (p.title) ticket.label = p.title;

    // replace the ticket's step children with the approved (edited) steps
    const oldIds = new Set(
      neighbors(this.graph, p.ticketId, 'out')
        .filter((n) => n.kind === 'step')
        .map((s) => s.id),
    );
    this.graph.nodes = this.graph.nodes.filter((n) => !oldIds.has(n.id));
    this.graph.edges = this.graph.edges.filter((e) => !oldIds.has(e.from) && !oldIds.has(e.to));
    p.steps.forEach((s, i) => {
      const sid = `${p.ticketId}-s${i + 1}`;
      // step 1 starts executing immediately; the rest stay queued
      this.graph.nodes.push({ id: sid, kind: 'step', label: s.label, status: i === 0 ? 'executing' : 'planning' });
      this.graph.edges.push({ id: `has:${sid}`, from: p.ticketId, to: sid, kind: 'has' });
    });

    ticket.status = 'executing';
    this.notify();
    // start step 1: the simulated executor finishes it and stops at the review gate
    if (p.steps.length) this.gateLater(`${p.ticketId}-s1`);
  }

  async reviewStep(stepId: string, action: ReviewAction): Promise<void> {
    const node = this.graph.nodes.find((n) => n.id === stepId);
    if (!node) return;
    if (action.kind === 'approve') {
      node.status = 'done';
      const next = this.nextPlanningStep(stepId);
      if (next) {
        next.status = 'executing'; // the agent picks up the next step (in progress)…
        this.gateLater(next.id); // …then finishes and stops at its own review gate
      } else {
        const ticket = this.ticketOf(stepId);
        if (ticket) ticket.status = 'done'; // last step approved -> ticket complete
      }
    } else if (action.kind === 'changes') {
      node.status = 'executing'; // re-run the same step
      this.gateLater(stepId);
    } else {
      node.status = 'awaiting_review';
    }
    this.notify();
  }

  private ticketOf(stepId: string): GraphNode | undefined {
    return neighbors(this.graph, stepId, 'in').find((n) => n.kind === 'ticket');
  }

  private nextPlanningStep(stepId: string): GraphNode | undefined {
    const ticket = this.ticketOf(stepId);
    if (!ticket) return undefined;
    const steps = neighbors(this.graph, ticket.id, 'out').filter((n) => n.kind === 'step');
    const i = steps.findIndex((s) => s.id === stepId);
    return steps.slice(i + 1).find((s) => s.status === 'planning');
  }

  /** Simulate the executor: after a beat the running step stops at its review gate,
   *  having touched a code region (so it has a reviewable diff) — mirrors the real
   *  backend lifecycle so the mock UI demonstrates plan -> execute -> review fully. */
  private gateLater(stepId: string): void {
    setTimeout(() => {
      const step = this.graph.nodes.find((n) => n.id === stepId);
      if (!step || step.status !== 'executing') return; // user moved on; don't clobber
      step.status = 'awaiting_review';
      const crId = `cr:mock:${stepId}`;
      if (!this.graph.nodes.some((n) => n.id === crId)) {
        this.graph.nodes.push({ id: crId, kind: 'code_region', label: `src/generated/${stepId}.ts` });
        this.graph.edges.push({ id: `touch:${stepId}`, from: stepId, to: crId, kind: 'touches' });
      }
      // CP2: a gated step surfaces a `review` message in the channel (mirrors the backend).
      this.postMsg('review', `'${step.label}' 리뷰 대기 — 승인 / 수정요청 / 인수 중 선택하세요.`, [stepId]);
      this.notify();
    }, 900);
  }

  private postMsg(
    type: MessageType,
    text: string,
    refs: string[] = [],
    author: ChannelMessage['author'] = 'agent',
  ): void {
    this.messages.push({ id: ++this.msgSeq, type, author, text, refs, ts: new Date().toISOString() });
  }

  async getMessages(since?: number): Promise<ChannelMessage[]> {
    const rows = since != null ? this.messages.filter((m) => m.id > since) : this.messages;
    return rows.map((m) => ({ ...m }));
  }

  async steer(text: string, scope?: { ticketId?: string; stepId?: string }): Promise<SteerResult> {
    this.postMsg('steer', text, [], 'user'); // record the instruction
    const hasBlocked = this.graph.nodes.some((n) => n.status === 'blocked');
    const op = classifyMock(text, { hasBlocked });
    let result: Record<string, unknown> = {};
    if (op === 'clarify') {
      this.postMsg('clarify', "무엇을 원하는지 모르겠어요 — 예: 'use Stripe', 'auth 건드리지 마', 'pause'.", [], 'system');
    } else if (op === 'control') {
      const t = text.toLowerCase();
      const level: AutonomyLevel = /per-step|perstep|매 step|매 스텝|pause|멈춰|정지/.test(t)
        ? 'per-step'
        : /co-pilot|copilot|부조종/.test(t)
          ? 'co-pilot'
          : 'auto';
      this.projectAutonomy = level;
      this.postMsg('system', `control → 자율도 ${level}`, [], 'system');
      result = { autonomy: level };
    } else if (op === 'constrain') {
      const cid = `constraint:mock:${++this.msgSeq}`;
      this.graph.nodes.push({ id: cid, kind: 'decision', label: text });
      if (scope?.ticketId && this.graph.nodes.some((n) => n.id === scope.ticketId)) {
        this.graph.edges.push({ id: `constrains:${cid}`, from: scope.ticketId, to: cid, kind: 'decided' });
      }
      this.postMsg('decision', `제약 고정: ${text}`, [cid], 'system');
      result = { nodeId: cid };
    } else if (op === 'redirect') {
      this.postMsg('system', `redirect → 재계획: ${text}`, scope?.ticketId ? [scope.ticketId] : [], 'system');
      result = { ticketId: scope?.ticketId };
    } else if (op === 'reprioritize') {
      this.postMsg('system', `reprioritize → 우선순위 조정: ${text}`, [], 'system');
    } else if (op === 'scope') {
      const tid = `t-scope-${++this.msgSeq}`;
      const title = text.replace(/도?\s*추가.*$/, '').replace(/(add |also add|scope)/gi, '').trim() || '새 일감';
      this.graph.nodes.push({ id: tid, kind: 'ticket', label: title, status: 'planning' });
      const obj = this.graph.nodes.find((n) => n.kind === 'objective');
      if (obj) this.graph.edges.push({ id: `has:${tid}`, from: obj.id, to: tid, kind: 'has' });
      this.postMsg('system', `scope → 새 티켓 '${title}' 생성`, [tid], 'system');
      result = { ticketId: tid };
    } else if (op === 'answer') {
      const blocked =
        (scope?.stepId && this.graph.nodes.find((n) => n.id === scope.stepId && n.status === 'blocked')) ||
        this.graph.nodes.find((n) => n.status === 'blocked');
      if (blocked) blocked.status = 'awaiting_review';
      this.postMsg('system', '답변 반영 → 막힌 step 재개', blocked ? [blocked.id] : [], 'system');
      result = { stepId: blocked?.id };
    } else if (op === 'ask') {
      // conversational Q&A — a deterministic project-status answer (the real backend uses an LLM)
      const obj = this.graph.nodes.find((n) => n.kind === 'objective');
      const tickets = this.graph.nodes.filter((n) => n.kind === 'ticket');
      const steps = this.graph.nodes.filter((n) => n.kind === 'step');
      const awaiting = steps.filter((s) => s.status === 'awaiting_review').length;
      const ans = `${obj ? `'${obj.label}' — ` : ''}티켓 ${tickets.length}개, step ${steps.length}개${
        awaiting ? `, 리뷰 대기 ${awaiting}개` : ''
      }. (mock 요약 — 실제 대화형 답변은 백엔드 LLM이 제공)`;
      this.postMsg('system', ans, [], 'agent');
      result = { answer: ans };
    }
    this.notify();
    return { op, scope: { ticket: scope?.ticketId, step: scope?.stepId }, result };
  }

  setPid(_pid: string): void {
    /* single in-memory fixture (project p1); nothing to switch */
  }

  async listProjects(): Promise<ProjectSummary[]> {
    const obj = this.graph.nodes.find((n) => n.kind === 'objective');
    const tickets = this.graph.nodes.filter((n) => n.kind === 'ticket');
    const steps = this.graph.nodes.filter((n) => n.kind === 'step');
    const base: ProjectSummary[] = obj
      ? [
          {
            projectId: 'p1',
            title: obj.label,
            description: (obj.data?.description as string) ?? null,
            tickets: tickets.length,
            steps: steps.length,
            awaiting: steps.filter((s) => s.status === 'awaiting_review').length,
          },
        ]
      : [];
    return [...base, ...this.extraProjects];
  }

  async proposeProject(goal: string): Promise<ProjectProposal> {
    const title = goal.trim().split('\n')[0].slice(0, 60) || '새 프로젝트';
    return {
      slug: slugify(title),
      title,
      tickets: [
        { title: '핵심 기능 구현', intent: `${title} 핵심 동작` },
        { title: '데이터·저장', intent: '영속/스토리지 계층' },
        { title: '테스트·검증', intent: '테스트 추가 및 수용 기준 확인' },
      ],
    };
  }

  async deleteProject(projectId: string, deleteDirectory: boolean): Promise<ProjectDeleted> {
    const extra = this.extraProjects.find((x) => x.projectId === projectId);
    let counts = { nodes: 0, edges: 0, messages: 0 };
    if (projectId === 'p1') {
      // the base fixture project — wipe its graph so listProjects drops it
      counts = { nodes: this.graph.nodes.length, edges: this.graph.edges.length, messages: this.messages.length };
      this.graph = { nodes: [], edges: [] };
      this.messages = [];
    } else if (extra) {
      counts = { nodes: extra.tickets + extra.steps + 1, edges: extra.tickets, messages: 0 };
      this.extraProjects = this.extraProjects.filter((x) => x.projectId !== projectId);
    }
    this.notify();
    return { projectId, ...counts, directoryRemoved: deleteDirectory };
  }

  async approveProject(p: ProjectProposal): Promise<ProjectCreated> {
    const slug = slugify(p.slug || p.title);
    const existing = this.extraProjects.find((x) => x.projectId === slug);
    if (existing) return { projectId: slug, title: existing.title, tickets: existing.tickets, created: false };
    this.extraProjects.push({
      projectId: slug,
      title: p.title || slug,
      description: p.description ?? null,
      tickets: p.tickets.length,
      steps: 0,
      awaiting: 0,
    });
    this.notify();
    return { projectId: slug, title: p.title || slug, tickets: p.tickets.length, created: true };
  }

  async getProjectInfo(): Promise<ProjectInfo> {
    return this.repoOverride
      ? { projectId: 'p1', repoDir: this.repoOverride, repoSource: 'override' }
      : { projectId: 'p1', repoDir: '/tmp/asv3-workspace/p1', repoSource: 'workspace' };
  }

  async setProjectRepo(repoDir: string | null): Promise<ProjectInfo> {
    this.repoOverride = repoDir && repoDir.trim() ? repoDir.trim() : null;
    this.notify();
    return this.getProjectInfo();
  }

  async setProjectMeta(meta: { title?: string; description?: string }): Promise<ProjectMeta> {
    const obj = this.graph.nodes.find((n) => n.kind === 'objective');
    if (obj) {
      if (meta.title && meta.title.trim()) obj.label = meta.title.trim();
      if (meta.description !== undefined) {
        const d = meta.description.trim();
        obj.data = { ...(obj.data || {}), description: d || undefined };
      }
    }
    this.notify();
    return {
      projectId: 'p1',
      title: obj?.label ?? 'p1',
      description: (obj?.data?.description as string | undefined) ?? null,
    };
  }

  async saveLayout(positions: Record<string, { x: number; y: number }>): Promise<void> {
    for (const [id, p] of Object.entries(positions)) {
      const n = this.graph.nodes.find((node) => node.id === id);
      if (n) n.data = { ...(n.data || {}), pos: { x: p.x, y: p.y } };
    }
    this.notify();
  }

  // ── CP0 governance (mirrors the backend resolver: global default + project override) ──
  private mergeRule(g: string, p: string): string {
    const gg = (g || '').trim();
    const pp = (p || '').trim();
    if (gg && pp) return `${gg}\n\n# Project-specific rules\n${pp}`;
    return gg || pp;
  }
  private resolveEngine(point: string): EngineSpec {
    const supported = GOV_SUPPORTED[point] ?? [];
    // project override > global > simulated default; a tier whose transport isn't supported
    // for this point is skipped (mirrors the backend _resolve_one fall-through).
    const pick = [this.projectModels[point], this.globalModels[point]].find(
      (c) => c && supported.includes(c.transport),
    );
    if (!pick) return { transport: 'simulated', model: '' }; // mock = simulated env default
    const model = pick.model || (pick.transport === 'simulated' ? '' : 'claude-opus-4-8');
    return { transport: pick.transport, model };
  }
  private cleanModels(models: ModelsMap): ModelsMap {
    const out: ModelsMap = {};
    for (const [point, spec] of Object.entries(models || {})) {
      if (GOV_POINTS.includes(point) && spec && GOV_TRANSPORTS.includes(spec.transport)) {
        out[point] = { transport: spec.transport, model: String(spec.model || '') };
      }
    }
    return out;
  }

  async getGlobalRules(): Promise<Rules> {
    return { ...this.globalRules };
  }
  async setGlobalRules(rules: Partial<Rules>): Promise<Rules> {
    if (rules.coding !== undefined) this.globalRules.coding = rules.coding;
    if (rules.planning !== undefined) this.globalRules.planning = rules.planning;
    return { ...this.globalRules };
  }
  async getProjectRules(): Promise<ProjectRules> {
    return {
      project: { ...this.projectRules },
      global: { ...this.globalRules },
      resolved: {
        coding: this.mergeRule(this.globalRules.coding, this.projectRules.coding),
        planning: this.mergeRule(this.globalRules.planning, this.projectRules.planning),
      },
    };
  }
  async setProjectRules(rules: Partial<Rules>): Promise<ProjectRules> {
    if (rules.coding !== undefined) this.projectRules.coding = rules.coding;
    if (rules.planning !== undefined) this.projectRules.planning = rules.planning;
    return this.getProjectRules();
  }
  async getGlobalModels(): Promise<GlobalModels> {
    return {
      points: [...GOV_POINTS],
      transports: [...GOV_TRANSPORTS],
      supported: { ...GOV_SUPPORTED },
      global: { ...this.globalModels },
    };
  }
  async setGlobalModels(models: ModelsMap): Promise<GlobalModels> {
    this.globalModels = this.cleanModels(models);
    return this.getGlobalModels();
  }
  async getProjectModels(): Promise<ProjectModels> {
    const resolved: ModelsMap = {};
    for (const p of GOV_POINTS) resolved[p] = this.resolveEngine(p);
    return {
      points: [...GOV_POINTS],
      transports: [...GOV_TRANSPORTS],
      supported: { ...GOV_SUPPORTED },
      project: { ...this.projectModels },
      global: { ...this.globalModels },
      resolved,
    };
  }
  async setProjectModels(models: ModelsMap): Promise<ProjectModels> {
    this.projectModels = this.cleanModels(models);
    return this.getProjectModels();
  }
  async getProjectAutonomy(): Promise<ProjectAutonomy> {
    return {
      levels: ['auto', 'co-pilot', 'per-step'],
      project: this.projectAutonomy,
      global: this.globalAutonomy,
      resolved: this.projectAutonomy ?? this.globalAutonomy,
    };
  }
  async setProjectAutonomy(level: AutonomyLevel | null): Promise<ProjectAutonomy> {
    const valid: AutonomyLevel[] = ['auto', 'co-pilot', 'per-step'];
    this.projectAutonomy = level && valid.includes(level) ? level : null;
    this.notify();
    return this.getProjectAutonomy();
  }
  async getTicketAutonomy(ticketId: string): Promise<TicketAutonomy> {
    const ticket = this.ticketAutonomy[ticketId] ?? null;
    return {
      levels: ['auto', 'co-pilot', 'per-step'],
      ticket,
      project: this.projectAutonomy,
      global: this.globalAutonomy,
      resolved: ticket ?? this.projectAutonomy ?? this.globalAutonomy, // ticket > project > global
    };
  }
  async setTicketAutonomy(ticketId: string, level: AutonomyLevel | null): Promise<TicketAutonomy> {
    const valid: AutonomyLevel[] = ['auto', 'co-pilot', 'per-step'];
    this.ticketAutonomy[ticketId] = level && valid.includes(level) ? level : null;
    this.notify();
    return this.getTicketAutonomy(ticketId);
  }

  async getModelAvailability(): Promise<ModelAvailability[]> {
    return [
      { transport: 'simulated', wired: true, available: true, detail: 'deterministic offline stub' },
      { transport: 'claude-cli', wired: true, available: true, detail: '`claude` on PATH (mock)' },
      { transport: 'codex-cli', wired: true, available: false, detail: '`codex` not found (mock)' },
      { transport: 'anthropic-api', wired: true, available: false, detail: 'ANTHROPIC_API_KEY not set (mock)' },
      { transport: 'openai-api', wired: true, available: false, detail: 'OPENAI_API_KEY not set (mock)' },
      { transport: 'local', wired: true, available: false, detail: 'set ASV3_LOCAL_BASE_URL (mock)' },
    ];
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
