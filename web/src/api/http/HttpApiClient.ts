import type { ApiClient } from '../ApiClient';
import type { ProjectGraph } from '../../domain/graph';
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
  ModelAvailability,
  AutonomyLevel,
  ProjectAutonomy,
  TicketAutonomy,
  ChannelMessage,
  SteerResult,
} from '../dto';

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
  // Conditional-GET cache for /graph: send If-None-Match and reuse the last graph on a 304,
  // so idle 1.5s polls transfer (and on the server, read) nothing when state is unchanged.
  private graphEtag: string | null = null;
  private lastGraph: ProjectGraph | null = null;

  constructor(
    private base: string,
    private pid: string,
  ) {}

  setPid(pid: string): void {
    this.pid = pid;
    this.graphEtag = null; // drop the previous project's cached graph/etag
    this.lastGraph = null;
  }

  async listProjects(): Promise<ProjectSummary[]> {
    const r = await fetch(`${this.base}/projects`);
    if (!r.ok) throw new Error(`${r.status} /projects`);
    return r.json() as Promise<ProjectSummary[]>;
  }

  // Project-level planning is NOT pid-scoped (it creates the project), so it posts to the
  // bare /projects/* endpoints rather than url()'s /projects/{pid}/* prefix.
  async proposeProject(goal: string): Promise<ProjectProposal> {
    const r = await fetch(`${this.base}/projects/plan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ goal }),
    });
    if (!r.ok) throw new Error(`${r.status} /projects/plan`);
    return r.json() as Promise<ProjectProposal>;
  }
  async approveProject(proposal: ProjectProposal): Promise<ProjectCreated> {
    const r = await fetch(`${this.base}/projects/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(proposal),
    });
    if (!r.ok) throw new Error(`${r.status} /projects/approve`);
    const created = (await r.json()) as ProjectCreated;
    this.notify(); // a new project appears in the landing list
    return created;
  }
  // NOT pid-scoped — deletes an arbitrary project by id (from the landing list).
  async deleteProject(projectId: string, deleteDirectory: boolean): Promise<ProjectDeleted> {
    const r = await fetch(
      `${this.base}/projects/${projectId}?delete_directory=${deleteDirectory ? 'true' : 'false'}`,
      { method: 'DELETE' },
    );
    if (!r.ok) throw new Error(`${r.status} DELETE /projects/${projectId}`);
    const out = (await r.json()) as ProjectDeleted;
    this.notify(); // the project disappears from the landing list
    return out;
  }

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

  private async put<T>(path: string, body: unknown): Promise<T> {
    const r = await fetch(this.url(path), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`${r.status} PUT ${path}`);
    return r.json() as Promise<T>;
  }

  // Governance global config is NOT pid-scoped (it's the default profile), so it hits the
  // bare /rules and /models endpoints rather than url()'s /projects/{pid}/* prefix.
  private async topGet<T>(path: string): Promise<T> {
    const r = await fetch(`${this.base}${path}`);
    if (!r.ok) throw new Error(`${r.status} ${path}`);
    return r.json() as Promise<T>;
  }
  private async topPut<T>(path: string, body: unknown): Promise<T> {
    const r = await fetch(`${this.base}${path}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`${r.status} PUT ${path}`);
    return r.json() as Promise<T>;
  }

  private notify() {
    this.subs.forEach((cb) => cb());
  }

  async getGraph(): Promise<ProjectGraph> {
    const r = await fetch(this.url('/graph'), {
      headers: this.graphEtag ? { 'If-None-Match': this.graphEtag } : {},
    });
    if (r.status === 304 && this.lastGraph) return this.lastGraph; // unchanged: reuse cached
    if (!r.ok) throw new Error(`${r.status} /graph`); // preserve offline-indicator behavior
    this.graphEtag = r.headers.get('ETag');
    this.lastGraph = (await r.json()) as ProjectGraph;
    return this.lastGraph;
  }
  getStepDetail(id: string): Promise<StepDetail> {
    return this.j(`/steps/${id}`);
  }
  async owningPath(id: string): Promise<string[]> {
    return (await this.j<{ path: string[] }>(`/owning-path/${id}`)).path;
  }
  async saveLayout(positions: Record<string, { x: number; y: number }>): Promise<void> {
    await this.post('/layout', { positions });
    this.notify(); // the new positions come back on the next /graph poll
  }
  getProjectInfo(): Promise<ProjectInfo> {
    return this.j('/info');
  }
  async setProjectRepo(repoDir: string | null): Promise<ProjectInfo> {
    const info = await this.post<ProjectInfo>('/repo', { repoDir });
    this.notify();
    return info;
  }

  async proposePlan(
    target: { goal: string; ticketId?: string } | { ticketId: string },
  ): Promise<PlanProposal> {
    // existing ticket -> (re)plan it; new goal -> reuse the caller-supplied stable id (so
    // re-opening the modal hits the SAME /plan thread instead of minting duplicate tickets),
    // falling back to a fresh id only if none was provided.
    const ticketId =
      'ticketId' in target && target.ticketId ? target.ticketId : `t-${Date.now().toString(36)}`;
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
  async setProjectMeta(meta: { title?: string; description?: string }): Promise<ProjectMeta> {
    const out = await this.post<ProjectMeta>('/meta', meta); // pid-scoped (/projects/{pid}/meta)
    this.notify();
    return out;
  }
  async reviewStep(id: string, action: ReviewAction): Promise<void> {
    const body =
      action.kind === 'changes' ? { kind: 'changes', comment: action.comment } : { kind: action.kind };
    await this.post(`/steps/${id}/review`, body);
    this.notify();
  }

  // ── CP0 governance ──
  getGlobalRules(): Promise<Rules> {
    return this.topGet('/rules');
  }
  setGlobalRules(rules: Partial<Rules>): Promise<Rules> {
    return this.topPut('/rules', rules);
  }
  getProjectRules(): Promise<ProjectRules> {
    return this.j('/rules'); // pid-scoped (/projects/{pid}/rules)
  }
  setProjectRules(rules: Partial<Rules>): Promise<ProjectRules> {
    return this.put('/rules', rules);
  }
  getGlobalModels(): Promise<GlobalModels> {
    return this.topGet('/models');
  }
  setGlobalModels(models: ModelsMap): Promise<GlobalModels> {
    return this.topPut('/models', { models });
  }
  getProjectModels(): Promise<ProjectModels> {
    return this.j('/models'); // pid-scoped (/projects/{pid}/models)
  }
  setProjectModels(models: ModelsMap): Promise<ProjectModels> {
    return this.put('/models', { models });
  }
  getModelAvailability(): Promise<ModelAvailability[]> {
    return this.topGet('/models/available');
  }
  getProjectAutonomy(): Promise<ProjectAutonomy> {
    return this.j('/autonomy'); // pid-scoped (/projects/{pid}/autonomy)
  }
  async setProjectAutonomy(level: AutonomyLevel | null): Promise<ProjectAutonomy> {
    const out = await this.put<ProjectAutonomy>('/autonomy', { level });
    this.notify();
    return out;
  }
  getTicketAutonomy(ticketId: string): Promise<TicketAutonomy> {
    return this.j(`/tickets/${ticketId}/autonomy`); // pid-scoped
  }
  async setTicketAutonomy(ticketId: string, level: AutonomyLevel | null): Promise<TicketAutonomy> {
    const out = await this.put<TicketAutonomy>(`/tickets/${ticketId}/autonomy`, { level });
    this.notify();
    return out;
  }
  getMessages(since?: number): Promise<ChannelMessage[]> {
    return this.j(since != null ? `/messages?since=${since}` : '/messages'); // pid-scoped
  }
  async steer(text: string, scope?: { ticketId?: string; stepId?: string }): Promise<SteerResult> {
    const out = await this.post<SteerResult>('/steer', {
      text,
      ticketId: scope?.ticketId,
      stepId: scope?.stepId,
    });
    this.notify(); // the op changed the graph/channel — re-poll
    return out;
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
