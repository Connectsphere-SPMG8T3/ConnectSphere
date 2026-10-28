import { defineStore } from "pinia";

import { registrationsApi } from "@/services/api";
import { useAuthStore } from "@/stores/auth";

export const useRegistrationStore = defineStore("registrations", {
  state: () => ({
    events: [],
    event: null,
    myRegistrations: [],
    registrationResult: null,
    isLoading: false,
    isLoadingMyRegistrations: false,
    isRegistering: false,
    error: null,
    myRegistrationsError: null,
  }),

  actions: {
    async loadDirectory() {
      this.isLoading = true;
      this.error = null;
      try {
        const response = await registrationsApi.directory();
        this.events = response.events ?? [];
      } catch (error) {
        this.error = error.message || "Unable to load events. Please try again.";
        throw error;
      } finally {
        this.isLoading = false;
      }
    },

    async loadEvent(eventId) {
      this.isLoading = true;
      this.error = null;
      this.registrationResult = null;
      try {
        this.event = await registrationsApi.event(eventId);
      } catch (error) {
        this.error = error.message || "Unable to load this event. Please try again.";
        throw error;
      } finally {
        this.isLoading = false;
      }
    },

    async loadMyRegistrations() {
      const auth = useAuthStore();
      this.isLoadingMyRegistrations = true;
      this.myRegistrationsError = null;
      try {
        const response = await auth.withSession((token) => registrationsApi.myRegistrations(token));
        this.myRegistrations = response.registrations ?? [];
      } catch (error) {
        this.myRegistrationsError = error.message || "Unable to load your registered events. Please try again.";
        throw error;
      } finally {
        this.isLoadingMyRegistrations = false;
      }
    },

    async register(eventId) {
      const auth = useAuthStore();
      this.isRegistering = true;
      this.error = null;
      try {
        this.registrationResult = await auth.withSession((token) => registrationsApi.register(eventId, token));
        if (this.event?.id === eventId) {
          try {
            this.event = await registrationsApi.event(eventId);
          } catch {
            this.error = "You are registered, but the updated place count could not be loaded.";
          }
        }
        return this.registrationResult;
      } catch (error) {
        if (error.status === 409 && /full/i.test(error.message)) {
          if (this.event?.id === eventId) this.event.availability = "full";
        }
        this.error = error.message || "Registration could not be completed.";
        throw error;
      } finally {
        this.isRegistering = false;
      }
    },
  },
});