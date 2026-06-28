import type { ProjectGraph } from '../domain/graph';
import type { StepDetail, ReviewAction, PlanProposal } from './dto';

/** The single seam every screen depends on. v1 ships MockApiClient; the real
 *  backend swaps this implementation without touching the UI. */
export interface ApiClient {
  getGraph(): Promise<ProjectGraph>;
  getStepDetail(stepId: string): Promise<StepDetail>;
  proposePlan(goal: string): Promise<PlanProposal>;
  approvePlan(proposal: PlanProposal): Promise<void>;
  reviewStep(stepId: string, action: ReviewAction): Promise<void>;
  owningPath(nodeId: string): Promise<string[]>; // node ids from CodeRegion up to Objective
  subscribe(cb: () => void): () => void; // called on any state change
}
