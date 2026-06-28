import { create } from 'zustand';
import type { ProjectGraph } from '../domain/graph';
import type { ApiClient } from '../api/ApiClient';
import { MockApiClient } from '../api/mock/MockApiClient';

export type Altitude = 'map' | 'lane';

interface State {
  api: ApiClient;
  graph: ProjectGraph | null;
  selectedTicketId: string | null;
  selectedStepId: string | null;
  load: () => Promise<void>;
  selectTicket: (id: string | null) => void;
  selectStep: (id: string | null) => void;
}

export const useStore = create<State>((set, get) => {
  const api = new MockApiClient();
  // Always live: any state change in the API re-loads the graph, so every screen
  // reflects the new state without a manual refresh control.
  api.subscribe(() => {
    void get().load();
  });
  return {
    api,
    graph: null,
    selectedTicketId: null,
    selectedStepId: null,
    load: async () => set({ graph: await api.getGraph() }),
    // Opening a ticket selects it (and drops any open step from a previous ticket).
    selectTicket: (id) => set({ selectedTicketId: id, selectedStepId: null }),
    selectStep: (id) => set({ selectedStepId: id }),
  };
});
