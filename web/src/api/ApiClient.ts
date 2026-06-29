import type { ProjectGraph } from '../domain/graph';
import type { StepDetail, ReviewAction, PlanProposal, ProjectInfo } from './dto';

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
  /** The project's target repo (where its executor commits) + where the path came from. */
  getProjectInfo(): Promise<ProjectInfo>;
  /** Set the project's target-repo override; pass null/'' to revert to the workspace default. */
  setProjectRepo(repoDir: string | null): Promise<ProjectInfo>;
  subscribe(cb: () => void): () => void; // called on any state change
}
