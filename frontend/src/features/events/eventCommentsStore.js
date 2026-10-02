import { defineStore } from "pinia";

import { validateComment } from "@/features/events/comments";
import { eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

/**
 * The discussion thread on one event (SCRUM-61), shared by the organiser's and the
 * coordinator's event pages. `eventId` marks which event the state belongs to; every
 * request re-checks it after its await, so a slow response for a previous event can
 * never land on the current one (the same guard as useEventReviewStore).
 */
export const useEventCommentsStore = defineStore("eventComments", {
  state: () => ({ eventId: null, comments: [], isLoading: false, isPosting: false, error: null }),

  actions: {
    async load(eventId) {
      const auth = useAuthStore();
      if (this.eventId !== eventId) this.comments = [];
      this.eventId = eventId;
      this.isLoading = true;
      this.error = null;
      try {
        const response = await auth.withSession((token) => eventsApi.listComments(eventId, token));
        if (this.eventId !== eventId) return;
        this.comments = response?.comments ?? [];
      } catch (error) {
        if (this.eventId !== eventId) return;
        this.comments = [];
        this.error = error.message;
      } finally {
        if (this.eventId === eventId) this.isLoading = false;
      }
    },

    async post(text) {
      const eventId = this.eventId;
      if (!eventId || validateComment(text)) return false;
      const auth = useAuthStore();
      this.isPosting = true;
      this.error = null;
      try {
        const saved = await auth.withSession((token) => eventsApi.addComment(eventId, text.trim(), token));
        if (this.eventId !== eventId) return false;
        this.comments = [...this.comments, saved];
        return true;
      } catch (error) {
        if (this.eventId === eventId) this.error = error.message;
        return false;
      } finally {
        if (this.eventId === eventId) this.isPosting = false;
      }
    },
  },
});
