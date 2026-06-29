import type { ApiClient } from '../ApiClient';
import type { ProjectGraph } from '../../domain/graph';
import type { StepDetail, ReviewAction, PlanProposal } from '../dto';

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

  async proposePlan(goal: string): Promise<PlanProposal> {
    return this.post('/plan/propose', { goal });
  }
  async approvePlan(proposal: PlanProposal): Promise<void> {
    await this.post('/plan/approve', proposal);
    this.notify();
  }
  async reviewStep(id: string, action: ReviewAction): Promise<void> {
    await this.post(`/steps/${id}/review`, action);
    this.notify();
  }

  subscribe(cb: () => void): () => void {
    this.subs.add(cb);
    const t = setInterval(cb, 1500); // light polling until SSE (Plan 3)
    return () => {
      this.subs.delete(cb);
      clearInterval(t);
    };
  }
}
