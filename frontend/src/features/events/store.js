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
 * Loads `GET /events/dashboard/coordinator` (`events.service.coordinator_dashboard`
 * in the backend), whose response shape is the state below: `action_items` and
 * `active_events`. The widgets were built against this contract before the
 * endpoint existed, so they needed no change when it shipped.
 */
export const useCoordinatorDashboardStore = defineStore("coordinatorDashboard", {
  state: () => ({
    actionItems: [],
    activeEvents: [],
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
        this.isAvailable = true;
      } catch (err) {
        this.reset();
        // A 404 means this backend predates the endpoint. That is not an
        // error worth showing a coordinator, so the widgets simply stay empty.
        // Anything else is a real failure and must be visible — an empty dashboard that silently
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
