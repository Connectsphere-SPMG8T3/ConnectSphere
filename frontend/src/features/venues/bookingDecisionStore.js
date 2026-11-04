import { defineStore } from "pinia";

import { rejectionPayload } from "@/features/venues/bookingDecision";
import { venueBookingsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

/**
 * One booking request on its own page: venue staff approve it (SCRUM-36) or
 * reject it (SCRUM-38), and the assigned coordinator reads why. The API
 * decides whether a decision still applies; on a 409 the booking changed under
 * the page, so the store reloads it and keeps the message, rather than leaving
 * a stale Approve or Reject on show.
 */
export const useBookingDecisionStore = defineStore("bookingDecision", {
  state: () => ({
    booking: null,
    isLoading: false,
    loadError: null,
    isApproving: false,
    isRejecting: false,
    isRestoring: false,
    isPreparing: false,
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

    /** Resolves true once approved; false with `error` set (and `conflict` on a 409) otherwise. */
    approve(bookingId) {
      return this.decide(bookingId, "isApproving", (token) => venueBookingsApi.approve(bookingId, token));
    },

    /** Resolves true once rejected; false with `error` set (and `conflict` on a 409) otherwise. */
    reject(bookingId, form) {
      return this.decide(
        bookingId, "isRejecting", (token) => venueBookingsApi.reject(bookingId, rejectionPayload(form), token),
      );
    },

    /** One decision at a time: either one in flight blocks both (AC9 is the API's; this only avoids a double send). */
    async decide(bookingId, busyFlag, send) {
      if (this.isApproving || this.isRejecting) return false;
      const auth = useAuthStore();
      this[busyFlag] = true;
      this.error = null;
      this.conflict = false;
      try {
        this.booking = await auth.withSession(send);
        return true;
      } catch (error) {
        this.error = error.message;
        if (error.status === 409) {
          this.conflict = true;
          await this.load(bookingId);
        }
        return false;
      } finally {
        this[busyFlag] = false;
      }
    },

    /**
     * Venue staff restore an affected booking (CR-95 AC9). Resolves true once
     * it is unflagged; false with `error` set otherwise, and on a 409 the
     * booking is reloaded because the venue or the replacement changed.
     */
    async restore(bookingId) {
      if (this.isRestoring) return false;
      const auth = useAuthStore();
      this.isRestoring = true;
      this.error = null;
      this.conflict = false;
      try {
        this.booking = await auth.withSession((token) => venueBookingsApi.restore(bookingId, token));
        return true;
      } catch (error) {
        this.error = error.message;
        if (error.status === 409) {
          this.conflict = true;
          await this.load(bookingId);
        }
        return false;
      } finally {
        this.isRestoring = false;
      }
    },

    async setPreparation(bookingId, payload) {
      if (this.isPreparing) return false;
      const auth = useAuthStore();
      this.isPreparing = true;
      this.error = null;
      this.conflict = false;
      try {
        const updated = await auth.withSession((token) =>
          venueBookingsApi.setPreparation(bookingId, payload, token),
        );
        this.booking = {
          ...this.booking,
          preparation: {
            stage: updated.stage,
            note: updated.note,
            updated_at: updated.updated_at,
            updated_by_name: updated.updated_by_name ?? null,
          },
        };
        return true;
      } catch (error) {
        this.error = error.message;
        this.conflict = error.status === 409;
        if (this.conflict) await this.load(bookingId);
        return false;
      } finally {
        this.isPreparing = false;
      }
    },
  },
});
