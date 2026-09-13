import { defineStore } from "pinia";

import { ApiError, authApi } from "@/services/api";

const STORAGE_KEY = "connectsphere.session";
const SESSION_EXPIRED_MESSAGE = "Your session has expired. Please sign in again.";

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

function persistSession({ token, refreshToken, profile }) {
  try {
    if (token && refreshToken && profile) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ token, refreshToken, profile }));
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // localStorage may be unavailable (private browsing, blocked storage);
    // the session simply won't survive a page reload in that case.
  }
}

const persisted = loadPersistedSession();

// Supabase rotates the refresh token every time it is used, so concurrent 401s
// must share a single refresh call instead of each spending the same token.
let refreshInFlight = null;

export const useAuthStore = defineStore("auth", {
  state: () => ({
    token: persisted?.token ?? null,
    refreshToken: persisted?.refreshToken ?? null,
    profile: persisted?.profile ?? null,
    sessionVerified: false,
    isLoading: false,
    error: null,
  }),

  getters: {
    isAuthenticated: (state) => Boolean(state.token && state.profile),
    role: (state) => state.profile?.role ?? null,
    dashboardPath: (state) => ROLE_DASHBOARD_ROUTES[state.profile?.role] ?? "/login",
  },

  actions: {
    applySession(result) {
      this.token = result.access_token;
      this.refreshToken = result.refresh_token;
      this.profile = result.profile;
      this.sessionVerified = true;
      persistSession(this);
    },

    clearSession(message = null) {
      this.token = null;
      this.refreshToken = null;
      this.profile = null;
      this.sessionVerified = false;
      this.error = message;
      persistSession(this);
    },

    async login(email, password) {
      this.isLoading = true;
      this.error = null;
      try {
        const result = await authApi.login(email, password);
        this.applySession(result);
        return result.profile;
      } catch (err) {
        this.clearSession(
          err instanceof ApiError ? err.message : "Unable to reach the server. Please try again.",
        );
        throw err;
      } finally {
        this.isLoading = false;
      }
    },

    refreshSession() {
      if (!this.refreshToken) {
        this.clearSession(SESSION_EXPIRED_MESSAGE);
        return Promise.reject(new ApiError(SESSION_EXPIRED_MESSAGE, 401));
      }
      if (!refreshInFlight) {
        refreshInFlight = authApi
          .refresh(this.refreshToken)
          .then((result) => this.applySession(result))
          .catch((err) => {
            if (err instanceof ApiError) this.clearSession(SESSION_EXPIRED_MESSAGE);
            throw err;
          })
          .finally(() => {
            refreshInFlight = null;
          });
      }
      return refreshInFlight;
    },

    /**
     * Run an authenticated API call; if the access token has expired, renew the
     * session once with the refresh token and retry. Use this for every call
     * that needs a token instead of passing `authStore.token` directly.
     */
    async withSession(call) {
      if (!this.token) throw new ApiError(SESSION_EXPIRED_MESSAGE, 401);
      try {
        return await call(this.token);
      } catch (err) {
        if (!(err instanceof ApiError) || err.status !== 401) throw err;
        await this.refreshSession();
        return call(this.token);
      }
    },

    async fetchProfile() {
      if (!this.token) return null;
      this.isLoading = true;
      try {
        const profile = await this.withSession((token) => authApi.me(token));
        this.profile = profile;
        this.sessionVerified = true;
        persistSession(this);
        return profile;
      } catch (err) {
        // The server rejected the session (401/404): sign out. Network errors
        // keep the stored session so a brief outage doesn't log the user out.
        if (err instanceof ApiError && this.token) this.clearSession(SESSION_EXPIRED_MESSAGE);
        throw err;
      } finally {
        this.isLoading = false;
      }
    },

    async logout() {
      const { token, refreshToken } = this;
      this.clearSession();
      if (!token) return;
      try {
        await authApi.logout(token);
      } catch (err) {
        // An expired access token can't authorise the revoke, so renew once to
        // still end the server-side session. Best-effort: the local session is
        // already cleared either way.
        if (err instanceof ApiError && err.status === 401 && refreshToken) {
          try {
            const renewed = await authApi.refresh(refreshToken);
            await authApi.logout(renewed.access_token);
          } catch {
            // Session already revoked or unreachable server; nothing left to do.
          }
        }
      }
    },
  },
});
