import { createPinia, setActivePinia } from "pinia";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, authApi } from "@/services/api";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: { login: vi.fn(), refresh: vi.fn(), me: vi.fn(), logout: vi.fn() },
}));

const STORAGE_KEY = "connectsphere.session";
const EXPIRED = "Your session has expired. Please sign in again.";
const PROFILE = { id: "u1", role: "event_coordinator", roles: ["event_coordinator"] };
const SESSION = { access_token: "new-access", refresh_token: "new-refresh", profile: PROFILE };

async function freshStore(stored = null) {
  if (stored) localStorage.setItem(STORAGE_KEY, stored);
  vi.resetModules();
  const { useAuthStore } = await import("@/stores/auth");
  setActivePinia(createPinia());
  return useAuthStore();
}

const signedIn = () =>
  freshStore(JSON.stringify({ token: "old-access", refreshToken: "old-refresh", profile: PROFILE }));

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
});

afterEach(() => vi.restoreAllMocks());

describe("signing in", () => {
  it("stores the session and returns the profile", async () => {
    const store = await freshStore();
    authApi.login.mockResolvedValue(SESSION);

    await expect(store.login("e", "p")).resolves.toEqual(PROFILE);

    expect(authApi.login).toHaveBeenCalledWith("e", "p");
    expect(store.token).toBe("new-access");
    expect(store.sessionVerified).toBe(true);
    expect(store.isLoading).toBe(false);
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY)).refreshToken).toBe("new-refresh");
  });

  it("shows the server's message when the sign-in is refused", async () => {
    const store = await freshStore();
    authApi.login.mockRejectedValue(new ApiError("Invalid email or password.", 401));

    await expect(store.login("e", "p")).rejects.toThrow();

    expect(store.error).toBe("Invalid email or password.");
    expect(store.isAuthenticated).toBe(false);
    expect(store.isLoading).toBe(false);
  });

  it("explains a failed connection without leaking its text", async () => {
    const store = await freshStore();
    authApi.login.mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(store.login("e", "p")).rejects.toThrow();

    expect(store.error).toBe("Unable to reach the server. Please try again.");
  });
});

describe("stored sessions", () => {
  it("ignores a stored session it cannot read", async () => {
    const store = await freshStore("{not json");

    expect(store.isAuthenticated).toBe(false);
  });

  it("keeps working in memory when storage is blocked", async () => {
    const store = await freshStore();
    authApi.login.mockResolvedValue(SESSION);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("Blocked");
    });

    await store.login("e", "p");

    expect(store.token).toBe("new-access");
  });
});

describe("renewing a session", () => {
  it("ends the session when there is no refresh token", async () => {
    const store = await freshStore();

    await expect(store.refreshSession()).rejects.toMatchObject({ status: 401 });

    expect(store.error).toBe(EXPIRED);
  });

  it("shares one refresh between concurrent callers", async () => {
    const store = await signedIn();
    authApi.refresh.mockResolvedValue(SESSION);

    await Promise.all([store.refreshSession(), store.refreshSession()]);

    expect(authApi.refresh).toHaveBeenCalledTimes(1);
    expect(authApi.refresh).toHaveBeenCalledWith("old-refresh");
    expect(store.token).toBe("new-access");
  });

  it("retries a call once with the renewed token", async () => {
    const store = await signedIn();
    authApi.refresh.mockResolvedValue(SESSION);
    const call = vi.fn().mockRejectedValueOnce(new ApiError("Expired", 401)).mockResolvedValueOnce("done");

    await expect(store.withSession(call)).resolves.toBe("done");

    expect(call.mock.calls).toEqual([["old-access"], ["new-access"]]);
  });

  it("does not renew for any other failure", async () => {
    const store = await signedIn();
    const failure = new ApiError("Forbidden", 403);

    await expect(store.withSession(vi.fn().mockRejectedValue(failure))).rejects.toBe(failure);

    expect(authApi.refresh).not.toHaveBeenCalled();
  });

  it("refuses a call with no session", async () => {
    const store = await freshStore();

    await expect(store.withSession(vi.fn())).rejects.toMatchObject({ status: 401 });
  });
});

describe("reading the profile", () => {
  it("has nothing to read without a session", async () => {
    const store = await freshStore();

    await expect(store.fetchProfile()).resolves.toBeNull();
    expect(authApi.me).not.toHaveBeenCalled();
  });

  it("verifies and stores the profile", async () => {
    const store = await signedIn();
    authApi.me.mockResolvedValue({ ...PROFILE, full_name: "Sam Lee" });

    await store.fetchProfile();

    expect(store.sessionVerified).toBe(true);
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY)).profile.full_name).toBe("Sam Lee");
  });
});

describe("signing out", () => {
  it("clears the session before telling the server", async () => {
    const store = await signedIn();
    authApi.logout.mockImplementation(async () => expect(store.token).toBeNull());

    await store.logout();

    expect(authApi.logout).toHaveBeenCalledWith("old-access");
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it("has nothing to tell the server without a session", async () => {
    const store = await freshStore();

    await store.logout();

    expect(authApi.logout).not.toHaveBeenCalled();
  });

  it("renews an expired token to end the session on the server", async () => {
    const store = await signedIn();
    authApi.logout.mockRejectedValueOnce(new ApiError("Expired", 401)).mockResolvedValueOnce(null);
    authApi.refresh.mockResolvedValue(SESSION);

    await store.logout();

    expect(authApi.refresh).toHaveBeenCalledWith("old-refresh");
    expect(authApi.logout).toHaveBeenLastCalledWith("new-access");
  });

  it("stays signed out even when that renewal fails", async () => {
    const store = await signedIn();
    authApi.logout.mockRejectedValue(new ApiError("Expired", 401));
    authApi.refresh.mockRejectedValue(new ApiError("Revoked", 401));

    await expect(store.logout()).resolves.toBeUndefined();

    expect(store.isAuthenticated).toBe(false);
  });

  it("does not renew after an outage", async () => {
    const store = await signedIn();
    authApi.logout.mockRejectedValue(new ApiError("Unavailable", 503));

    await store.logout();

    expect(authApi.refresh).not.toHaveBeenCalled();
  });
});
