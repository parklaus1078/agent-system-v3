import type { ProjectGraph, GraphNode } from '../../domain/graph';
import { neighbors } from '../../domain/graph';
import type { ApiClient } from '../ApiClient';
import type { StepDetail, ReviewAction, PlanProposal, ProjectInfo } from '../dto';
import { makeFixture } from './fixtures';

export class MockApiClient implements ApiClient {
  private graph: ProjectGraph = makeFixture();
  private subs = new Set<() => void>();
  private repoOverride: string | null = null; // null -> workspace default

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

  async proposePlan(target: { goal: string } | { ticketId: string }): Promise<PlanProposal> {
    if ('ticketId' in target) {
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
      ticketId: 't-new',
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
      this.notify();
    }, 900);
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
