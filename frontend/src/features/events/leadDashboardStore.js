import { defineStore } from "pinia";

import { ApiError, eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

const NETWORK_ERROR = "Unable to reach the server. Please try again.";

/**
 * Backing store for the Event Coordinator Lead dashboard (CR-101): loads
 * `GET /events/dashboard/lead` and performs `POST /events/{id}/reassign`.
 */
export const useLeadDashboardStore = defineStore("leadDashboard", {
  state: () => ({
    unassigned: [],
    activeEvents: [],
    coordinators: [],
    isLoading: false,
    error: null,
    // False until the first load has finished, however it finished, so the page
    // never shows a zero it cannot yet stand behind.
    hasSettled: false,
    isReassigning: false,
    reassignError: null,
  }),

  getters: {
    allEvents: (state) => [...state.unassigned, ...state.activeEvents],
    eventById() {
      return (id) => this.allEvents.find((event) => event.event_id === id);
    },
  },

  actions: {
    async load() {
      const auth = useAuthStore();
      if (!auth.token) {
        this.hasSettled = true;
        return;
      }
      this.isLoading = true;
      this.error = null;
      try {
        const payload = await auth.withSession((token) => eventsApi.leadDashboard(token));
        this.unassigned = payload?.unassigned ?? [];
        this.activeEvents = payload?.active_events ?? [];
        this.coordinators = payload?.coordinators ?? [];
      } catch (err) {
        // Never leave rows from an earlier load on screen next to an error.
        this.unassigned = [];
        this.activeEvents = [];
        this.coordinators = [];
        this.error = err instanceof ApiError ? err.message : NETWORK_ERROR;
      } finally {
        this.isLoading = false;
        this.hasSettled = true;
      }
    },

    async reassign(eventId, coordinatorId) {
      const auth = useAuthStore();
      this.isReassigning = true;
      this.reassignError = null;
      try {
        await auth.withSession((token) => eventsApi.reassign(eventId, coordinatorId, token));
      } catch (err) {
        this.reassignError = err instanceof ApiError ? err.message : NETWORK_ERROR;
        return false;
      } finally {
        this.isReassigning = false;
      }
      await this.load();
      return true;
    },
  },
});
