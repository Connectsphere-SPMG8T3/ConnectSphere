import { defineStore } from "pinia";
import { eventsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

export const useSafetyDecisionStore = defineStore("safetyDecision", {
  state: () => ({ queue: [], review: null, decisions: [], reviewEventId: null, reviewGeneration: 0, loading: false, error: null }),
  actions: {
    async loadQueue() {
      this.loading = true;
      this.error = null;
      try {
        const response = await useAuthStore().withSession((token) => eventsApi.safetyQueue(token));
        this.queue = response.items;
      } catch (error) {
        this.queue = [];
        this.error = error.message;
      } finally {
        this.loading = false;
      }
    },
    async loadReview(eventId) {
      const generation = ++this.reviewGeneration;
      this.reviewEventId = eventId;
      this.review = null;
      this.decisions = [];
      this.loading = true;
      this.error = null;
      try {
        const auth = useAuthStore();
        const review = await auth.withSession((token) => eventsApi.safetyReview(eventId, token));
        if (this.reviewGeneration !== generation || auth.role !== "safety_officer") return;
        this.review = review;
        this.decisions = review.decisions;
      } catch (error) {
        if (this.reviewGeneration === generation) this.error = error.message;
      } finally {
        if (this.reviewGeneration === generation) this.loading = false;
      }
    },
    async decide(kind, eventId, payload) {
      this.loading = true;
      this.error = null;
      let event;
      try {
        const call = { approve: eventsApi.safetyApprove, requestChanges: eventsApi.safetyRequestChanges, reject: eventsApi.safetyReject }[kind];
        event = await useAuthStore().withSession((token) => call(eventId, payload, token));
      } catch (error) {
        this.error = error.message;
        throw error;
      } finally {
        this.loading = false;
      }
      // The event leaves review on success. Clear its private review rather
      // than issuing a read that will intentionally return 404.
      this.reviewGeneration += 1;
      this.reviewEventId = null;
      this.review = null;
      this.decisions = [];
      await this.loadQueue();
      return event;
    },
  },
});
