import { create } from 'zustand';
import { neighbors, type ProjectGraph } from '../domain/graph';
import type { ApiClient } from '../api/ApiClient';
import { MockApiClient } from '../api/mock/MockApiClient';
import { HttpApiClient } from '../api/http/HttpApiClient';

export type Altitude = 'map' | 'lane';
// The top-bar exploration mode. Navigator = map (no ticket) or the ticket's kanban
// board (ticket open); Cockpit = the 3-pane review workspace for the open ticket.
export type Mode = 'navigator' | 'cockpit';

interface State {
  api: ApiClient;
  graph: ProjectGraph | null;
  mode: Mode;
  selectedTicketId: string | null;
  selectedStepId: string | null;
  reviewOpen: boolean; // full-screen review gate overlay
  planTicketId: string | null; // ticket whose plan is being edited (planning tickets)
  load: () => Promise<void>;
  setMode: (mode: Mode) => void;
  selectTicket: (id: string | null) => void;
  selectStep: (id: string | null) => void;
  openInCockpit: (stepId: string) => void; // jump from the board into the step's review
  openReview: () => void;
  closeReview: () => void;
  editPlan: (ticketId: string) => void;
  closePlan: () => void;
}

/** When a ticket opens, focus the step that needs you — the one awaiting review,
 *  else the first step — so the cockpit review fills in immediately. */
function defaultStepFor(graph: ProjectGraph | null, ticketId: string | null): string | null {
  if (!graph || !ticketId) return null;
  const steps = neighbors(graph, ticketId, 'out').filter((n) => n.kind === 'step');
  return (steps.find((s) => s.status === 'awaiting_review') ?? steps[0])?.id ?? null;
}

export const useStore = create<State>((set, get) => {
  // Swap to the real backend by setting VITE_API_BASE; otherwise run on the mock.
  const apiBase = import.meta.env.VITE_API_BASE;
  const api: ApiClient = apiBase ? new HttpApiClient(apiBase, 'p1') : new MockApiClient();
  // Always live: any state change in the API re-loads the graph, so every screen
  // reflects the new state without a manual refresh control.
  api.subscribe(() => {
    void get().load();
  });
  return {
    api,
    graph: null,
    mode: 'navigator',
    selectedTicketId: null,
    selectedStepId: null,
    reviewOpen: false,
    planTicketId: null,
    load: async () => set({ graph: await api.getGraph() }),
    setMode: (mode) => set({ mode }),
    selectTicket: (id) =>
      set((s) => ({
        selectedTicketId: id,
        selectedStepId: defaultStepFor(s.graph, id),
        reviewOpen: false,
      })),
    selectStep: (id) => set({ selectedStepId: id }),
    openInCockpit: (stepId) => set({ selectedStepId: stepId, mode: 'cockpit' }),
    openReview: () => set({ reviewOpen: true }),
    closeReview: () => set({ reviewOpen: false }),
    editPlan: (ticketId) => set({ planTicketId: ticketId }),
    closePlan: () => set({ planTicketId: null }),
  };
});
