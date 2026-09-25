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

export function canReturn(status) {
  return status === "under_review";
}

/**
 * The event a coordinator is reviewing (SCRUM-34 approve, SCRUM-52 reject, SCRUM-33 return) and its
 * status history. `loadHistory` is also used by the organiser's event page.
 */
export const useEventReviewStore = defineStore("eventReview", {
  // `historyEventId` tracks which event `history` belongs to, and doubles as
  // the "current request" marker for both `load` and `loadHistory`: each
  // request captures the id it's fetching for, and checks it again after
  // every await before writing state. The store is a singleton, so without
  // this two problems can occur — either while a fetch is still pending, or
  // permanently if it fails (SCRUM-52) or resolves out of order (SCRUM-34/52):
  // the previous event's history can show on the new event's page, or an
  // older, slower request can overwrite a newer one's result after the fact.
  state: () => ({ event: null, history: [], historyEventId: null, isLoading: false, isActing: false, error: null }),

  actions: {
    async load(eventId) {
      const auth = useAuthStore();
      this.historyEventId = eventId;
      this.isLoading = true;
      this.error = null;
      try {
        const [event, history] = await Promise.all([
          auth.withSession((token) => eventsApi.get(eventId, token)),
          auth.withSession((token) => eventsApi.history(eventId, token)),
        ]);
        // A newer `load`/`loadHistory` call started while this one was in
        // flight and resolved first: this response is stale, so don't let it
        // clobber the newer state (SCRUM-34/52).
        if (this.historyEventId !== eventId) return;
        this.event = event;
        this.history = history?.entries ?? [];
      } catch (error) {
        if (this.historyEventId !== eventId) return;
        this.event = null;
        this.history = [];
        this.error = error.message;
      } finally {
        if (this.historyEventId === eventId) this.isLoading = false;
      }
    },

    async loadHistory(eventId) {
      const auth = useAuthStore();
      // Switching to a different event: clear the previous event's entries
      // before fetching, synchronously, so they never show for the new event
      // — not while this fetch is pending, and not if it fails. A refresh for
      // the *same* event (the post-decision reload in `act()`) keeps the
      // current history in place until the new entries arrive.
      if (this.historyEventId !== eventId) {
        this.history = [];
        this.historyEventId = eventId;
      }
      try {
        const response = await auth.withSession((token) => eventsApi.history(eventId, token));
        // A newer request for a different event superseded this one while it
        // was in flight: stale, so leave the (already newer) history alone.
        if (this.historyEventId !== eventId) return this.history;
        this.history = response?.entries ?? [];
        return this.history;
      } catch (error) {
        if (this.historyEventId !== eventId) return this.history;
        throw error;
      }
    },

    async approve() {
      return this.act((token) => eventsApi.approve(this.event.id, token));
    },

    async reject(reason) {
      return this.act((token) => eventsApi.reject(this.event.id, reason.trim(), token));
    },

    async returnForAmendment(message, flaggedFields) {
      return this.act((token) =>
        eventsApi.returnForAmendment(this.event.id, { message: message.trim(), flagged_fields: flaggedFields }, token),
      );
    },

    async act(call) {
      const auth = useAuthStore();
      this.isActing = true;
      this.error = null;
      try {
        this.event = await auth.withSession(call);
      } catch (error) {
        this.error = error.message;
        throw error;
      } finally {
        this.isActing = false;
      }
      // The decision already succeeded above; a history refresh failing here
      // must not report it as failed or invite a retry that would 409.
      try {
        await this.loadHistory(this.event.id);
      } catch {
        // Previous history stays as-is until the next successful load.
      }
      return this.event;
    },
  },
});
