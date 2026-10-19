import { defineStore } from "pinia";

import { equipmentApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

/**
 * One event's equipment as Technical Support arrange it (SCRUM-24): its lines
 * with notes, the exit tick, the derived technical status and the history.
 *
 * Every action reloads the view afterwards, because the database moves more
 * than the line acted on (the technical status, the history, sometimes the
 * tick). `eventId` marks which event the state belongs to; a slow answer for a
 * previous event never lands on the current one (as useEquipmentRequestStore).
 * Errors from an action are kept per line (`lineErrors`) so a refusal shows
 * beside the line it refused.
 */
export const useTechnicalEventStore = defineStore("technicalEvent", {
  state: () => ({
    eventId: null,
    view: null,
    isLoading: false,
    error: null,
    busy: null,
    lineErrors: {},
    exitError: null,
  }),

  actions: {
    async load(eventId) {
      const auth = useAuthStore();
      if (this.eventId !== eventId) {
        this.view = null;
        this.lineErrors = {};
        this.exitError = null;
        this.busy = null;
      }
      this.eventId = eventId;
      this.isLoading = true;
      this.error = null;
      try {
        const view = await auth.withSession((token) => equipmentApi.technicalView(eventId, token));
        if (this.eventId === eventId) this.view = view;
      } catch (error) {
        if (this.eventId === eventId) this.error = error.message;
      } finally {
        if (this.eventId === eventId) this.isLoading = false;
      }
    },

    async _lineAction(lineId, call) {
      const eventId = this.eventId;
      if (!eventId || this.busy) return false;
      const auth = useAuthStore();
      this.busy = lineId;
      this.lineErrors = { ...this.lineErrors, [lineId]: null };
      try {
        await auth.withSession(call);
        return true;
      } catch (error) {
        if (this.eventId === eventId) this.lineErrors = { ...this.lineErrors, [lineId]: error.message };
        return false;
      } finally {
        if (this.eventId === eventId) {
          this.busy = null;
          await this.load(eventId);
        }
      }
    },

    reserve(lineId) {
      return this._lineAction(lineId, (token) => equipmentApi.reserveLine(lineId, token));
    },

    markNotAvailable(lineId, reason) {
      return this._lineAction(lineId, (token) => equipmentApi.markNotAvailable(lineId, reason.trim(), token));
    },

    saveNote(lineId, note) {
      return this._lineAction(lineId, (token) => equipmentApi.setLineNote(lineId, note.trim() || null, token));
    },

    async setExitConfirmation(confirmed) {
      const eventId = this.eventId;
      if (!eventId || this.busy) return false;
      const auth = useAuthStore();
      this.busy = "exit";
      this.exitError = null;
      try {
        await auth.withSession((token) => equipmentApi.setExitConfirmation(eventId, confirmed, token));
        return true;
      } catch (error) {
        if (this.eventId === eventId) this.exitError = error.message;
        return false;
      } finally {
        if (this.eventId === eventId) {
          this.busy = null;
          await this.load(eventId);
        }
      }
    },
  },
});
