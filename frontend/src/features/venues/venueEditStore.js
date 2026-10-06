import { defineStore } from "pinia";

import { editFormToPayload } from "@/features/venues/venueProfile";
import { venuesApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

/**
 * The venue a venue-staff member is editing (SCRUM-63) and its change
 * history. Mirrors `eventReviewStore`'s shape: a singleton store with a
 * request marker (`venueId`) so a slow or out-of-order response for a
 * previous venue can never land on the page for a new one.
 */
export const useVenueEditStore = defineStore("venueEdit", {
  state: () => ({
    venueId: null,
    venue: null,
    history: [],
    warnings: [],
    isLoading: false,
    isSaving: false,
    error: null,
  }),

  actions: {
    async load(venueId) {
      const auth = useAuthStore();
      this.venueId = venueId;
      this.isLoading = true;
      this.error = null;
      this.warnings = [];
      try {
        const venue = await auth.withSession((token) => venuesApi.get(venueId, token));
        if (this.venueId !== venueId) return;
        this.venue = venue;
      } catch (error) {
        if (this.venueId !== venueId) return;
        this.venue = null;
        this.error = error.message;
      } finally {
        if (this.venueId === venueId) this.isLoading = false;
      }
    },

    async loadHistory(venueId) {
      const auth = useAuthStore();
      // Switching to a different venue (or loading history standalone, as
      // VenueDetailView does without calling `load()` first): clear the
      // previous venue's entries before fetching, so they never show under
      // the new one, like `eventReviewStore.loadHistory`.
      if (this.venueId !== venueId) {
        this.history = [];
        this.venueId = venueId;
      }
      try {
        const response = await auth.withSession((token) => venuesApi.history(venueId, token));
        if (this.venueId !== venueId) return this.history;
        this.history = response?.entries ?? [];
        return this.history;
      } catch (error) {
        if (this.venueId !== venueId) return this.history;
        throw error;
      }
    },

    /**
     * Submit the edit form. Returns `true` once saved; `false` when a
     * warning came back and the caller should show it and let the user
     * decide whether to confirm (VC-R2) — nothing is written in that case.
     */
    async submit(form, { confirm = false } = {}) {
      const auth = useAuthStore();
      const venueId = this.venueId;
      this.isSaving = true;
      this.error = null;
      try {
        const payload = editFormToPayload(form, { confirm });
        const response = await auth.withSession((token) => venuesApi.update(venueId, payload, token));
        if (this.venueId !== venueId) return false;
        this.warnings = response.warnings ?? [];
        if (response.saved) {
          this.venue = response.venue;
          return true;
        }
        return false;
      } catch (error) {
        if (this.venueId === venueId) this.error = error.message;
        throw error;
      } finally {
        if (this.venueId === venueId) this.isSaving = false;
      }
    },
  },
});
