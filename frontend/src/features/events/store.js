import { defineStore } from "pinia";

import {
  groupActiveEventsByStatus,
  prioritiseActionItems,
  readinessGaps as selectReadinessGaps,
} from "@/features/events/dashboard";
import { ApiError, eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

/**
 * Backing store for the Event Coordinator dashboard (SCRUM-72).
 *
 * The shape below is the contract the `events` module's dashboard endpoint has
 * to return. It is defined now so the widgets are built against real data, not
 * placeholders: today the endpoint does not exist and every widget renders its
 * empty state, and when the endpoint ships the dashboard fills in with no
 * further component changes.
 */
export const useCoordinatorDashboardStore = defineStore("coordinatorDashboard", {
  state: () => ({
    actionItems: [],
    activeEvents: [],
    unassignedCount: 0,
    isLoading: false,
    error: null,
    // False until a load has actually returned data. Distinguishes "the events
    // module isn't built yet" from "you genuinely have nothing to do", which
    // the dashboard words differently.
    isAvailable: false,
    // False until the first load has finished, however it finished. The counts
    // are meaningless before that, so the dashboard withholds them rather than
    // showing a zero it cannot yet stand behind.
    hasSettled: false,
  }),

  getters: {
    prioritisedActions: (state) => prioritiseActionItems(state.actionItems),
    statusGroups: (state) => groupActiveEventsByStatus(state.activeEvents),
  },

  actions: {
    readinessGaps({ now = new Date(), days = 14 } = {}) {
      return selectReadinessGaps(this.activeEvents, { now, days });
    },

    reset() {
      this.actionItems = [];
      this.activeEvents = [];
      this.unassignedCount = 0;
      this.isAvailable = false;
    },

    async load() {
      const auth = useAuthStore();
      if (!auth.token) {
        this.hasSettled = true;
        return;
      }

      this.isLoading = true;
      this.error = null;
      try {
        const payload = await auth.withSession((token) => eventsApi.coordinatorDashboard(token));
        this.actionItems = payload?.action_items ?? [];
        this.activeEvents = payload?.active_events ?? [];
        this.unassignedCount = payload?.unassigned_count ?? 0;
        this.isAvailable = true;
      } catch (err) {
        this.reset();
        // A 404 means the endpoint isn't deployed yet, which is the expected
        // state for the whole of Sprint 1. That is not an error worth showing a
        // coordinator, so the widgets simply stay empty. Anything else is a
        // real failure and must be visible — an empty dashboard that silently
        // swallowed a 500 would tell a coordinator they have nothing to do.
        if (!(err instanceof ApiError) || err.status !== 404) {
          this.error =
            err instanceof ApiError
              ? err.message
              : "Unable to reach the server. Please try again.";
        }
      } finally {
        this.isLoading = false;
        this.hasSettled = true;
      }
    },
  },
});
