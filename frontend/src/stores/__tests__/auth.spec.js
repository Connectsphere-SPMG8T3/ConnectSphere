import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, authApi } from "@/services/api";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
}));

const STORAGE_KEY = "connectsphere.session";
const PROFILE = { id: "u1", email: "coordinator@connectsphere.dev", role: "event_coordinator" };
const STORED_SESSION = { token: "stored-access", refreshToken: "stored-refresh", profile: PROFILE };

async function storeWithStoredSession() {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(STORED_SESSION));
  // The store reads localStorage when its module loads, so load a fresh copy.
  vi.resetModules();
  const { useAuthStore } = await import("@/stores/auth");
  setActivePinia(createPinia());
  return useAuthStore();
}

function expectStoredSessionKept(store) {
  expect(store.token).toBe(STORED_SESSION.token);
  expect(store.refreshToken).toBe(STORED_SESSION.refreshToken);
  expect(store.isAuthenticated).toBe(true);
  expect(JSON.parse(localStorage.getItem(STORAGE_KEY))).toEqual(STORED_SESSION);
}

describe("auth store session verification", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it("keeps the stored session when the API is temporarily unavailable", async () => {
    const store = await storeWithStoredSession();
    authApi.me.mockRejectedValue(new ApiError("Temporarily unavailable.", 503));

    await expect(store.fetchProfile()).rejects.toThrow();

    expectStoredSessionKept(store);
  });

  it("keeps the stored session when renewing it hits an unavailable API", async () => {
    const store = await storeWithStoredSession();
    authApi.me.mockRejectedValue(new ApiError("Invalid or expired authentication token.", 401));
    authApi.refresh.mockRejectedValue(new ApiError("Temporarily unavailable.", 503));

    await expect(store.fetchProfile()).rejects.toThrow();

    expectStoredSessionKept(store);
  });

  it("signs out when the server rejects both the access and refresh tokens", async () => {
    const store = await storeWithStoredSession();
    authApi.me.mockRejectedValue(new ApiError("Invalid or expired authentication token.", 401));
    authApi.refresh.mockRejectedValue(new ApiError("Invalid or expired authentication token.", 401));

    await expect(store.fetchProfile()).rejects.toThrow();

    expect(store.isAuthenticated).toBe(false);
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });
});
