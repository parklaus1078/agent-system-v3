import type { ProjectGraph } from '../domain/graph';
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
} from './dto';

/** The single seam every screen depends on. v1 ships MockApiClient; the real
 *  backend swaps this implementation without touching the UI. */
export interface ApiClient {
  getGraph(): Promise<ProjectGraph>;
  getStepDetail(stepId: string): Promise<StepDetail>;
  /** Start the planning lifecycle and return the proposed (editable) steps —
   *  for a brand-new goal, or to (re)plan an existing planning ticket. The
   *  returned `ticketId` is the one to pass back to approvePlan. */
  proposePlan(target: { goal: string; ticketId?: string } | { ticketId: string }): Promise<PlanProposal>;
  approvePlan(proposal: PlanProposal): Promise<void>;
  reviewStep(stepId: string, action: ReviewAction): Promise<void>;
  owningPath(nodeId: string): Promise<string[]>; // node ids from CodeRegion up to Objective
  /** Persist dragged map node positions for the current project (node.data.pos). */
  saveLayout(positions: Record<string, { x: number; y: number }>): Promise<void>;
  /** All projects for the landing page. */
  listProjects(): Promise<ProjectSummary[]>;
  /** Propose a project from a raw goal — {slug, title, tickets[]}; persists nothing. */
  proposeProject(goal: string): Promise<ProjectProposal>;
  /** Create the project (objective + planning tickets). Idempotent on slug. */
  approveProject(proposal: ProjectProposal): Promise<ProjectCreated>;
  /** Delete a project's mapping data (nodes/edges/messages) + checkpoints; with
   *  `deleteDirectory`, also remove the actual project repo directory. */
  deleteProject(projectId: string, deleteDirectory: boolean): Promise<ProjectDeleted>;
  /** Update the current project's title/description (view+edit after creation). */
  setProjectMeta(meta: { title?: string; description?: string }): Promise<ProjectMeta>;
  /** Switch which project the per-project calls (graph/steps/plan/…) target. */
  setPid(pid: string): void;
  /** The project's target repo (where its executor commits) + where the path came from. */
  getProjectInfo(): Promise<ProjectInfo>;
  /** Set the project's target-repo override; pass null/'' to revert to the workspace default. */
  setProjectRepo(repoDir: string | null): Promise<ProjectInfo>;

  // ── CP0 governance: rules (what to inject) + model routing (who runs each point) ──
  /** Global default rules. */
  getGlobalRules(): Promise<Rules>;
  /** Update global rules; omit an axis to leave it unchanged. */
  setGlobalRules(rules: Partial<Rules>): Promise<Rules>;
  /** Current project's rules: its override, the global default, and the effective merge. */
  getProjectRules(): Promise<ProjectRules>;
  setProjectRules(rules: Partial<Rules>): Promise<ProjectRules>;
  /** Global model-routing table (+ point/transport vocabularies). */
  getGlobalModels(): Promise<GlobalModels>;
  setGlobalModels(models: ModelsMap): Promise<GlobalModels>;
  /** Current project's model routing: override, global, effective per point. */
  getProjectModels(): Promise<ProjectModels>;
  setProjectModels(models: ModelsMap): Promise<ProjectModels>;
  /** Per-transport health (CLI present / API key set) — status only, never secrets. */
  getModelAvailability(): Promise<ModelAvailability[]>;

  // ── CP1 autonomy/throttle: the per-project dial (auto / co-pilot / per-step) ──
  /** The current project's throttle: override, global default, effective level. */
  getProjectAutonomy(): Promise<ProjectAutonomy>;
  /** Set (or clear, with null) the current project's throttle override. */
  setProjectAutonomy(level: AutonomyLevel | null): Promise<ProjectAutonomy>;
  /** CP4: a ticket's throttle (ticket override + effective ticket>project>global). */
  getTicketAutonomy(ticketId: string): Promise<TicketAutonomy>;
  setTicketAutonomy(ticketId: string, level: AutonomyLevel | null): Promise<TicketAutonomy>;

  // ── CP2 conversation channel: typed agent->human messages ──
  /** The current project's channel messages; pass `since` (last seen id) for only newer ones. */
  getMessages(since?: number): Promise<ChannelMessage[]>;

  // ── CP3 steer: a human's free-form NL, routed to a fixed graph op ──
  /** Route a steer instruction; scope is the UI's current ticket/step selection (optional). */
  steer(text: string, scope?: { ticketId?: string; stepId?: string }): Promise<SteerResult>;

  subscribe(cb: () => void): () => void; // called on any state change
}
