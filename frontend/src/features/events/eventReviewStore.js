import { defineStore } from "pinia";

import { eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

// Mirrors the API's REJECT_REASON_MAX_LENGTH ([Assumption], REQUIREMENTS §9).
export const REJECT_REASON_MAX_LENGTH = 1000;

// Which buttons to offer. The API is the enforcement point (lifecycle.py); these
// only avoid offering an action that would answer 409.
export function canApprove(status) {
  return status === "under_review";
}

export function canReject(status) {
  return status === "under_review" || status === "planning";
}

/**
 * The event a coordinator is reviewing (SCRUM-34 approve, SCRUM-52 reject) and its
 * status history. `loadHistory` is also used by the organiser's event page.
 */
export const useEventReviewStore = defineStore("eventReview", {
  state: () => ({ event: null, history: [], isLoading: false, isActing: false, error: null }),

  actions: {
    async load(eventId) {
      const auth = useAuthStore();
      this.isLoading = true;
      this.error = null;
      try {
        const [event, history] = await Promise.all([
          auth.withSession((token) => eventsApi.get(eventId, token)),
          auth.withSession((token) => eventsApi.history(eventId, token)),
        ]);
        this.event = event;
        this.history = history?.entries ?? [];
      } catch (error) {
        this.event = null;
        this.history = [];
        this.error = error.message;
      } finally {
        this.isLoading = false;
      }
    },

    async loadHistory(eventId) {
      const auth = useAuthStore();
      const response = await auth.withSession((token) => eventsApi.history(eventId, token));
      this.history = response?.entries ?? [];
      return this.history;
    },

    async approve() {
      return this.act((token) => eventsApi.approve(this.event.id, token));
    },

    async reject(reason) {
      return this.act((token) => eventsApi.reject(this.event.id, reason.trim(), token));
    },

    async act(call) {
      const auth = useAuthStore();
      this.isActing = true;
      this.error = null;
      try {
        this.event = await auth.withSession(call);
        await this.loadHistory(this.event.id);
        return this.event;
      } catch (error) {
        this.error = error.message;
        throw error;
      } finally {
        this.isActing = false;
      }
    },
  },
});
