import { defineStore } from "pinia";

import { venueBookingsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

// Mirrors the API's BOOKING_NOTE_MAX_LENGTH ([Assumption], REQUIREMENTS §9).
export const BOOKING_NOTE_MAX_LENGTH = 1000;

/**
 * A coordinator's venue booking request (SCRUM-19). The API decides every
 * refusal (overlap, block, one venue per event, lifecycle); this store only
 * carries the request and the message that comes back.
 */
export const useVenueBookingStore = defineStore("venueBooking", {
  state: () => ({ isRequesting: false, error: null }),

  actions: {
    async request(eventId, venueId, note) {
      const auth = useAuthStore();
      this.isRequesting = true;
      this.error = null;
      try {
        const payload = { event_id: eventId, venue_id: venueId, note: note?.trim() || null };
        return await auth.withSession((token) => venueBookingsApi.request(payload, token));
      } catch (error) {
        this.error = error.message;
        throw error;
      } finally {
        this.isRequesting = false;
      }
    },
  },
});
