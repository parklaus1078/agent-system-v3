import type { ApiClient } from '../ApiClient';
import type { ProjectGraph } from '../../domain/graph';
import type { StepDetail, ReviewAction, PlanProposal } from '../dto';

/** ApiClient over the backend REST endpoints. Read paths are live; the write
 *  paths (propose/approve/review) and SSE land in Plan 3 — until then the app
 *  keeps using MockApiClient for those. */
export class HttpApiClient implements ApiClient {
  constructor(
    private base: string,
    private pid: string,
  ) {}

  private async j<T>(path: string): Promise<T> {
    const r = await fetch(`${this.base}/projects/${this.pid}${path}`);
    if (!r.ok) throw new Error(`${r.status} ${path}`);
    return r.json() as Promise<T>;
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
  proposePlan(_goal: string): Promise<PlanProposal> {
    throw new Error('NotImplemented until Plan 3');
  }
  approvePlan(_proposal: PlanProposal): Promise<void> {
    throw new Error('NotImplemented until Plan 3');
  }
  reviewStep(_id: string, _action: ReviewAction): Promise<void> {
    throw new Error('NotImplemented until Plan 3');
  }
  subscribe(cb: () => void): () => void {
    const t = setInterval(cb, 1500); // light polling until SSE (Plan 3)
    return () => clearInterval(t);
  }
}
