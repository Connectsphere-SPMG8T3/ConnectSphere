import { defineStore } from "pinia";

import { venueBookingsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

// Mirrors the API's BOOKING_NOTE_MAX_LENGTH ([Assumption], REQUIREMENTS §9).
export const BOOKING_NOTE_MAX_LENGTH = 1000;

/**
 * A coordinator's venue booking request (SCRUM-19). The API decides every
 * refusal (overlap, block, one venue per event, lifecycle); this store only
 * carries the request and the message that comes back, with what is in the
 * way when the API names it (SCRUM-21 `conflict`).
 */
export const useVenueBookingStore = defineStore("venueBooking", {
  state: () => ({ isRequesting: false, error: null, conflict: null }),

  actions: {
    async request(eventId, venueId, note, replacesBookingId = null, acknowledgedWarnings = false) {
      const auth = useAuthStore();
      this.isRequesting = true;
      this.error = null;
      this.conflict = null;
      try {
        const payload = { event_id: eventId, venue_id: venueId, note: note?.trim() || null };
        if (replacesBookingId) payload.replaces_booking_id = replacesBookingId;
        // BR-R3: a venue Suitable with warnings is requested only once they are acknowledged.
        if (acknowledgedWarnings) payload.acknowledge_warnings = true;
        return await auth.withSession((token) => venueBookingsApi.request(payload, token));
      } catch (error) {
        this.error = error.message;
        this.conflict = error.conflict ?? null;
        throw error;
      } finally {
        this.isRequesting = false;
      }
    },

    async requestForSpace(spaceId, venueId, note, replacesBookingId = null, acknowledgedWarnings = false) {
      const auth = useAuthStore();
      this.isRequesting = true;
      this.error = null;
      this.conflict = null;
      try {
        const payload = { event_space_request_id: spaceId, venue_id: venueId, note: note?.trim() || null };
        if (replacesBookingId) payload.replaces_booking_id = replacesBookingId;
        // BR-R3: a venue Suitable with warnings is requested only once they are acknowledged.
        if (acknowledgedWarnings) payload.acknowledge_warnings = true;
        return await auth.withSession((token) => venueBookingsApi.request(payload, token));
      } catch (error) {
        this.error = error.message;
        this.conflict = error.conflict ?? null;
        throw error;
      } finally {
        this.isRequesting = false;
      }
    },
  },
});
