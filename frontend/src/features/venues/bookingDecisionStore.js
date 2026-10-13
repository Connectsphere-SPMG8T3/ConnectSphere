import { defineStore } from "pinia";

import { rejectionPayload } from "@/features/venues/bookingDecision";
import { venueBookingsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

/**
 * One booking request on its own page (SCRUM-38): venue staff decide it, and
 * the assigned coordinator reads why. The API decides whether a decision still
 * applies; on a 409 the booking changed under the page (AC10), so the store
 * reloads it and keeps the message, rather than leaving a stale Reject on show.
 * SCRUM-36's approval belongs here too.
 */
export const useBookingDecisionStore = defineStore("bookingDecision", {
  state: () => ({
    booking: null,
    isLoading: false,
    loadError: null,
    isRejecting: false,
    error: null,
    conflict: false,
  }),

  actions: {
    async load(bookingId) {
      const auth = useAuthStore();
      this.isLoading = true;
      this.loadError = null;
      try {
        this.booking = await auth.withSession((token) => venueBookingsApi.get(bookingId, token));
      } catch (error) {
        this.booking = null;
        this.loadError = error.message;
      } finally {
        this.isLoading = false;
      }
    },

    /** Resolves true once rejected; false with `error` set (and `conflict` on a 409) otherwise. */
    async reject(bookingId, form) {
      if (this.isRejecting) return false;
      const auth = useAuthStore();
      this.isRejecting = true;
      this.error = null;
      this.conflict = false;
      try {
        this.booking = await auth.withSession((token) => venueBookingsApi.reject(bookingId, rejectionPayload(form), token));
        return true;
      } catch (error) {
        this.error = error.message;
        if (error.status === 409) {
          this.conflict = true;
          await this.load(bookingId);
        }
        return false;
      } finally {
        this.isRejecting = false;
      }
    },
  },
});
