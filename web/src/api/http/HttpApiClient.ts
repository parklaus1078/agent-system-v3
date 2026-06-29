import type { ApiClient } from '../ApiClient';
import type { ProjectGraph } from '../../domain/graph';
import type { StepDetail, ReviewAction, PlanProposal } from '../dto';

/** The lifecycle-state envelope returned by the plan/approve/review endpoints. */
interface LifecycleState {
  ticketId: string;
  next: string[];
  done: boolean;
  current: number | null;
  steps: PlanProposal['steps'];
  awaiting: { type: string; steps?: PlanProposal['steps']; step?: number } | null;
}

/** ApiClient over the backend REST endpoints. Reads are live (polled);
 *  writes POST and then immediately notify subscribers so the UI re-loads. */
export class HttpApiClient implements ApiClient {
  private subs = new Set<() => void>();

  constructor(
    private base: string,
    private pid: string,
  ) {}

  private url(path: string): string {
    return `${this.base}/projects/${this.pid}${path}`;
  }

  private async j<T>(path: string): Promise<T> {
    const r = await fetch(this.url(path));
    if (!r.ok) throw new Error(`${r.status} ${path}`);
    return r.json() as Promise<T>;
  }

  private async post<T>(path: string, body: unknown): Promise<T> {
    const r = await fetch(this.url(path), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`${r.status} ${path}`);
    return r.json() as Promise<T>;
  }

  private notify() {
    this.subs.forEach((cb) => cb());
  }

  getGraph(): Promise<ProjectGraph> {
    return this.j('/graph');
  }
  getStepDetail(id: string): Promise<StepDetail> {
    return this.j(`/steps/${id}`);
  }
  async owningPath(id: string): Promise<string[]> {
    return (await this.j<{ path: string[] }>(`/owning-path/${id}`)).path;
  }

  async proposePlan(target: { goal: string } | { ticketId: string }): Promise<PlanProposal> {
    // existing ticket -> (re)plan it; new goal -> mint a ticket id and create it.
    const ticketId = 'ticketId' in target ? target.ticketId : `t-${Date.now().toString(36)}`;
    const title = 'goal' in target ? target.goal : undefined;
    const state = await this.post<LifecycleState>(`/tickets/${ticketId}/plan`, { title });
    return { ticketId, steps: state.awaiting?.steps ?? [], title };
  }
  async approvePlan(proposal: PlanProposal): Promise<void> {
    await this.post(`/tickets/${proposal.ticketId}/plan/approve`, {
      steps: proposal.steps,
      title: proposal.title,
    });
    this.notify();
  }
  async reviewStep(id: string, action: ReviewAction): Promise<void> {
    const body =
      action.kind === 'changes' ? { kind: 'changes', comment: action.comment } : { kind: action.kind };
    await this.post(`/steps/${id}/review`, body);
    this.notify();
  }

  subscribe(cb: () => void): () => void {
    this.subs.add(cb);
    // Light polling until SSE (Plan 3). Skip ticks while the tab is hidden to avoid
    // pointless background fetches; refresh once on return to visibility.
    const tick = () => {
      if (typeof document === 'undefined' || document.visibilityState === 'visible') cb();
    };
    const t = setInterval(tick, 1500);
    const onVisible = () => {
      if (document.visibilityState === 'visible') cb();
    };
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', onVisible);
    }
    return () => {
      this.subs.delete(cb);
      clearInterval(t);
      if (typeof document !== 'undefined') {
        document.removeEventListener('visibilitychange', onVisible);
      }
    };
  }
}
