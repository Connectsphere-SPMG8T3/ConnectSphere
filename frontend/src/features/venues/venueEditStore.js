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
    // SCRUM-64: bookings a deactivation would flag Affected, from the preview.
    affected: [],
    // SCRUM-51: the saved block and the bookings recorded against it (AC6).
    blockResult: null,
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

    /**
     * Deactivate a venue (SCRUM-64). Takes the venue id explicitly because
     * the profile page reads the venue through the search store, not `load()`.
     * Returns `true` once saved; `false` when `affected` came back and the
     * caller should show it and let staff confirm — nothing is written then.
     */
    async deactivate(venueId, { reason, note, version }, { confirm = false } = {}) {
      return this._save(async (token) => {
        const payload = { reason, note: note?.trim() || null, version, confirm };
        const response = await venuesApi.deactivate(venueId, payload, token);
        this.affected = response.saved ? [] : response.affected ?? [];
        if (response.saved) this.venue = response.venue;
        return response.saved;
      });
    },

    /**
     * Block a venue (SCRUM-51). `payload` is `toBlockPayload`'s. Returns
     * `true` once saved, with `blockResult` holding the block and the
     * bookings recorded against it; `false` when `affected` came back for
     * staff to confirm, and nothing was written.
     */
    async createBlock(venueId, payload) {
      return this._save(async (token) => {
        const response = await venuesApi.createBlock(venueId, payload, token);
        this.affected = response.saved ? [] : response.affected ?? [];
        this.blockResult = response.saved ? { block: response.block, affected: response.affected ?? [] } : null;
        return response.saved;
      });
    },

    async reactivate(venueId, version) {
      return this._save(async (token) => {
        this.venue = await venuesApi.reactivate(venueId, { version }, token);
      });
    },

    async _save(send) {
      const auth = useAuthStore();
      this.isSaving = true;
      this.error = null;
      try {
        return await auth.withSession(send);
      } catch (error) {
        this.error = error.message;
        throw error;
      } finally {
        this.isSaving = false;
      }
    },
  },
});
