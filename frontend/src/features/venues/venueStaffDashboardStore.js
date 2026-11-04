import { defineStore } from "pinia";

import {
  sortPendingHoldsSoonestExpiryFirst,
  venueStatuses as selectVenueStatuses,
} from "@/features/venues/dashboard";
import { toCalendarItems } from "@/features/venues/calendar";
import { ApiError, venueBookingsApi, venuesApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

/**
 * Backing store for the Venue Staff dashboard (SCRUM-70).
 *
 * Unlike the coordinator's, every widget here has real data today: venues,
 * blocks and bookings all exist. The `isAvailable` / `hasSettled` pair is kept
 * anyway, because the distinction it draws still matters — a dashboard that
 * shows "0 pending requests" before it has heard from the server is telling a
 * venue staff member they have nothing to do, which may be false.
 *
 * All logic lives in `features/venues/dashboard.js` and `calendar.js`; this
 * store only fetches and holds.
 */
export const useVenueStaffDashboardStore = defineStore("venueStaffDashboard", {
  state: () => ({
    venues: [],
    bookingRequests: [],
    pendingHolds: [],
    reReviewBookings: [],
    // CR-95 AC9: live bookings whose venue became unavailable, for staff to restore.
    affectedBookings: [],
    blocks: [],
    generatedAt: null,
    isLoading: false,
    error: null,
    // False until a load has actually returned data.
    isAvailable: false,
    // False until the first load has finished, however it finished. The counts
    // are meaningless before that, so the dashboard withholds them rather than
    // showing a zero it cannot yet stand behind.
    hasSettled: false,
    // CR-99 AC2: a change of expiry in flight, and why the last one failed.
    isChangingExpiry: false,
    expiryError: null,
  }),

  getters: {
    soonestExpiryHolds: (state) => sortPendingHoldsSoonestExpiryFirst(state.pendingHolds),
    calendarItems: (state) => toCalendarItems(state),
  },

  actions: {
    venueStatuses(now = new Date()) {
      return selectVenueStatuses(this.venues, this.blocks, now);
    },

    reset() {
      this.venues = [];
      this.bookingRequests = [];
      this.pendingHolds = [];
      this.reReviewBookings = [];
      this.affectedBookings = [];
      this.blocks = [];
      this.generatedAt = null;
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
        const payload = await auth.withSession((token) => venuesApi.venueStaffDashboard(token));
        this.venues = payload?.venues ?? [];
        this.pendingHolds = payload?.pending_holds ?? [];
        this.reReviewBookings = payload?.re_review_bookings ?? [];
        this.affectedBookings = payload?.affected_bookings ?? [];
        this.bookingRequests = payload?.booking_requests ?? [...this.pendingHolds, ...this.reReviewBookings];
        this.blocks = payload?.blocks ?? [];
        this.generatedAt = payload?.generated_at ?? null;
        this.isAvailable = true;
      } catch (err) {
        this.reset();
        // A 404 here means the SPA is talking to a backend older than itself,
        // not that the feature is unbuilt — the endpoint ships in this story.
        // It still isn't worth an error banner: the widgets stay empty and say
        // they are waiting. Anything else is a real failure and must be
        // visible, because an empty dashboard that quietly swallowed a 500
        // would tell a staff member nothing needs their attention.
        if (!(err instanceof ApiError) || err.status !== 404) {
          this.error =
            err instanceof ApiError ? err.message : "Unable to reach the server. Please try again.";
        }
      } finally {
        this.isLoading = false;
        this.hasSettled = true;
      }
    },

    /**
     * Change or extend a hold's expiry (CR-99 AC2), then reload the queue so
     * its order follows the new expiry. Resolves true when saved; otherwise
     * `expiryError` says why, in the server's words where it gave them.
     */
    async changeHoldExpiry(bookingId, expiresAt) {
      this.expiryError = null;
      if (!expiresAt) {
        this.expiryError = "Choose a date and time for the new expiry.";
        return false;
      }
      const auth = useAuthStore();
      this.isChangingExpiry = true;
      try {
        await auth.withSession((token) =>
          venueBookingsApi.changeExpiry(bookingId, { expires_at: expiresAt }, token),
        );
      } catch (err) {
        this.expiryError =
          err instanceof ApiError ? err.message : "Unable to reach the server. Please try again.";
        return false;
      } finally {
        this.isChangingExpiry = false;
      }
      await this.load();
      return true;
    },
  },
});
