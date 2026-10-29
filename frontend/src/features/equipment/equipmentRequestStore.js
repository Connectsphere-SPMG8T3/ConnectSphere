import { defineStore } from "pinia";

import { canSaveLine, canSubmit, toLineUpdate, toPayload } from "@/features/equipment/equipmentRequest";
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
    // Story 37: a refused Send for re-review, shown above the lines rather than instead of them.
    actionError: null,
    submitError: null,
    // SCRUM-44: the line being changed or removed, and the event's equipment
    // history (AC8), read on its own so a failed read never hides the lines.
    busyLineId: null,
    history: [],
    historyError: null,
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
        this.actionError = null;
        this.busyLineId = null;
        this.history = [];
        this.historyError = null;
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

    async loadHistory(eventId) {
      const auth = useAuthStore();
      try {
        const answer = await auth.withSession((token) => equipmentApi.eventHistory(eventId, token));
        if (this.eventId !== eventId) return;
        this.history = answer?.history ?? [];
        this.historyError = null;
      } catch (error) {
        if (this.eventId !== eventId) return;
        this.history = [];
        this.historyError = error.message;
      }
    },

    // SCRUM-44 AC2/AC3: change a line, naming the status it was seen in (AC6).
    // Success or refusal, the lines are reloaded so a line that moved shows its
    // real status.
    updateLine(line, draft) {
      if (!canSaveLine(draft)) return Promise.resolve(false);
      return this.changeLine(line, (token) => equipmentApi.updateLine(line.id, toLineUpdate(draft, line.status), token));
    },

    // SCRUM-44 AC1: remove a line, naming the status it was seen in (AC6).
    removeLine(line) {
      return this.changeLine(line, (token) => equipmentApi.removeLine(line.id, line.status, token));
    },

    async changeLine(line, call) {
      const eventId = this.eventId;
      if (!eventId || this.busyLineId) return false;
      const auth = useAuthStore();
      this.busyLineId = line.id;
      this.actionError = null;
      let saved = false;
      try {
        await auth.withSession(call);
        saved = true;
      } catch (error) {
        if (this.eventId === eventId) this.actionError = error.message;
      }
      if (this.eventId !== eventId) return false;
      await Promise.all([this.load(eventId), this.loadHistory(eventId)]);
      if (this.eventId === eventId) this.busyLineId = null;
      return saved;
    },

    // Story 37 AC6: a line an approved time change left short goes to technical support.
    async sendForReReview(lineId, note) {
      const eventId = this.eventId;
      if (!eventId || this.isSubmitting) return false;
      const auth = useAuthStore();
      this.isSubmitting = true;
      this.actionError = null;
      try {
        await auth.withSession((token) => equipmentApi.sendLineForReReview(lineId, note, token));
        if (this.eventId === eventId) await this.load(eventId);
        return true;
      } catch (error) {
        if (this.eventId === eventId) this.actionError = error.message;
        return false;
      } finally {
        if (this.eventId === eventId) this.isSubmitting = false;
      }
    },
  },
});
