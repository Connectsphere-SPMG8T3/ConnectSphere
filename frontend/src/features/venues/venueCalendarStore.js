import { defineStore } from "pinia";

import { shiftAnchor, viewRange } from "@/features/venues/availabilityCalendar";
import { singaporeDayKey } from "@/features/venues/singaporeTime";
import { venuesApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

/**
 * The venue, view and period a venue-staff member has on their availability
 * calendar (SCRUM-57), and what occupies it. Every change asks the API again
 * for just that range, so a booking approved or a block added elsewhere shows
 * on the next load without a page reload (AC4). Each request is stamped, so a
 * slow answer for a venue or period already left can't land on the new one.
 */
export const useVenueCalendarStore = defineStore("venueCalendar", {
  state: () => ({
    venueId: null,
    view: "week",
    anchorKey: null,
    calendar: null,
    isLoading: false,
    hasLoaded: false,
    error: null,
    requestId: 0,
  }),

  actions: {
    async open(venueId, { today } = {}) {
      this.venueId = venueId;
      if (!this.anchorKey || today) this.anchorKey = singaporeDayKey(today ?? new Date());
      await this.load();
    },

    async setView(view) {
      if (view === this.view) return;
      this.view = view;
      await this.load();
    },

    async step(delta) {
      this.anchorKey = shiftAnchor(this.view, this.anchorKey, delta);
      await this.load();
    },

    async goToToday(today = new Date()) {
      this.anchorKey = singaporeDayKey(today);
      await this.load();
    },

    async refresh() {
      await this.load();
    },

    async load() {
      if (!this.venueId) return;
      const auth = useAuthStore();
      const requestId = this.requestId + 1;
      this.requestId = requestId;
      const venueId = this.venueId;
      this.isLoading = true;
      this.error = null;
      try {
        const calendar = await auth.withSession((token) =>
          venuesApi.calendar(venueId, viewRange(this.view, this.anchorKey), token),
        );
        if (this.requestId !== requestId) return;
        this.calendar = calendar;
      } catch (error) {
        if (this.requestId !== requestId) return;
        this.calendar = null;
        this.error = error.message;
      } finally {
        if (this.requestId === requestId) {
          this.isLoading = false;
          this.hasLoaded = true;
        }
      }
    },
  },
});
