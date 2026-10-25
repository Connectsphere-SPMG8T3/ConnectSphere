import { defineStore } from "pinia";

import { eventsApi, venueBookingsApi } from "@/services/api";
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

export function canSendForSafetyCheck(event) {
  return event?.status === "planning" && event.safety_readiness?.ready === true;
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
  state: () => ({ event: null, history: [], safetyDecisions: [], historyEventId: null, isLoading: false, isActing: false, error: null }),

  actions: {
    async load(eventId) {
      const auth = useAuthStore();
      this.historyEventId = eventId;
      if (this.event?.id !== eventId) this.event = null;
      this.safetyDecisions = [];
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
        try {
          await this.loadSafetyDecisions(eventId);
        } catch {
          // Private history is supplementary; event details remain available.
        }
      } catch (error) {
        if (this.historyEventId !== eventId) return;
        this.event = null;
        this.history = [];
        this.error = error.message;
      } finally {
        if (this.historyEventId === eventId) this.isLoading = false;
      }
    },

    async loadSafetyDecisions(eventId) {
      this.safetyDecisions = [];
      const auth = useAuthStore();
      // Organiser sessions share this store but must never fetch comments.
      if (auth.role !== "event_coordinator") return;
      const decisions = await auth.withSession((token) => eventsApi.safetyDecisions(eventId, token));
      if (this.historyEventId !== eventId || auth.role !== "event_coordinator") return;
      this.safetyDecisions = decisions;
    },

    async loadHistory(eventId) {
      const auth = useAuthStore();
      if (auth.role !== "event_coordinator") this.safetyDecisions = [];
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

    async markBookingRevised(bookingId, note) {
      if (this.isActing) return;
      const auth = useAuthStore();
      const eventId = this.event.id;
      this.isActing = true;
      this.error = null;
      try {
        await auth.withSession((token) => venueBookingsApi.markRevised(bookingId, note, token));
        await this.load(eventId);
      } catch (error) {
        this.error = error.message;
        throw error;
      } finally {
        this.isActing = false;
      }
    },

    async sendForSafetyCheck() {
      const eventId = this.event.id;
      try {
        return await this.act((token) => eventsApi.sendForSafetyCheck(eventId, token));
      } catch (error) {
        // Refresh a stale readiness result without losing the original refusal.
        if (this.historyEventId === eventId || this.historyEventId === null) {
          await this.load(eventId);
          if (this.historyEventId === eventId) this.error = error.message;
        }
        throw error;
      }
    },

    // CR-97 AC9: the coordinator marks which space is the event's primary venue.
    async setPrimarySpace(spaceId) {
      return this.act((token) => eventsApi.setPrimarySpace(this.event.id, spaceId, token));
    },

    async clearPrimarySpace() {
      return this.act((token) => eventsApi.clearPrimarySpace(this.event.id, token));
    },

    async approve() {
      return this.act((token) => eventsApi.approve(this.event.id, token));
    },

    async reject(reason) {
      return this.act((token) => eventsApi.reject(this.event.id, reason.trim(), token));
    },

    // Story 115: the decision answers the bare event, so read it again for the
    // coordinator's view (venues, open request). The decision stands if that fails.
    async approveCancellation() {
      return this.decideCancellation((token) => eventsApi.approveCancellation(this.event.id, token));
    },

    async rejectCancellation(reason) {
      return this.decideCancellation((token) => eventsApi.rejectCancellation(this.event.id, reason.trim(), token));
    },

    // Story 37: deciding the organiser's change request reloads the event the same way.
    async rejectChange(reason) {
      return this.decideCancellation((token) => eventsApi.rejectChange(this.event.id, reason.trim(), token));
    },

    async cancelEvent(reason) {
      return this.decideCancellation((token) => eventsApi.cancelEvent(this.event.id, reason.trim(), token));
    },

    async decideCancellation(call) {
      const eventId = (await this.act(call)).id;
      try {
        const event = await useAuthStore().withSession((token) => eventsApi.get(eventId, token));
        if (this.historyEventId === eventId) this.event = event;
      } catch {
        // The decision's own response stays shown until the next load.
      }
      return this.event;
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
