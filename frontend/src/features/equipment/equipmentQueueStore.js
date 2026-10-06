import { defineStore } from "pinia";

import { equipmentApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

/**
 * Tech support's pending equipment request lines across every open event
 * (SCRUM-45; tech support are a pool, AUTH-R5). Read-only: reserving and
 * rejecting lines is SCRUM-24's.
 */
export const useEquipmentQueueStore = defineStore("equipmentQueue", {
  state: () => ({ lines: [], isLoading: false, error: null }),

  actions: {
    async load() {
      const auth = useAuthStore();
      this.isLoading = true;
      this.error = null;
      try {
        const response = await auth.withSession((token) => equipmentApi.pendingRequests(token));
        this.lines = response?.lines ?? [];
      } catch (error) {
        this.lines = [];
        this.error = error.message;
      } finally {
        this.isLoading = false;
      }
    },
  },
});
