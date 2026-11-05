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
    isWithdrawing: false,
    isUpdatingRegistration: false,
    error: null,
    myRegistrationsError: null,
    // A failed accept or decline, shown beside the invitation. Kept apart from
    // the load error, which replaces the page (D90).
    registrationActionError: null,
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

    async withdraw(eventId) {
      const auth = useAuthStore();
      this.isWithdrawing = true;
      this.error = null;
      try {
        const result = await auth.withSession((token) => registrationsApi.withdraw(eventId, token));
        this.myRegistrations = this.myRegistrations.filter(({ event }) => event.id !== eventId);
        const refreshResults = await Promise.allSettled([
          this.loadMyRegistrations(),
          this.loadDirectory(),
        ]);
        const refreshError = refreshResults.find(({ status }) => status === "rejected");
        if (refreshError) {
          this.error = `Registration was withdrawn, but updated event data could not be loaded: ${refreshError.reason.message || "Please refresh and try again."}`;
        }
        return result;
      } catch (error) {
        this.error = error.message || "Registration could not be withdrawn.";
        throw error;
      } finally {
        this.isWithdrawing = false;
      }
    },

    async acceptInvitation(registrationId) {
      const auth = useAuthStore();
      this.isUpdatingRegistration = true;
      this.registrationActionError = null;
      try {
        const result = await auth.withSession((token) =>
          registrationsApi.acceptInvitation(registrationId, token),
        );
        await this.loadMyRegistrations();
        return result;
      } catch (error) {
        this.registrationActionError = error.message || "The invitation could not be accepted.";
        throw error;
      } finally {
        this.isUpdatingRegistration = false;
      }
    },

    async leaveWaitlist(registrationId) {
      const auth = useAuthStore();
      this.isUpdatingRegistration = true;
      this.registrationActionError = null;
      try {
        await auth.withSession((token) => registrationsApi.leaveWaitlist(registrationId, token));
        await this.loadMyRegistrations();
      } catch (error) {
        this.registrationActionError = error.message || "You could not leave the waitlist.";
        throw error;
      } finally {
        this.isUpdatingRegistration = false;
      }
    },
  },
});