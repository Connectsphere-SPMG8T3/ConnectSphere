import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, authApi } from "@/services/api";

vi.mock("@/services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  authApi: {
    login: vi.fn(),
    refresh: vi.fn(),
    me: vi.fn(),
    logout: vi.fn(),
    setActiveRole: vi.fn(),
    updateProfile: vi.fn(),
  },
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

describe("auth store role switching (SCRUM-74/75)", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it("has no roles and is not multi-role when the profile predates the roles field", async () => {
    const store = await storeWithStoredSession();

    expect(store.roles).toEqual([]);
    expect(store.hasMultipleRoles).toBe(false);
  });

  it("is multi-role only once the profile lists two or more roles", async () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        ...STORED_SESSION,
        profile: { ...PROFILE, roles: ["event_coordinator", "venue_staff"] },
      }),
    );
    vi.resetModules();
    const { useAuthStore } = await import("@/stores/auth");
    setActivePinia(createPinia());
    const store = useAuthStore();

    expect(store.roles).toEqual(["event_coordinator", "venue_staff"]);
    expect(store.hasMultipleRoles).toBe(true);
  });

  it("switches the active role and persists the updated profile", async () => {
    const store = await storeWithStoredSession();
    const updatedProfile = { ...PROFILE, role: "venue_staff", roles: ["event_coordinator", "venue_staff"] };
    authApi.setActiveRole.mockResolvedValue(updatedProfile);

    await store.setActiveRole("venue_staff");

    expect(authApi.setActiveRole).toHaveBeenCalledWith(STORED_SESSION.token, "venue_staff");
    expect(store.role).toBe("venue_staff");
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY)).profile).toEqual(updatedProfile);
  });

  it("leaves the active role unchanged when the switch is rejected", async () => {
    const store = await storeWithStoredSession();
    authApi.setActiveRole.mockRejectedValue(new ApiError("You do not hold the 'venue_staff' role.", 403));

    await expect(store.setActiveRole("venue_staff")).rejects.toThrow();

    expect(store.role).toBe("event_coordinator");
  });
});

describe("auth store profile editing (SCRUM-92)", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it("updates and persists the profile returned by the API", async () => {
    const store = await storeWithStoredSession();
    const updatedProfile = { ...PROFILE, full_name: "Updated Name", phone_number: null };
    const changes = { full_name: "Updated Name", phone_number: null };
    authApi.updateProfile.mockResolvedValue(updatedProfile);

    await store.updateProfile(changes);

    expect(authApi.updateProfile).toHaveBeenCalledWith(STORED_SESSION.token, changes);
    expect(store.profile).toEqual(updatedProfile);
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY)).profile).toEqual(updatedProfile);
  });

  it("leaves the stored profile unchanged when the update is rejected", async () => {
    const store = await storeWithStoredSession();
    authApi.updateProfile.mockRejectedValue(new ApiError("Full name is required.", 422));

    await expect(store.updateProfile({ full_name: "", phone_number: null })).rejects.toThrow();

    expect(store.profile).toEqual(PROFILE);
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY)).profile).toEqual(PROFILE);
  });
});

describe("staff roles added for 12 AC12 and CR-103 AC5", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it.each([
    ["event_coordinator_lead", "/dashboard/coordinator-lead", "Event Coordinator Lead"],
    ["safety_officer", "/dashboard/safety", "Safety Officer"],
  ])("lands %s on %s and labels it %s", async (role, path, label) => {
    const store = await storeWithStoredSession();
    store.profile = { ...PROFILE, role };
    const { ROLE_LABELS } = await import("@/stores/auth");

    expect(store.dashboardPath).toBe(path);
    expect(ROLE_LABELS[role]).toBe(label);
  });
});
