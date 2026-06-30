import type { ProjectGraph } from '../domain/graph';
import type {
  StepDetail,
  ReviewAction,
  PlanProposal,
  ProjectInfo,
  ProjectSummary,
  ProjectProposal,
  ProjectCreated,
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
  /** Switch which project the per-project calls (graph/steps/plan/…) target. */
  setPid(pid: string): void;
  /** The project's target repo (where its executor commits) + where the path came from. */
  getProjectInfo(): Promise<ProjectInfo>;
  /** Set the project's target-repo override; pass null/'' to revert to the workspace default. */
  setProjectRepo(repoDir: string | null): Promise<ProjectInfo>;
  subscribe(cb: () => void): () => void; // called on any state change
}
