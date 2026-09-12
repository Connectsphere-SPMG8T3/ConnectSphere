import { defineStore } from "pinia";

import { ApiError, authApi } from "@/services/api";

const STORAGE_KEY = "connectsphere.session";

export const ROLE_DASHBOARD_ROUTES = {
  event_organiser: "/dashboard/organiser",
  event_coordinator: "/dashboard/coordinator",
  venue_staff: "/dashboard/venue-staff",
  tech_support: "/dashboard/tech-support",
  attendee: "/dashboard/attendee",
};

function loadPersistedSession() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function persistSession(token, profile) {
  try {
    if (token && profile) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ token, profile }));
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // localStorage may be unavailable (private browsing, blocked storage);
    // the session simply won't survive a page reload in that case.
  }
}

const persisted = loadPersistedSession();

export const useAuthStore = defineStore("auth", {
  state: () => ({
    token: persisted?.token ?? null,
    profile: persisted?.profile ?? null,
    isLoading: false,
    error: null,
  }),

  getters: {
    isAuthenticated: (state) => Boolean(state.token && state.profile),
    role: (state) => state.profile?.role ?? null,
    dashboardPath: (state) => ROLE_DASHBOARD_ROUTES[state.profile?.role] ?? "/login",
  },

  actions: {
    async login(email, password) {
      this.isLoading = true;
      this.error = null;
      try {
        const result = await authApi.login(email, password);
        this.token = result.access_token;
        this.profile = result.profile;
        persistSession(this.token, this.profile);
        return result.profile;
      } catch (err) {
        this.token = null;
        this.profile = null;
        persistSession(null, null);
        this.error =
          err instanceof ApiError ? err.message : "Unable to reach the server. Please try again.";
        throw err;
      } finally {
        this.isLoading = false;
      }
    },

    async fetchProfile() {
      if (!this.token) return null;
      this.isLoading = true;
      try {
        const profile = await authApi.me(this.token);
        this.profile = profile;
        persistSession(this.token, this.profile);
        return profile;
      } catch (err) {
        this.token = null;
        this.profile = null;
        persistSession(null, null);
        throw err;
      } finally {
        this.isLoading = false;
      }
    },

    async logout() {
      const token = this.token;
      this.token = null;
      this.profile = null;
      this.error = null;
      persistSession(null, null);
      if (token) {
        try {
          await authApi.logout(token);
        } catch {
          // The client-side session is already cleared; a failed
          // server-side revocation should not block the user from logging out.
        }
      }
    },
  },
});
