import { defineStore } from "pinia";

import { ApiError, eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

const NETWORK_ERROR = "Unable to reach the server. Please try again.";

/**
 * Backing store for the Event Coordinator Lead dashboard (CR-101): loads
 * `GET /events/dashboard/lead` and performs `POST /events/{id}/assign` (SCRUM-12) and `/reassign`.
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
    // CR-106: declining a coordinator's reassignment request, with its own error for the dialog.
    isDeclining: false,
    declineError: null,
    // SCRUM-81 AC4: the open event's reassignments. `historyEventId` marks which event the
    // current load is for, so a slow answer for an event the Lead has left is dropped.
    history: [],
    historyEventId: null,
    historyError: null,
    isLoadingHistory: false,
  }),

  getters: {
    allEvents: (state) => [...state.unassigned, ...state.activeEvents],
    eventById() {
      return (id) => this.allEvents.find((event) => event.event_id === id);
    },
  },

  actions: {
    // Forget everything: a view calls this as it opens so it never shows rows or an
    // error left by an earlier visit, or by another account on the same tab.
    reset() {
      this.unassigned = [];
      this.activeEvents = [];
      this.coordinators = [];
      this.error = null;
      this.hasSettled = false;
      this.reassignError = null;
      this.declineError = null;
      this.history = [];
      this.historyEventId = null;
      this.historyError = null;
      this.isLoadingHistory = false;
    },

    // SCRUM-81 AC4: the reassignments of one event, newest first. A failure leaves the list
    // empty with a message; the event itself is unaffected.
    async loadHistory(eventId) {
      const auth = useAuthStore();
      this.historyEventId = eventId;
      this.history = [];
      this.historyError = null;
      if (!auth.token) return;
      this.isLoadingHistory = true;
      try {
        const response = await auth.withSession((token) => eventsApi.reassignmentHistory(eventId, token));
        if (this.historyEventId !== eventId) return;
        this.history = response?.entries ?? [];
      } catch (err) {
        if (this.historyEventId !== eventId) return;
        this.historyError = err instanceof ApiError ? err.message : NETWORK_ERROR;
      } finally {
        if (this.historyEventId === eventId) this.isLoadingHistory = false;
      }
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

    // Assign a coordinator to a queued event (SCRUM-12). Shares the reassign flags: a Lead
    // is only ever doing one of the two on a page.
    async assign(eventId, coordinatorId) {
      const auth = useAuthStore();
      this.isReassigning = true;
      this.reassignError = null;
      try {
        await auth.withSession((token) => eventsApi.assign(eventId, coordinatorId, token));
      } catch (err) {
        this.reassignError = err instanceof ApiError ? err.message : NETWORK_ERROR;
        return false;
      } finally {
        this.isReassigning = false;
      }
      await this.load();
      return true;
    },

    // CR-106 AC5: decline the coordinator's open request with a reason. The coordinator stays assigned.
    async declineReassignment(eventId, reason) {
      const auth = useAuthStore();
      this.isDeclining = true;
      this.declineError = null;
      try {
        await auth.withSession((token) => eventsApi.declineReassignment(eventId, reason.trim(), token));
      } catch (err) {
        this.declineError = err instanceof ApiError ? err.message : NETWORK_ERROR;
        return false;
      } finally {
        this.isDeclining = false;
      }
      await this.load();
      return true;
    },

    async reassign(eventId, coordinatorId, expectedVersion) {
      const auth = useAuthStore();
      this.isReassigning = true;
      this.reassignError = null;
      try {
        await auth.withSession((token) => eventsApi.reassign(eventId, coordinatorId, expectedVersion, token));
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
