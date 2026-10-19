import { defineStore } from "pinia";

import { waitingCount } from "@/features/equipment/requestList";
import { equipmentApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

/**
 * Tech support's equipment request lines across every open event (SCRUM-45,
 * SCRUM-24; tech support are a pool, AUTH-R5). Every status is loaded, so the
 * requests page can show resolved lines for reference; the dashboard tile
 * counts the ones waiting on tech support. `isLoaded` stays false until a
 * response arrives, so a failed load shows a dash rather than a zero.
 */
export const useEquipmentQueueStore = defineStore("equipmentQueue", {
  state: () => ({ lines: [], isLoading: false, isLoaded: false, error: null }),

  getters: {
    waitingCount: (state) => waitingCount(state.lines),
  },

  actions: {
    async load() {
      const auth = useAuthStore();
      this.isLoading = true;
      this.error = null;
      try {
        const response = await auth.withSession((token) => equipmentApi.requestList(token));
        this.lines = response?.lines ?? [];
        this.isLoaded = true;
      } catch (error) {
        this.lines = [];
        this.isLoaded = false;
        this.error = error.message;
      } finally {
        this.isLoading = false;
      }
    },
  },
});
