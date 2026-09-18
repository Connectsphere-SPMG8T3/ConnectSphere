import { defineStore } from "pinia";

import {
  sortPendingHoldsOldestFirst,
  summariseVenueStaffDashboard,
  venueStatuses as selectVenueStatuses,
} from "@/features/venues/dashboard";
import { toCalendarItems } from "@/features/venues/calendar";
import { ApiError, venuesApi } from "@/services/api";
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
    pendingHolds: [],
    reReviewBookings: [],
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
  }),

  getters: {
    counts: (state) => summariseVenueStaffDashboard(state),
    oldestFirstHolds: (state) => sortPendingHoldsOldestFirst(state.pendingHolds),
    calendarItems: (state) => toCalendarItems(state),
  },

  actions: {
    venueStatuses(now = new Date()) {
      return selectVenueStatuses(this.venues, this.blocks, now);
    },

    reset() {
      this.venues = [];
      this.pendingHolds = [];
      this.reReviewBookings = [];
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
  },
});
