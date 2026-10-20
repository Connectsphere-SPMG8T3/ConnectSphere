import { defineStore } from "pinia";

import { canSubmit, toPayload } from "@/features/equipment/equipmentRequest";
import { equipmentApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

/**
 * One event's equipment request lines and the catalogue they're picked from
 * (SCRUM-45), for the assigned coordinator. `eventId` marks which event the state
 * belongs to; every request re-checks it after its await, so a slow response for
 * a previous event never lands on the current one (as useEventCommentsStore does).
 */
export const useEquipmentRequestStore = defineStore("equipmentRequest", {
  state: () => ({
    eventId: null,
    catalogue: [],
    lines: [],
    // SCRUM-24 AC9-AC11: the event's derived technical status and exit tick.
    technicalStatus: null,
    exitConfirmation: null,
    isLoading: false,
    isSubmitting: false,
    error: null,
    submitError: null,
  }),

  actions: {
    async load(eventId) {
      const auth = useAuthStore();
      if (this.eventId !== eventId) {
        this.lines = [];
        this.technicalStatus = null;
        this.exitConfirmation = null;
        this.isSubmitting = false;
        this.submitError = null;
      }
      this.eventId = eventId;
      this.isLoading = true;
      this.error = null;
      try {
        const [catalogue, requests] = await Promise.all([
          auth.withSession((token) => equipmentApi.catalogue(token)),
          auth.withSession((token) => equipmentApi.eventRequests(eventId, token)),
        ]);
        if (this.eventId !== eventId) return;
        this.catalogue = catalogue?.items ?? [];
        this.lines = requests?.lines ?? [];
        this.technicalStatus = requests?.technical_status ?? null;
        this.exitConfirmation = requests?.exit_confirmation ?? null;
      } catch (error) {
        if (this.eventId !== eventId) return;
        this.lines = [];
        this.error = error.message;
      } finally {
        if (this.eventId === eventId) this.isLoading = false;
      }
    },

    async submit(draftLines) {
      const eventId = this.eventId;
      if (!eventId || !canSubmit(draftLines)) return false;
      const auth = useAuthStore();
      this.isSubmitting = true;
      this.submitError = null;
      try {
        const saved = await auth.withSession((token) => equipmentApi.submitRequest(toPayload(eventId, draftLines), token));
        if (this.eventId !== eventId) return false;
        this.lines = [...this.lines, ...(saved?.lines ?? [])];
        return true;
      } catch (error) {
        if (this.eventId === eventId) this.submitError = error.message;
        return false;
      } finally {
        if (this.eventId === eventId) this.isSubmitting = false;
      }
    },
  },
});
