import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { neighbors, type ProjectGraph } from '../domain/graph';
import type { ApiClient } from '../api/ApiClient';
import type { AutonomyLevel, ChannelMessage } from '../api/dto';
import { MockApiClient } from '../api/mock/MockApiClient';
import { HttpApiClient } from '../api/http/HttpApiClient';

export type Altitude = 'map' | 'lane';
// The top-bar exploration mode. Navigator = map (no ticket) or the ticket's kanban
// board (ticket open); Cockpit = the 3-pane review workspace for the open ticket.
export type Mode = 'navigator' | 'cockpit';

interface State {
  api: ApiClient;
  pid: string; // current project id (from the /project/:pid route)
  graph: ProjectGraph | null;
  online: boolean; // is the backend reachable (drives the live/offline indicator)
  error: string | null; // transient error to surface as a toast (e.g. a failed write)
  mode: Mode;
  selectedTicketId: string | null;
  selectedStepId: string | null;
  reviewOpen: boolean; // full-screen review gate overlay
  planTicketId: string | null; // ticket whose plan is being edited (planning tickets)
  autonomy: AutonomyLevel; // CP1 throttle: effective level for the current project
  messages: ChannelMessage[]; // CP2 channel (accumulated via the since cursor)
  highlightIds: string[] | null; // CP4: map nodes to highlight (BugTrace / channel ref chips)
  channelFilter: string | null; // CP4: when set, the channel shows only messages ref-ing this node
  channelOpen: boolean; // CP2 channel right-rail visibility (setting a filter forces it open)
  load: () => Promise<void>;
  loadAutonomy: () => Promise<void>;
  loadMessages: () => Promise<void>;
  setAutonomy: (level: AutonomyLevel) => Promise<void>;
  setPid: (pid: string) => void; // switch project (route-driven)
  setError: (msg: string | null) => void;
  setMode: (mode: Mode) => void;
  selectTicket: (id: string | null) => void;
  selectStep: (id: string | null) => void;
  setHighlightIds: (ids: string[] | null) => void;
  setChannelFilter: (nodeId: string | null) => void;
  setChannelOpen: (open: boolean) => void;
  focusNode: (nodeId: string) => void; // channel ref chip -> highlight the node on the map
  openInCockpit: (stepId: string) => void; // jump from the board into the step's review
  openReview: () => void;
  closeReview: () => void;
  editPlan: (ticketId: string) => void;
  closePlan: () => void;
}

/** When a ticket opens, focus the step that needs you — the one awaiting review,
 *  else the blocked one (so you can debug it), else the first step — so the
 *  cockpit review fills in immediately. */
function defaultStepFor(graph: ProjectGraph | null, ticketId: string | null): string | null {
  if (!graph || !ticketId) return null;
  const steps = neighbors(graph, ticketId, 'out').filter((n) => n.kind === 'step');
  const needsYou =
    steps.find((s) => s.status === 'awaiting_review') ?? steps.find((s) => s.status === 'blocked');
  return (needsYou ?? steps[0])?.id ?? null;
}

export const useStore = create<State>()(
  persist(
    (set, get) => {
      // Swap to the real backend by setting VITE_API_BASE; otherwise run on the mock.
      const apiBase = import.meta.env.VITE_API_BASE;
      const api: ApiClient = apiBase ? new HttpApiClient(apiBase, 'p1') : new MockApiClient();
      // Always live: any state change in the API re-loads the graph, so every screen
      // reflects the new state without a manual refresh control.
      api.subscribe(() => {
        void get().load();
        void get().loadMessages();
        void get().loadAutonomy(); // a steer `control` op can change the throttle server-side
      });
      return {
        api,
        pid: 'p1',
        graph: null,
        online: true,
        error: null,
        mode: 'navigator',
        selectedTicketId: null,
        selectedStepId: null,
        reviewOpen: false,
        planTicketId: null,
        autonomy: 'per-step',
        messages: [],
        highlightIds: null,
        channelFilter: null,
        channelOpen: true,
        setHighlightIds: (highlightIds) => set({ highlightIds }),
        // Setting a filter (a map node click) forces the channel open, so its filter indicator
        // and ✕ clear button are mounted — otherwise the filter would be invisible and stuck.
        setChannelFilter: (channelFilter) =>
          set(channelFilter ? { channelFilter, channelOpen: true } : { channelFilter }),
        setChannelOpen: (channelOpen) => set({ channelOpen }),
        focusNode: (nodeId) =>
          set({
            highlightIds: [nodeId],
            channelFilter: null,
            selectedTicketId: null,
            selectedStepId: null,
            reviewOpen: false,
            mode: 'navigator', // switch to the map so the highlight is visible
          }),
        loadMessages: async () => {
          const pid = get().pid; // guard: a slow response for a previous project must not apply
          const cur = get().messages;
          const since = cur.length ? cur[cur.length - 1].id : undefined;
          try {
            const newer = await api.getMessages(since);
            if (get().pid !== pid || !newer.length) return;
            const existing = get().messages;
            const maxId = existing.length ? existing[existing.length - 1].id : 0;
            const toAdd = newer.filter((m) => m.id > maxId); // dedupe against overlapping polls
            if (toAdd.length) set({ messages: [...existing, ...toAdd] });
          } catch {
            /* backend unreachable: keep the messages we have */
          }
        },
        loadAutonomy: async () => {
          const pid = get().pid; // guard: a slow response for a previous project must not win
          try {
            const v = await api.getProjectAutonomy();
            if (get().pid === pid && get().autonomy !== v.resolved) set({ autonomy: v.resolved });
          } catch {
            /* backend unreachable: keep the last known throttle */
          }
        },
        setAutonomy: async (level) => {
          const v = await api.setProjectAutonomy(level);
          set({ autonomy: v.resolved });
        },
        load: async () => {
          try {
            const next = await api.getGraph();
            const cur = get().graph;
            // Preserve referential identity when nothing changed, so dependent effects
            // (e.g. useStepDetail) don't re-fetch on every poll tick. Mark online again.
            if (cur && JSON.stringify(cur) === JSON.stringify(next)) {
              if (!get().online) set({ online: true });
              return;
            }
            set({ graph: next, online: true });
          } catch {
            // Backend unreachable: keep the last graph, flag offline (no unhandled
            // rejection, no silent stale "live" badge).
            if (get().online) set({ online: false });
          }
        },
        setPid: (pid) => {
          if (get().pid === pid && get().graph) return;
          api.setPid(pid);
          set({
            pid, graph: null, selectedTicketId: null, selectedStepId: null,
            reviewOpen: false, messages: [], highlightIds: null, channelFilter: null,
          });
          void get().load();
          void get().loadAutonomy(); // refresh the throttle dial for the new project
          void get().loadMessages(); // load the new project's channel from scratch
        },
        setError: (error) => set({ error }),
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
    },
    {
      // Persist only navigation state so a reload restores the cockpit/board/selection
      // instead of dropping back to the map. (sessionStorage = per-tab session.)
      name: 'asv3-ui',
      storage: createJSONStorage(() => sessionStorage),
      partialize: (s) => ({
        mode: s.mode,
        selectedTicketId: s.selectedTicketId,
        selectedStepId: s.selectedStepId,
      }),
    },
  ),
);
